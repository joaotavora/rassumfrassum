"""
LSP-specific message routing and merging logic.
"""

import asyncio
from dataclasses import dataclass, field
from functools import reduce
from typing import cast, Callable, Awaitable, Optional

from .json import JSON
from .util import (
    dmerge,
    is_scalar,
    debug,
)


@dataclass
class Server:
    """Information about a logical LSP server."""

    name: str
    caps: JSON = field(default_factory=dict)
    cookie: object = None


@dataclass
class DocumentState:
    """State for tracking diagnostics for a document."""

    docver: int
    inflight_pushes: dict[int, list] = field(
        default_factory=dict
    )  # server_id -> diagnostics
    inflight_pulls: dict[int, None] = field(
        default_factory=dict
    )  # server_id -> None (acts as a set for now)
    push_diags_timer: Optional[asyncio.Task] = None
    dispatched: bool = False
    stashed_items: set[int] = field(
        default_factory=set
    )  # lean_ids of stashed completion/codeAction items


@dataclass
class PayloadItem:
    """A payload item for aggregation."""

    payload: JSON | list
    server: Server
    is_error: bool


@dataclass
class DirectResponse:
    """A direct response payload to send immediately without forwarding."""

    payload: JSON
    is_error: bool = False


class LspLogic:
    """Decide on message routing and response aggregation."""

    def __init__(
        self,
        servers: list[Server],
        send_notification: Callable[[str, JSON], Awaitable[None]],
        opts,
    ):
        """Initialize with all servers, a notification sender, and options."""
        self.primary = servers[0]
        self.send_notification = send_notification
        self.opts = opts
        # Track document state: URI -> DocumentState
        self.document_state: dict[str, DocumentState] = {}
        # Map server ID to server object for data recovery
        self.servers: dict[int, Server] = {id(s): s for s in servers}
        # Stash for lean identifiers: lean_id -> (payload, original_data, server)
        self.stash: dict[int, tuple[JSON, JSON | None, Server]] = {}

    async def on_client_request(
        self, method: str, params: JSON, servers: list[Server]
    ) -> list[Server] | DirectResponse:
        """
        Handle client requests and determine who receives it

        Args:
            method: LSP method name
            params: Request parameters
            servers: List of available servers (primary first)

        Returns:
            List of servers that should receive the request, or
            DirectResponse to send immediately without forwarding
        """
        # Check for data recovery from stash
        if (
            method.endswith("resolve")
            and (stashed := self.stash.get(cast(int, params.get('data'))))
        ):
            payload, original_data, server = stashed
            if original_data is not None:
                # Happy case: restore original data and route to server
                params['data'] = original_data
                return [server]
            else:
                # Unhappy case: no original data, respond immediately with stashed payload
                return DirectResponse(payload=payload)

        # initialize and shutdown go to all servers
        if method in ['initialize', 'shutdown']:
            # Force UTF-16 encoding to avoid position mismatches (#8)
            if method == 'initialize' and (
                g := params['capabilities'].get('general')
            ):
                g['positionEncodings'] = ['utf-16']
            return servers

        # Route requests to _all_ servers supporting this
        if method == 'textDocument/codeAction':
            return [s for s in servers if s.caps.get('codeActionProvider')]

        # Completions is special
        if method == 'textDocument/completion':
            cands = [s for s in servers if s.caps.get('completionProvider')]
            if len(cands) <= 1:
                return cands
            if k := params.get("context", {}).get("triggerCharacter"):
                return [
                    s
                    for s in cands
                    if (cp := s.caps.get("completionProvider"))
                    and k in cp.get("triggerCharacters", [])
                ]
            else:
                return cands

        # Route these to at most one server supporting this capability
        if cap := {
            'textDocument/rename': 'renameProvider',
            'textDocument/formatting': 'documentFormattingProvider',
            'textDocument/rangeFormatting': 'documentRangeFormattingProvider',
        }.get(method):
            for s in servers:
                if s.caps.get(cap):
                    return [s]
            return []

        # Handle pull diagnostics requests
        if method == 'textDocument/diagnostic':
            # fmt: off
            if (
                (text_doc := params.get('textDocument'))
                and (uri := text_doc.get('uri'))
                and (state := self.document_state.get(uri))
                and (targets := [s for s in servers if s.caps.get('diagnosticProvider')])
            ):
                # Register inflight pulls for all target servers
                for target in targets:
                    state.inflight_pulls[id(target)] = None

                # Check if this helps completes an ongoing push aggregation
                if self._pushdiags_complete(state):
                    await self._publish_pushdiags(uri, state)

                return targets
            return []

        # Default: route to primary server
        return [servers[0]] if servers else []

    async def on_client_notification(self, method: str, params: JSON) -> None:
        """
        Handle client notifications to track document state.
        """

        def reset_state(uri: str, version: Optional[int]):
            """Reset document state. If version is None, close the document."""
            if state := self.document_state.get(uri):
                if state.push_diags_timer:
                    state.push_diags_timer.cancel()
                # Clean up stashed items for this document
                for lean_id in state.stashed_items:
                    self.stash.pop(lean_id, None)
            if version is None:
                self.document_state.pop(uri, None)
            else:
                self.document_state[uri] = DocumentState(docver=version)

        if method in (
            'textDocument/didOpen',
            'textDocument/didChange',
            'textDocument/didClose',
        ):
            doc = params.get('textDocument', {})
            if (uri := doc.get('uri')) is not None:
                v = (
                    None
                    if method == 'textDocument/didClose'
                    else doc.get('version')
                )
                reset_state(uri, v)

    async def on_client_response(
        self,
        method: str,
        request_params: JSON,
        response_payload: JSON,
        is_error: bool,
        server: Server,
    ) -> None:
        """
        Handle client responses to server requests.
        """
        pass

    async def on_server_request(
        self, method: str, params: JSON, source: Server
    ) -> DirectResponse | None:
        """
        Handle server requests to the client.

        Returns:
            DirectResponse to send immediately without forwarding, or
            None to forward the request normally
        """
        pass

    async def on_server_notification(
        self, method: str, params: JSON, source: Server
    ) -> None:
        """
        Handle server notifications and forward to client.
        """
        # Special handling for diagnostics aggregation
        if (
            method == 'textDocument/publishDiagnostics'
            and (uri := params.get('uri'))
            and (state := self.document_state.get(uri))
        ):
            # Add source attribution
            diagnostics = params.get('diagnostics', [])
            for diag in diagnostics:
                if 'source' not in diag:
                    diag['source'] = source.name

            # Check version - drop stale diagnostics
            if (version := params.get('version')) and version != state.docver:
                return

            # Update aggregate with this server's diagnostics
            state.inflight_pushes[id(source)] = diagnostics

            # If already dispatched, decide whether to re-send or drop
            if state.dispatched:
                if self.opts.drop_tardy:
                    debug("Dropping tardy diagnostics")
                    return
                else:
                    debug("Re-sending enhanced aggregation for tardy diagnostics")
                    await self._publish_pushdiags(uri, state)
            elif self._pushdiags_complete(state):
                # All servers (push + pull) have responded, send immediately
                await self._publish_pushdiags(uri, state)
            # Check if this is the first diagnostic for this document
            elif len(state.inflight_pushes) == 1:
                # Start timeout task
                async def send_on_timeout():
                    await asyncio.sleep(
                        self.get_aggregation_timeout_ms(method) / 1000.0
                    )
                    await self._publish_pushdiags(uri, state)

                state.push_diags_timer = asyncio.create_task(send_on_timeout())

            return

        # Forward other notifications immediately
        await self.send_notification(method, params)

    async def on_server_response(
        self,
        method: str | None,
        request_params: JSON,
        payload: JSON,
        is_error: bool,
        server: Server,
    ) -> None:
        """
        Handle server responses.
        """
        if not payload or is_error:
            return

        # Stash data fields in codeAction responses
        if (
            method == 'textDocument/codeAction'
            and (uri := request_params.get('textDocument', {}).get('uri'))
            and (doc_state := self.document_state.get(uri))
        ):
            for action in cast(list, payload):
                self._stash_data(action, server, doc_state)

        # Stash data fields in completion responses
        if (
            method == 'textDocument/completion'
            and (uri := request_params.get('textDocument', {}).get('uri'))
            and (doc_state := self.document_state.get(uri))
        ):
            items = (
                payload
                if isinstance(payload, list)
                else payload.get('items', [])
            )
            for item in cast(list, items):
                self._stash_data(item, server, doc_state)

        # Extract server name and capabilities from initialize response
        if method == 'initialize':
            if 'name' in payload.get('serverInfo', {}):
                server.name = payload['serverInfo']['name']
            caps = payload.get('capabilities')
            server.caps = caps.copy() if caps else {}

    def get_aggregation_timeout_ms(self, method: str | None) -> int:
        """
        Get timeout in milliseconds for this aggregation.
        """
        if method == 'textDocument/publishDiagnostics':
            return 1000
        return 2500

    def aggregate_response_payloads(
        self,
        method: str,
        items: list[PayloadItem],
    ) -> tuple[JSON | list, bool]:
        """
        Aggregate payloads.
        Returns tuple of (aggregate payload, is_error).
        """

        # If all responses are errors, return the first error
        if all(item.is_error for item in items):
            return (items[0].payload, True)

        # Otherwise, skip errors and aggregate successful responses
        items = [item for item in items if not item.is_error]

        if method == 'textDocument/diagnostic':
            all_items = []
            for item in items:
                p = cast(JSON, item.payload)
                diagnostics = p.get('items', [])
                # Add source attribution
                for diag in diagnostics:
                    if 'source' not in diag:
                        diag['source'] = item.server.name
                all_items.extend(diagnostics)
            # FIXME: JT@2026-01-05: we elide any 'resultId', which
            # means we're missing out on that optimization
            res = {'items': all_items, 'kind': "full"}

        elif method == 'textDocument/codeAction':
            res = reduce(
                lambda acc, item: acc + (cast(list, item.payload) or []),
                items,
                [],
            )

        elif method == 'textDocument/completion':

            def normalize(x):
                return x if isinstance(x, dict) else {'items': x}

            # FIXME: Deep merging CompletionList properties is wrong
            # for many fields (e.g., isIncomplete should probably be OR'd)
            res = reduce(
                lambda acc, item: dmerge(acc, normalize(item.payload)),
                items,
                {},
            )

        elif method == 'initialize':
            res = reduce(
                lambda acc, item: self._merge_initialize_payloads(
                    acc, cast(JSON, item.payload), item.server
                ),
                items,
                {},
            )

        elif method == 'shutdown':
            res = {}

        else:
            res = reduce(
                lambda acc, item: dmerge(acc, cast(JSON, item.payload)),
                items,
                {},
            )

        return (res, False)

    def _merge_initialize_payloads(
        self, aggregate: JSON, payload: JSON, source: Server
    ) -> JSON:
        """Merge initialize response payloads (result objects)."""

        # Determine if this response is from primary
        primary_payload = source == self.primary

        # Merge capabilities by iterating through all keys
        res = aggregate.get('capabilities', {})
        new = payload.get('capabilities', {})

        for cap, newval in new.items():

            def t1sync(x):
                return x == 1 or (isinstance(x, dict) and x.get("change") == 1)

            if res.get(cap) is None:
                res[cap] = newval
            elif cap == 'textDocumentSync' and t1sync(newval):
                res[cap] = newval
            elif is_scalar(newval) and res.get(cap) is None:
                res[cap] = newval
            elif is_scalar(res.get(cap)) and not is_scalar(newval):
                res[cap] = newval
            elif (
                isinstance(res.get(cap), dict)
                and isinstance(newval, dict)
                and cap not in ["semanticTokensProvider"]
            ):
                # FIXME: This generic merging needs work. For example,
                # if one server has hoverProvider: true and another
                # has hoverProvider: {"workDoneProgress": true}, the
                # result should be {"workDoneProgress": false} to
                # retain the truish value while not announcing a
                # capability that one server doesn't support. However,
                # the correct merging strategy likely varies per
                # capability.
                res[cap] = dmerge(res.get(cap), newval)

        aggregate['capabilities'] = res

        # Merge serverInfo
        s_info = payload.get('serverInfo', {})
        if s_info:

            def merge_field(field: str, s: str) -> str:
                merged_info = aggregate.get('serverInfo', {})
                cur = merged_info.get(field, '')
                new = s_info.get(field, '')

                if not (cur and new):
                    return new or cur

                return f"{new}{s}{cur}" if primary_payload else f"{cur}{s}{new}"

            aggregate['serverInfo'] = {
                'name': merge_field('name', '+'),
                'version': merge_field('version', ','),
            }
        # Return the mutated aggregate
        return aggregate

    def _stash_data(self, payload: JSON, server: Server, doc_state: DocumentState):
        """Stash data field with lean identifier."""
        # Stash original data (or None) and server, replace with lean id
        original_data = payload.get('data')
        lean_id = id(payload)
        self.stash[lean_id] = (payload, original_data, server)
        payload['data'] = lean_id

        # Track lean_id in document state for cleanup
        doc_state.stashed_items.add(lean_id)

    def _pushdiags_complete(self, state: DocumentState) -> bool:
        """Check if diagnostic aggregation is complete for a document."""
        # Don't send empty aggregations - need at least one push diagnostic
        if not state.inflight_pushes:
            return False
        # Aggregation is complete when union of push diagnostics and inflight pulls covers all servers
        return (
            state.inflight_pushes.keys() | state.inflight_pulls.keys()
        ) == self.servers.keys()

    async def _publish_pushdiags(self, uri: str, state: DocumentState) -> None:
        """Send aggregated diagnostics to the client."""
        state.dispatched = True
        if state.push_diags_timer:
            state.push_diags_timer.cancel()

        await self.send_notification(
            'textDocument/publishDiagnostics',
            {
                'uri': uri,
                'version': state.docver,
                'diagnostics': reduce(
                    lambda acc, diags: acc + (cast(list, diags) or []),
                    state.inflight_pushes.values(),
                    [],
                ),
            },
        )
