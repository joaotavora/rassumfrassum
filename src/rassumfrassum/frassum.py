"""
LSP-specific message routing and merging logic.
"""

from dataclasses import dataclass, field
from typing import cast

from .json import JSON
from .util import (
    dmerge,
    is_scalar,
)


@dataclass
class Server:
    """Information about a logical LSP server."""

    name: str
    caps: JSON = field(default_factory=dict)
    cookie: object = None


class LspLogic:
    """Decide on message routing and response aggregation."""

    def __init__(self, servers: list[Server]):
        """Initialize with all servers."""
        self.servers = servers
        # Track document versions: URI -> version number
        self.document_versions: dict[str, dict] = {}
        # Map server ID to server object for data recovery
        self.server_by_id: dict[int, Server] = {id(s): s for s in servers}

    async def on_client_request(
        self, method: str, params: JSON, servers: list[Server]
    ) -> list[Server]:
        """
        Handle client requests and determine who receives it

        Args:
            method: LSP method name
            params: Request parameters
            servers: List of available servers (primary first)

        Returns:
            List of servers that should receive the request
        """
        # Check for data recovery from inline stash
        data = (
            params.get('data')
            if params and method.endswith("resolve")
            else None
        )
        if (
            isinstance(data, dict)
            and (probe := data.get('frassum-server'))
            and (target := self.server_by_id.get(probe))
        ):
            # Replace with original data
            params['data'] = data.get('frassum-data')
            return [target]

        # initialize and shutdown go to all servers
        if method in ['initialize', 'shutdown']:
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

        # Default: route to primary server
        return [self.servers[0]] if servers else []

    async def on_client_notification(self, method: str, params: JSON) -> None:
        """
        Handle client notifications to track document state.
        """
        if method == 'textDocument/didOpen':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            version = text_doc.get('version')
            if uri is not None and version is not None:
                self.document_versions[uri] = {
                    'tracked_version': version,
                    'has_some_diags': False,
                }

        elif method == 'textDocument/didChange':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            version = text_doc.get('version')
            if uri is not None and version is not None:
                self.document_versions[uri] = {
                    'tracked_version': version,
                    'has_some_diags': False,
                }

        elif method == 'textDocument/didClose':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            if uri is not None:
                self.document_versions.pop(uri, None)

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
    ) -> None:
        """
        Handle server requests to the client.
        """
        pass

    async def on_server_notification(
        self, method: str, params: JSON, source: Server
    ) -> None:
        """
        Handle server notifications.
        """
        # Add source attribution to diagnostics
        if method == 'textDocument/publishDiagnostics':
            for diag in params.get('diagnostics', []):
                if 'source' not in diag:
                    diag['source'] = source.name

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
        if method == 'textDocument/codeAction':
            for action in cast(list, payload):
                self._stash_data_maybe(action, server)

        # Stash data fields in completion responses
        if method == 'textDocument/completion':
            items = (
                payload
                if isinstance(payload, list)
                else payload.get('items', [])
            )
            for item in cast(list, items):
                self._stash_data_maybe(item, server)

        # Extract server name and capabilities from initialize response
        if method == 'initialize':
            if 'name' in payload.get('serverInfo', {}):
                server.name = payload['serverInfo']['name']
            caps = payload.get('capabilities')
            server.caps = caps.copy() if caps else {}

    def get_notif_aggregation_key(
        self, method: str | None, payload: JSON
    ) -> tuple[tuple, bool] | str | None:
        """
        Get aggregation info for notifications that need aggregation.
        Returns None if this notification doesn't need aggregation.
        Returns "drop" if message should be dropped (stale version).
        """
        if method == 'textDocument/publishDiagnostics':
            if (uri := payload.get('uri')) and (
                probe := self.document_versions.get(uri)
            ):
                tracked_version = probe["tracked_version"]
                version = payload.get('version')
                if version is None:
                    version = tracked_version
                elif version != tracked_version:
                    return "drop"
                had_diags = probe["has_some_diags"]
                probe["has_some_diags"] = True
                return (('notification', method, uri), not had_diags)

        return None

    def get_aggregation_timeout_ms(self, method: str | None) -> int:
        """
        Get timeout in milliseconds for this aggregation.
        """
        if method == 'textDocument/publishDiagnostics':
            return 1000

        # Default for responses
        return 1500

    def aggregate_payloads(
        self,
        method: str,
        payload_tuples: list[tuple[JSON | list, Server, bool]],
    ) -> JSON | list:
        """
        Aggregate payloads.
        Returns the new aggregate payload.
        """

        # FIXME, it's not correct to skip all errors.  If _all_ are
        # errors, I think we should do something about it.
        payload_tuples = [p for p in payload_tuples if not p[2]]
        if method == 'textDocument/publishDiagnostics':
            aggregate = {}
            for p, source, _ in payload_tuples:
                p = cast(JSON, p)
                diags = p.get('diagnostics', [])
                for diag in diags:
                    if 'source' not in diag:
                        diag['source'] = source.name
                aggregate = dmerge(aggregate, p)
            return aggregate
        elif method == 'textDocument/codeAction':
            res = []
            for p, _, _ in payload_tuples:
                res += p
            return res
        elif method == 'textDocument/completion':
            res = {}

            def normalize(x):
                return x if isinstance(x, dict) else {'items': x}

            # FIXME: Deep merging CompletionList properties is wrong
            # for many fields (e.g., isIncomplete should probably be
            # OR'd)
            for p, _, _ in payload_tuples:
                res = dmerge(res, normalize(p))
            return res
        elif method == 'initialize':
            # Merge capabilities
            res = {}
            for p, source, _ in payload_tuples:
                p = cast(JSON, p)
                res = self._merge_initialize_payloads(res, p, source)
            return res
        elif method == 'shutdown':
            # Shutdown returns null, just return current aggregate
            return {}
        else:
            # Default: do some generic mergin (could use 'reduce')
            res = {}
            for p, _, _ in payload_tuples:
                res = dmerge(res, cast(JSON, p))
            return res

    def _merge_initialize_payloads(
        self, aggregate: JSON, payload: JSON, source: Server
    ) -> JSON:
        """Merge initialize response payloads (result objects)."""

        # Determine if this response is from primary
        primary_payload = source == self.servers[0]

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

    def _stash_data_maybe(self, payload: JSON, server: Server):
        """Stash data field with server ID inline."""
        # FIXME: investigate why payload can be None
        if not payload or 'data' not in payload:
            return
        # Replace data with inline dict containing server ID and original data
        original_data = payload['data']
        payload['data'] = {
            'frassum-server': id(server),
            'frassum-data': original_data,
        }
