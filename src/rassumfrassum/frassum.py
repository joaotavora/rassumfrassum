"""
LSP-specific message routing and merging logic.
"""

from dataclasses import dataclass, field
from .jaja import JSON
from typing import cast
from .lolo import log  # pyright: ignore[reportUnusedImport]  # noqa: F401


@dataclass
class Server:
    """Information about a logical LSP server."""

    name: str
    capabilities: JSON = field(default_factory=dict)
    cookie: object = None


@dataclass
class DataCookie:
    """Data associated with a server."""

    data: JSON
    server: Server


class LspLogic:
    """Decide on message routing and response aggregation."""

    def __init__(self, primary_server: Server):
        """Initialize with reference to the primary server."""
        self.primary_server = primary_server
        # Track document versions: URI -> version number
        self.document_versions: dict[str, int] = {}
        # Track data cookies: key -> DataCookie
        self.data_cookies: dict[str, DataCookie] = {}
        # Counter for generating unique data cookie IDs
        self._data_cookie_counter: int = 0

    def servers_to_route_to(
        self, method: str, params: JSON, servers: list[Server]
    ) -> list[Server]:
        """
        Determine which servers should receive this request.

        Args:
            method: LSP method name
            params: Request parameters
            servers: List of available servers (primary first)

        Returns:
            List of servers that should receive the request
        """
        # Check for data cookie recovery
        data = params.get('data') if params else None
        if isinstance(data, str) and data.startswith('rassumfrassum-'):
            # This is a cookie ID - recover the original data
            if data in self.data_cookies:
                cookie = self.data_cookies[data]
                # Replace cookie ID with original data
                params['data'] = cookie.data
                # Route only to the server that sent this data
                return [cookie.server]

        # initialize and shutdown go to all servers
        if method in ['initialize', 'shutdown']:
            return servers

        # Route requests to _all_ servers supporting this
        if method == 'textDocument/codeAction':
            return [
                s for s in servers if s.capabilities.get('codeActionProvider')
            ]

        # Route requests to _first_ server supporting this capability
        if cap := {
            'textDocument/rename': 'renameProvider',
            'textDocument/formatting': 'documentFormattingProvider',
            'textDocument/rangeFormatting': 'documentRangeFormattingProvider',
        }.get(method):
            for s in servers:
                if s.capabilities.get(cap):
                    return [s]
            return []

        # Default: route to primary server
        return [self.primary_server] if servers else []

    def on_client_request(self, method: str, params: JSON) -> None:
        """
        Handle client requests to servers.  May modify params.
        """
        pass

    def on_client_notification(self, method: str, params: JSON) -> None:
        """
        Handle client notifications to track document state.
        """
        if method == 'textDocument/didOpen':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            version = text_doc.get('version')
            if uri is not None and version is not None:
                self.document_versions[uri] = version

        elif method == 'textDocument/didChange':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            version = text_doc.get('version')
            if uri is not None and version is not None:
                self.document_versions[uri] = version

        elif method == 'textDocument/didClose':
            text_doc = params.get('textDocument', {})
            uri = text_doc.get('uri')
            if uri is not None:
                self.document_versions.pop(uri, None)

    def on_client_response(
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

    def on_server_request(
        self, method: str, params: JSON, source: Server
    ) -> None:
        """
        Handle server requests to the client.
        """
        pass

    def _stash_data_maybe(self, payload: JSON, server: Server):
        """Stash data field behind a cookie ID, replacing it in the payload."""
        # FIXME: investigate why payload can be None
        if not payload or 'data' not in payload:
            return
        # Generate unique ID
        self._data_cookie_counter += 1
        cookie_id = f"rassumfrassum-{self._data_cookie_counter}"
        # Store original data
        self.data_cookies[cookie_id] = DataCookie(
            data=payload['data'],
            server=server
        )
        # Replace data with cookie ID
        payload['data'] = cookie_id


    def on_server_notification(
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

    def on_server_response(
        self,
        method: str | None,
        request_params: JSON,
        response_payload: JSON,
        is_error: bool,
        server: Server,
    ) -> None:
        """
        Handle server responses.
        Returns the (potentially modified) response_payload.
        """
        # Stash data fields in codeAction responses
        if method == 'textDocument/codeAction' and not is_error:
            for action in cast(list, response_payload):
                self._stash_data_maybe(action, server)

        # Extract server name and capabilities from initialize response
        if method == 'initialize' and not is_error:
            if 'name' in response_payload.get('serverInfo', {}):
                server.name = response_payload['serverInfo']['name']
            caps = response_payload.get('capabilities')
            server.capabilities = caps.copy() if caps else {}

    def get_notif_aggregation_key(
        self, method: str | None, payload: JSON
    ) -> tuple | None:
        """
        Get aggregation key for notifications that need aggregation.
        Returns None if this notification doesn't need aggregation.
        Returns ("drop",) if message should be dropped (stale version).
        """
        if method == 'textDocument/publishDiagnostics':
            uri = payload.get('uri', '')
            version = payload.get('version')

            if uri in self.document_versions:
                tracked_version = self.document_versions[uri]
                if version is None:
                    version = tracked_version
                elif version < tracked_version:
                    return ("drop",)

            return ('notification', method, uri, version or 0)

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
        aggregate: JSON | list,
        payload: JSON,
        source: Server,
        is_error: bool,
    ) -> JSON | list:
        """
        Aggregate a new payload with the current aggregate.
        Returns the new aggregate payload.
        """
        # Don't aggregate error responses, just skip them
        if is_error:
            return aggregate
        if method == 'textDocument/publishDiagnostics':
            # Merge diagnostics
            aggregate = cast(JSON, aggregate)
            current_diags = aggregate.get('diagnostics', [])
            new_diags = payload.get('diagnostics', [])

            # Add source to new diagnostics
            for diag in new_diags:
                if 'source' not in diag:
                    diag['source'] = source.name

            # Combine diagnostics
            aggregate['diagnostics'] = current_diags + new_diags
            return aggregate
        elif method == 'textDocument/codeAction':
            # Merge code actions - just concatenate
            return (cast(list, aggregate) or []) + (cast(list, payload) or [])
        elif method == 'initialize':
            # Merge capabilities
            aggregate = cast(JSON, aggregate)
            return self._merge_initialize_payloads(aggregate, payload, source)
        elif method == 'shutdown':
            # Shutdown returns null, just return current aggregate
            return aggregate
        else:
            # Default: return current aggregate
            return aggregate

    def _merge_initialize_payloads(
        self, aggregate: JSON, payload: JSON, source: Server
    ) -> JSON:
        """Merge initialize response payloads (result objects)."""

        # Determine if this response is from primary
        primary_payload = source == self.primary_server

        # Merge capabilities by iterating through all keys
        merged_caps = aggregate.get('capabilities', {})
        new_caps = payload.get('capabilities', {})

        for cap_name, cap_value in new_caps.items():
            if cap_name == 'textDocumentSync':

                def t1sync(x):
                    return x == 1 or (
                        isinstance(x, dict) and x.get("change") == 1
                    )

                current_sync = merged_caps.get('textDocumentSync')
                if not t1sync(current_sync) and t1sync(cap_value):
                    merged_caps['textDocumentSync'] = cap_value
            elif (
                cap_name in {'renameProvider', 'codeActionProvider'}
                or primary_payload
                or merged_caps.get(cap_name) is None
            ):
                # FIXME: this "generic merging" logic is still quite
                # dumb.
                current = merged_caps.get(cap_name)
                if isinstance(current, bool) and cap_value:
                    merged_caps[cap_name] = cap_value
                    continue

                # If new_value is a boolean, handle it simply
                if not isinstance(cap_value, dict):
                    current = merged_caps.get(cap_name)
                    if not isinstance(current, dict):
                        merged_caps[cap_name] = cap_value
                    continue

                # new_value is a dict, proceed with deep merge
                merged_caps.setdefault(cap_name, {})
                current = merged_caps.get(cap_name)
                for key, value in cap_value.items():
                    if key not in current:
                        current[key] = value
                    elif isinstance(value, bool) and isinstance(
                        current[key], bool
                    ):
                        current[key] = value or current[key]
                    else:
                        current[key] = value

        aggregate['capabilities'] = merged_caps

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
