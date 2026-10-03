"""
LSP-specific message routing and merging logic.
"""

import asyncio
import difflib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import reduce
from pathlib import PurePosixPath
from typing import Optional, cast
from urllib.parse import unquote, urlparse

from .json import JSON
from .util import (
    debug,
    dmerge,
    expand_braces,
    info,
    is_scalar,
    warn,
)


@dataclass
class Server:
    """Information about a logical LSP server."""

    name: str
    caps: JSON = field(default_factory=dict)
    cookie: object = None
    # textDocumentSync kind (0/1/2), or None if unknown
    sync_kind: int | None = None


@dataclass
class LspDocument:
    """Represents an LSP document."""

    uri: str
    docver: int
    text: str = ""
    stashed_items: set[int] = field(
        default_factory=set
    )  # lean_ids of stashed completion/codeAction items
    inflight_pushes: dict[int, list] = field(
        default_factory=dict
    )  # server_id -> diagnostics
    push_diags_timer: Optional[asyncio.Task] = None
    push_dispatched: bool = False
    inflight_pulls: dict[int, str | int] = field(
        default_factory=dict
    )  # server_id -> previousResultId


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
        notify_client: Callable[[str, JSON], Awaitable[None]],
        request_client: Callable[[str, JSON], Awaitable[tuple[bool, JSON]]],
        request_server: Callable[
            [Server, str, JSON], Awaitable[tuple[bool, JSON]]
        ],
        notify_server: Callable[[Server, str, JSON], Awaitable[None]],
        opts,
    ):
        """Initialize with all servers, notification and request senders, and options."""
        self.primary = servers[0]
        self.notify_client = notify_client
        self.request_client = request_client
        self.request_server = request_server
        self.notify_server = notify_server
        self.opts = opts
        # Track document state: URI -> LspDocument
        self.documents: dict[str, LspDocument] = {}
        # Map server ID to server object for data recovery
        self.servers: dict[int, Server] = {id(s): s for s in servers}
        # Stash for lean identifiers: lean_id -> (payload, original_data, server)
        self.stash: dict[int, tuple[JSON, JSON | None, Server]] = {}
        self.commands_map: dict[str, Server] = {}
        # Track file watchers: registration_id -> (server, list of expanded glob patterns)
        self.file_watchers: dict[str, tuple[Server, list[str]]] = {}

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
        if method.endswith("resolve") and (
            stashed := self.stash.get(cast(int, params.get('data')))
        ):
            payload, original_data, server = stashed
            if original_data is not None:
                # Happy case: restore original data and route to original server
                params['data'] = original_data
                return [server]
            elif payload:
                # Happier case: respond immediately with stashed payload
                return DirectResponse(payload=payload)
            else:
                # Oops!  This will be an error to the client
                return []

        # initialize goes to all servers
        elif method == 'initialize':
            doc_caps = params['capabilities']['textDocument']
            # Check for client $streamingDiagnostics capability
            if doc_caps.pop('$streamingDiagnostics', None):
                self.opts.stream_diagnostics = True

                info("Client requested streaming diagnostics mode")

            # Force UTF-16 encoding to avoid position mismatches (#8)
            if g := params['capabilities'].get('general'):
                g['positionEncodings'] = ['utf-16']

            # In streaming mode, add diagnostic capability to client
            if self.opts.stream_diagnostics:
                # TODO: also force versionSupport in the
                # publishDiagnostics cap.
                doc_caps['diagnostic'] = {'dynamicRegistration': False}
            return servers

        # shutdown goes to all servers
        elif method == 'shutdown':
            return servers

        # Route codeAction to all supporting servers
        elif method == 'textDocument/codeAction':
            return [s for s in servers if s.caps.get('codeActionProvider')]

        # Route location-based requests to all supporting servers
        elif cap := {
            'textDocument/definition': 'definitionProvider',
            'textDocument/typeDefinition': 'typeDefinitionProvider',
            'textDocument/implementation': 'implementationProvider',
            'textDocument/declaration': 'declarationProvider',
            'textDocument/references': 'referencesProvider',
        }.get(method):
            return [s for s in servers if s.caps.get(cap) is not None]

        elif method == 'workspace/executeCommand':
            probe = self.commands_map.get(cast(str, params.get('command')))
            return [probe] if probe else []

        # Completions is special
        elif method == 'textDocument/completion':
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
        elif cap := {
            'textDocument/rename': 'renameProvider',
            'textDocument/formatting': 'documentFormattingProvider',
            'textDocument/rangeFormatting': 'documentRangeFormattingProvider',
            'textDocument/documentSymbol': 'documentSymbolProvider',
        }.get(method):
            for s in servers:
                if s.caps.get(cap) is not None:
                    return [s]
            return []

        # Handle pull diagnostics requests
        elif method == 'textDocument/diagnostic':
            # fmt: off
            if (
                (text_doc := params.get('textDocument'))
                and (uri := text_doc.get('uri'))
                and (state := self.documents.get(uri))
                and (targets := [s for s in servers if s.caps.get('diagnosticProvider')])
            ):
                # Register inflight pulls for all target servers
                for target in targets:
                    state.inflight_pulls[id(target)] = -1

                # Check if this helps completes an ongoing push
                # aggregation JT@2026-01-08: hmmm, this should work,
                # but could also do it in on_server_response...
                if self._pushdiags_complete(state):
                    await self._publish_pushdiags(uri, state)

                return targets
            return []

        # Default: route to primary server
        return [servers[0]] if servers else []

    async def on_client_notification(self, method: str, params: JSON) -> None:
        """
        Handle client notifications to track document state and forward to servers.
        """

        async def forward_all():
            for server in self.servers.values():
                await self.notify_server(server, method, params)

        def close_state(uri: str) -> None:
            """Close document tracking for uri, if tracked."""
            if state := self.documents.get(uri):
                if state.push_diags_timer:
                    state.push_diags_timer.cancel()
                # Clean up stashed items for this document
                for lean_id in state.stashed_items:
                    self.stash.pop(lean_id, None)
                self.documents.pop(uri, None)

        def reset_state(uri: str, version: int | None) -> LspDocument:
            """Reset document state for a new version.

            Always returns a LspDocument: if version isn't an
            integer, warn and keep the document as-is.
            """
            if state := self.documents.get(uri):
                if state.push_diags_timer:
                    state.push_diags_timer.cancel()
                # Clean up stashed items for this document
                for lean_id in state.stashed_items:
                    self.stash.pop(lean_id, None)
                if isinstance(version, int):
                    # Preserve inflight_pulls in streaming mode
                    old_pulls = (
                        state.inflight_pulls
                        if self.opts.stream_diagnostics
                        else {}
                    )
                    # Replace with fresh state, keeping the text mirror
                    state = LspDocument(uri, version, state.text)
                    state.inflight_pulls.update(old_pulls)
                    self.documents[uri] = state
                return state
            state = LspDocument(uri, version if isinstance(version, int) else 0)
            self.documents[uri] = state
            return state

        if method == 'textDocument/didClose':
            uri = params["textDocument"]["uri"]
            close_state(uri)
            await forward_all()
        elif method == 'textDocument/didOpen':
            uri = params["textDocument"]["uri"]
            state = reset_state(uri, params["textDocument"].get("version"))
            state.text = params["textDocument"].get("text", "")
            await forward_all()
            # In streaming mode, pull diagnostics from pull-capable servers
            if self.opts.stream_diagnostics:
                await self._pull_and_stream_diags(uri, state, False)
        elif method == 'textDocument/didChange':
            uri = params["textDocument"]["uri"]
            state = reset_state(uri, params["textDocument"].get("version"))
            await self._forward_did_change(
                state, params.get("contentChanges", [])
            )
            # In streaming mode, pull diagnostics from pull-capable servers
            if self.opts.stream_diagnostics:
                await self._pull_and_stream_diags(uri, state, True)
        elif method == 'textDocument/didSave':
            uri = params["textDocument"]["uri"]
            if (state := self.documents.get(uri)) and (
                (text := params.get('text')) is not None
            ):
                state.text = text

            await forward_all()
        elif method == 'workspace/didChangeWatchedFiles' and (
            changes := params.get("changes")
        ):
            # FIXME: If there are multiple changes, we send all of them to a server
            # even if it only cares about some. Should filter params per server.
            for server, patterns in self.file_watchers.values():
                for change in changes:
                    if (uri := change.get("uri")) and any(
                        _uri_matches_pattern(uri, p) for p in patterns
                    ):
                        await self.notify_server(server, method, params)
                        break
        else:
            await forward_all()

    async def _forward_did_change(
        self, state: LspDocument, content_changes: JSON
    ) -> None:
        """Forward client didChange, translating sync kind per server.

        Full-sync servers get the whole text computed from our mirror;
        incremental servers get ranged changes (the client's verbatim,
        or a diff if the client sent a range-less full change, which
        some incremental servers can't take).
        """
        old_text = state.text
        try:
            new_text = _apply_content_changes(old_text, content_changes)
        except (KeyError, IndexError, TypeError):
            warn(
                f"Malformed content changes for {state.uri}; dropping didChange"
            )
            return
        state.text = new_text

        # state.docver was bumped to this change's version by reset_state
        text_doc = {'uri': state.uri, 'version': state.docver}
        full_params = {
            'textDocument': text_doc,
            'contentChanges': [{'text': new_text}],
        }
        verbatim_params = {
            'textDocument': text_doc,
            'contentChanges': content_changes,
        }
        diff_changes = None

        for server in self.servers.values():
            kind = server.sync_kind
            if kind == 1:
                params = full_params
            elif kind == 2:
                if any('range' not in c for c in content_changes):
                    if diff_changes is None:
                        diff_changes = _diff_changes(old_text, new_text)
                    if not diff_changes:
                        continue
                    params = {
                        'textDocument': text_doc,
                        'contentChanges': diff_changes,
                    }
                else:
                    params = verbatim_params
            else:
                # Unknown sync kind: forward verbatim (historical behavior)
                params = verbatim_params
            await self.notify_server(server, 'textDocument/didChange', params)

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
        if method == 'workspace/configuration' and not is_error:
            items = cast(list, response_payload)
            for i, item in enumerate(items):
                if not isinstance(item, dict) or 'rass' not in item:
                    continue
                rass = item['rass']
                generic = {k: v for k, v in item.items() if k != 'rass'}
                new_item = generic
                if isinstance(rass, dict):
                    for pattern, overlay in rass.items():
                        if re.search(pattern, server.name) and isinstance(
                            overlay, dict
                        ):
                            new_item = dmerge(overlay, generic)
                            break
                items[i] = new_item

    async def on_server_request(
        self, method: str, params: JSON, source: Server
    ) -> DirectResponse | None:
        """
        Handle server requests to the client.

        Returns:
            DirectResponse to send immediately without forwarding, or
            None to forward the request normally
        """
        # Track file watcher registrations
        if method == "client/registerCapability" and (
            registrations := params.get("registrations")
        ):
            for reg in registrations:
                if (
                    reg.get("method") == "workspace/didChangeWatchedFiles"
                    and (reg_id := reg.get("id"))
                    and (opts := reg.get("registerOptions"))
                    and (watchers := opts.get("watchers"))
                ):
                    # Process watchers: expand braces, combine baseUri+pattern
                    expanded_patterns = []
                    for watcher in watchers:
                        expanded_patterns.extend(_process_watcher(watcher))
                    if expanded_patterns:
                        self.file_watchers[reg_id] = (source, expanded_patterns)
        return None

    async def on_server_notification(
        self, method: str, params: JSON, source: Server
    ) -> None:
        """
        Handle server notifications and forward to client.
        """
        # Special handling for diagnostics
        if (
            method == 'textDocument/publishDiagnostics'
            and (uri := params.get('uri'))
            and (state := self.documents.get(uri))
        ):
            diagnostics = params.get('diagnostics', [])
            self._stash_diagnostics_data(diagnostics, source, state)
            _add_source_attribution(diagnostics, source)

            # Check version - drop stale diagnostics
            if (version := params.get('version')) and version != state.docver:
                return

            # In streaming mode, send diagnostics immediately without aggregation
            if self.opts.stream_diagnostics:
                # Add version if not present
                params['token'] = f"{source.name}-{id(source)}"
                if 'version' not in params:
                    params['version'] = state.docver
                await self.notify_client('$/streamDiagnostics', params)
                return

            # Non-streaming mode: aggregation logic
            # Update aggregate with this server's diagnostics
            state.inflight_pushes[id(source)] = diagnostics

            # If already dispatched, decide whether to re-send or drop
            if state.push_dispatched:
                if self.opts.drop_tardy:
                    debug("Dropping tardy diagnostics")
                    return
                else:
                    debug(
                        "Re-sending enhanced aggregation for tardy diagnostics"
                    )
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
        elif (
            method == 'textDocument/publishDiagnostics'
            and self.opts.stream_diagnostics
        ):
            # no 'state' but still want to convert
            params['token'] = f"{source.name}-{id(source)}"
            method = '$/streamDiagnostics'

        # Forward other notifications immediately
        await self.notify_client(method, params)

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
            and (uri := request_params['textDocument']['uri'])
            and (doc_state := self.documents.get(uri))
        ):
            for action in cast(list, payload):
                self._stash_data(action, server, doc_state)
                if (command := action.get("command")) and (
                    command_name := command.get("command")
                    if isinstance(command, dict)
                    else command
                ):
                    self.commands_map[command_name] = server
        elif (
            method == 'textDocument/codeAction'
            and (uri := request_params['textDocument']['uri'])
            and (doc_state := self.documents.get(uri))
        ):
            for action in cast(list, payload):
                self._stash_data(action, server, doc_state)
        elif (
            method == 'textDocument/diagnostics'
            and (uri := request_params['textDocument']['uri'])
            and (doc_state := self.documents.get(uri))
        ):
            self._stash_diagnostics_data(
                payload.get('items', []), server, doc_state
            )
            doc_state.inflight_pulls[id(server)] = cast(
                str | int, payload.get("resultId")
            )
        elif (
            method == 'textDocument/completion'
            and (uri := request_params.get('textDocument', {}).get('uri'))
            and (doc_state := self.documents.get(uri))
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
            caps = payload.get('capabilities', {})
            server.caps = caps.copy() if caps else {}

            # Parse text sync kind for per-server didChange translation
            if sync := caps.get('textDocumentSync'):
                server.sync_kind = (
                    sync.get('change') if isinstance(sync, dict) else sync
                )

            # index the commands of "executeCommandProvider"
            if (p := caps.get("executeCommandProvider")) and (
                cmds := p.get("commands")
            ):
                for c in cmds:
                    self.commands_map[c] = server

            # In streaming mode, remove diagnosticProvider from the merged caps
            # (but keep it in server.caps for our internal use)
            if self.opts.stream_diagnostics and caps:
                caps.pop('diagnosticProvider', None)

    def get_aggregation_timeout_ms(self, method: str | None) -> int:
        """
        Get timeout in milliseconds for this aggregation.
        """
        if method == 'textDocument/publishDiagnostics':
            return 1000
        return 3000

    def process_responses(
        self,
        method: str,
        items: list[PayloadItem],
    ) -> tuple[JSON | list, bool]:
        """
        Aggregate payloads (which may be only one!)
        Returns tuple of (aggregate payload, is_error).
        """

        def reduce_maybe(items, fn, initial):
            """Reduce items, or return single payload directly if only one."""
            if len(items) == 1:
                return items[0].payload
            return reduce(fn, items, initial)

        is_error = False
        # If all responses are errors, return the first error
        if all(item.is_error for item in items):
            res = items[0].payload
            is_error = True

        # Otherwise, skip errors and aggregate successful responses
        items = [item for item in items if (not item.is_error) and item.payload]

        if method in (
            'textDocument/definition',
            'textDocument/typeDefinition',
            'textDocument/implementation',
            'textDocument/declaration',
            'textDocument/references',
        ):
            res = reduce_maybe(
                items,
                lambda acc, item: self._merge_locations(
                    acc, cast(JSON, item.payload), item.server
                ),
                [],
            )

        elif method == 'textDocument/diagnostic':
            all_items = []
            for item in items:
                p = cast(JSON, item.payload)
                diagnostics = p.get('items', [])
                _add_source_attribution(diagnostics, item.server)
                all_items.extend(diagnostics)
            # FIXME: JT@2026-01-05: we elide any 'resultId', which
            # means we're missing out on that optimization.  Not too
            # serious if we can convince the client to support
            # streaming, which should support 'resultId'.
            res = {'items': all_items, 'kind': "full"}

        elif method == 'textDocument/codeAction':
            res = reduce_maybe(
                items,
                lambda acc, item: acc + (cast(list, item.payload) or []),
                [],
            )

        elif method == 'textDocument/completion':

            def normalize(x):
                return x if isinstance(x, dict) else {'items': x}

            # FIXME: Deep merging CompletionList properties is wrong
            # for many fields (e.g., isIncomplete should probably be OR'd)
            res = reduce_maybe(
                items,
                lambda acc, item: dmerge(acc, normalize(item.payload)),
                {},
            )

        elif method == 'initialize':
            res = reduce_maybe(
                items,
                lambda acc, item: self._merge_initialize_payloads(
                    acc, cast(JSON, item.payload), item.server
                ),
                {},
            )
            if is_error:
                return (res, is_error)
            res = cast(JSON, res)

            # In streaming mode, advertise our custom streaming capability
            if self.opts.stream_diagnostics:
                res['capabilities']['$streamingDiagnosticsProvider'] = True

            # Decide the text sync kind advertised to the client (#55).
            # Prefer incremental when any server needs it; didChange is
            # translated per server in _forward_did_change.
            kinds = {s.sync_kind for s in self.servers.values()} - {None, 0}
            if (
                kinds
                and (caps := cast(JSON, res.get('capabilities')))
                and (sync := caps.get('textDocumentSync'))
            ):
                chosen = 2 if 2 in kinds else 1
                caps['textDocumentSync'] = (
                    {**sync, 'change': chosen}
                    if isinstance(sync, dict)
                    else {'change': chosen, 'openClose': True}
                )

        elif method == 'shutdown':
            res = {}

        else:
            res = reduce_maybe(
                items,
                lambda acc, item: dmerge(acc, cast(JSON, item.payload)),
                {},
            )

        return (res, is_error)

    def process_request(
        self, method: str, params: JSON, server: Server
    ) -> JSON | None:
        """Called just before request is forwarded to a specific server.

        Return the params to send to this server, or None for no params."""
        if (
            method == 'textDocument/codeAction'
            and (context := params.get('context'))
            and (diags := context.get('diagnostics'))
        ):
            # TODO: as a further optimization we could use the stashed
            # data prevent that context diagnostics from other sources
            # don't travel as context.
            for d in diags:
                if (
                    (lean_id := d.get('data'))
                    and isinstance(lean_id, int)
                    and (stashed := self.stash.get(lean_id))
                ):
                    _, orig_data, _ = stashed
                    d['data'] = orig_data

        if (
            method == 'initialize'
            and (init_opts := params.get('initializationOptions'))
            and 'rass' in init_opts
        ):
            rass = init_opts['rass']
            generic_opts = {k: v for k, v in init_opts.items() if k != 'rass'}
            new_init_opts = generic_opts
            if isinstance(rass, dict):
                for pattern, overlay in rass.items():
                    if re.search(pattern, server.name) and isinstance(
                        overlay, dict
                    ):
                        new_init_opts = dmerge(overlay, generic_opts)
                        break
            params = {**params, 'initializationOptions': new_init_opts}

        return params

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
            if res.get(cap) is None or (
                is_scalar(res.get(cap)) and not is_scalar(newval)
            ):
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

    def _merge_locations(
        self, aggregate: list[JSON], payload: JSON | list[JSON], source: Server
    ) -> list[JSON]:
        if isinstance(payload, dict):
            payload = [payload]

        def to_location_link(value: JSON) -> JSON | None:
            if "targetUri" in value:
                return value
            # Location -> LocationLink
            elif (uri := value.get('uri')) and (range := value.get('range')):
                return {
                    "targetUri": uri,
                    "targetSelectionRange": range,
                    "targetRange": range,
                }
            else:
                return None

        def location_link_equal(l1: JSON, l2: JSON) -> bool:
            return l1["targetSelectionRange"] == l2["targetSelectionRange"]

        result = []
        for v in payload:
            v = to_location_link(v)
            if v and not any(
                location_link_equal(v, other) for other in aggregate
            ):
                result.append(v)

        return aggregate + result

    def _stash_data(
        self, payload: JSON, server: Server, doc_state: LspDocument
    ):
        """Stash data field with lean identifier.  Mutate payload."""
        # Stash original data (or None) and server, replace with lean id
        original_data = payload.get('data')
        lean_id = id(payload)
        self.stash[lean_id] = (payload, original_data, server)
        payload['data'] = lean_id

        # Track lean_id in document state for cleanup
        doc_state.stashed_items.add(lean_id)

    def _pushdiags_complete(self, state: LspDocument) -> bool:
        """Check if diagnostic aggregation is complete for a document."""
        # Don't send empty aggregations - need at least one push diagnostic
        if not state.inflight_pushes:
            return False
        # Aggregation is complete when union of push diagnostics and inflight pulls covers all servers
        return (
            state.inflight_pushes.keys() | state.inflight_pulls.keys()
        ) == self.servers.keys()

    async def _publish_pushdiags(self, uri: str, state: LspDocument) -> None:
        """Send aggregated diagnostics to the client."""
        state.push_dispatched = True
        if state.push_diags_timer:
            state.push_diags_timer.cancel()

        await self.notify_client(
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

    async def _pull_and_stream_diags(self, orig_uri, state, include_neighbours):
        """Pull from diagnosticProvider servers and push to client.
        uri is the URI that motivated this.
        """

        async def doit(server: Server, uri: str, state: LspDocument):
            is_error, pull_response = await self.request_server(
                server,
                'textDocument/diagnostic',
                {
                    'textDocument': {'uri': uri},
                    'previousResultId': state.inflight_pulls.get(id(server)),
                },
            )

            if is_error:
                if pull_response.get('data', {}).get('retriggerRequest'):
                    await doit(server, uri, state)
            elif pull_response:
                resultId = pull_response.get("resultId")
                state.inflight_pulls[id(server)] = cast(str | int, resultId)
                kind = pull_response.get('kind')
                diagnostics = pull_response.get('items', [])
                # The client keeps a neighbour's diagnostics while its
                # version doesn't change, so an unchanged report would
                # only make it re-report the same diagnostics.
                if kind == 'unchanged' and uri != orig_uri:
                    return
                self._stash_diagnostics_data(diagnostics, server, state)
                _add_source_attribution(diagnostics, server)
                # Send as streamDiagnostics notification
                params = {
                    'uri': uri,
                    'version': state.docver,
                    'token': f"{server.name}-{id(server)}",
                    'kind': kind,
                }
                if diagnostics:
                    params['diagnostics'] = diagnostics
                await self.notify_client('$/streamDiagnostics', params)

        for server in self.servers.values():
            if not (provider := server.caps.get('diagnosticProvider')):
                continue
            # Use as background task to avoid blocking other
            # servers.
            asyncio.create_task(doit(server, orig_uri, state))
            # Neighbours can only change if the server's diagnostics
            # depend on other files.
            inter_file = provider.get('interFileDependencies', True)
            if include_neighbours and inter_file:
                for uri, other in self.documents.items():
                    if uri != orig_uri:
                        asyncio.create_task(doit(server, uri, other))

    def _stash_diagnostics_data(self, diags, source, state):
        for diag in diags:
            self._stash_data(diag, source, state)


def _utf16_offset(s: str, u16_index: int) -> int:
    """Convert a UTF-16 code unit offset to a Python string index.

    LSP positions are UTF-16 code unit offsets (rass forces
    positionEncodings to utf-16); Python indexes by code point."""
    if u16_index <= 0:
        return 0
    if s[:u16_index].isascii():
        # ASCII fast path: offsets coincide
        return min(u16_index, len(s))
    units = 0
    for i, c in enumerate(s):
        if units >= u16_index:
            return i
        units += 2 if ord(c) > 0xFFFF else 1
    return len(s)


def _lsp_position(text: str, pos: JSON) -> int:
    """Python index for an LSP position (UTF-16 line/character).

    Positions beyond the document are clamped to the document end
    (same as VSCode's TextDocument.offsetAt)."""
    line_start = 0
    for _ in range(cast(int, pos['line'])):
        nl = text.find('\n', line_start)
        if nl < 0:
            return len(text)
        line_start = nl + 1
    nl = text.find('\n', line_start)
    line_text = text[line_start:] if nl < 0 else text[line_start:nl]
    return line_start + _utf16_offset(line_text, cast(int, pos['character']))


def _apply_content_changes(text: str, changes: JSON) -> str:
    """Apply LSP didChange contentChanges to text, returning new text.

    Changes are sequential state changes: c1 is computed on the
    original state, c2 on the state after c1, and so on.  A change
    without a 'range' replaces the whole document."""
    for change in cast(list, changes):
        new = change.get('text', '')
        if (r := change.get('range')) is None:
            return new
        start = _lsp_position(text, r['start'])
        end = _lsp_position(text, r['end'])
        text = text[:start] + new + text[end:]
    return text


def _diff_changes(old: str, new: str) -> list[JSON]:
    """Compute line-based ranged contentChanges transforming old into new.

    Ranges are rebased so that applying the changes in order (see
    _apply_content_changes) yields new."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    )
    changes = []
    line_delta = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            continue
        changes.append(
            {
                'range': {
                    'start': {'line': i1 + line_delta, 'character': 0},
                    'end': {'line': i2 + line_delta, 'character': 0},
                },
                'text': ''.join(new_lines[j1:j2]),
            }
        )
        line_delta += (j2 - j1) - (i2 - i1)
    return changes


def _add_source_attribution(diags, server):
    for d in diags:
        if 'source' not in d:
            d['source'] = server.name


def _process_watcher(watcher: JSON) -> list[str]:
    """Process an LSP "watcher" into a list of expanded glob patterns.

    Returns empty list for malformed watchers."""
    glob_pattern = watcher.get("globPattern")
    if not glob_pattern:
        return []  # Malformed watcher

    if isinstance(glob_pattern, str):
        # Simple glob pattern like "**/*.toml" - expand braces
        return expand_braces(glob_pattern)

    elif isinstance(glob_pattern, dict):
        # Relative pattern with baseUri - combine and expand
        base_uri = glob_pattern.get("baseUri")
        pattern = glob_pattern.get("pattern")
        if not base_uri or not pattern:
            return []  # Malformed

        # baseUri can be either a string or a dict with 'uri' and 'name' fields
        if isinstance(base_uri, dict):
            base_uri = base_uri.get("uri")
            if not base_uri:
                return []  # Malformed

        # Parse baseUri to get path
        base_parsed = urlparse(base_uri)
        if base_parsed.scheme != "file":
            return []  # Only support file:// URIs

        base_path = unquote(base_parsed.path)
        # Combine base path with pattern, then expand braces
        expanded = expand_braces(pattern)
        return [f"{base_path}/{p}" for p in expanded]

    return []  # Unknown format


def _uri_matches_pattern(uri: str, pattern: str) -> bool:
    """Check if a URI matches a glob pattern string."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return False

    path = unquote(parsed.path)
    posix_path = PurePosixPath(path)

    try:
        return posix_path.match(pattern)
    except Exception:
        # Pattern matching error - be conservative and forward
        return True
