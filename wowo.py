"""
LSP-specific message routing and merging logic.
"""

import asyncio # because reasons
from dataclasses import dataclass
from jaja import JSON
from typing import cast


@dataclass
class Server:
    """Information about a logical LSP server."""
    name: str
    capabilities: JSON | None = None

class LspLogic:
    """
    Routes LSP messages between client and multiple servers.
    Handles request routing and response merging.
    """

    def __init__(self, primary_server: Server):
        """Initialize with reference to the primary server."""
        self.primary_server = primary_server
        # Track document versions: URI -> version number
        self.document_versions: dict[str, int] = {}

    def should_route_to_server(
        self,
        method: str,
        params: JSON,
        server: Server
    ) -> bool | str:
        """
        Determine if a request should be routed to this server.

        Returns:
            True: Route to this server, continue asking remaining servers
            False: Don't route to this server, continue asking remaining servers
            "stop": Route to this server, STOP asking remaining servers

        Servers are queried in order (primary first).
        """
        # initialize and shutdown go to all servers
        if method in ['initialize', 'shutdown']:
            return True

        # Route textDocument/codeAction to every server with codeActionProvider
        if method == 'textDocument/codeAction':
            caps = server.capabilities or {}
            return True if caps.get('codeActionProvider') else False

        # Route textDocument/rename to first server with renameProvider
        if method == 'textDocument/rename':
            caps = server.capabilities or {}
            return "stop" if caps.get('renameProvider') else False

        # Default: only primary server handles requests
        return server == self.primary_server and "stop"

    def on_client_request(self, method: str, params: JSON) -> None:
        """
        Handle client requests to servers.
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
        server: Server
    ) -> None:
        """
        Handle client responses to server requests.
        """
        pass

    def on_server_request(
        self,
        method: str,
        params: JSON,
        source: Server
    ) -> None:
        """
        Handle server requests to the client.
        """
        pass

    def on_server_notification(
        self,
        method: str,
        params: JSON,
        source: Server
    ) -> JSON:
        """
        Handle server notifications.
        Returns the (potentially modified) params.
        """
        # Add source attribution to diagnostics
        if method == 'textDocument/publishDiagnostics':
            result = params.copy()
            for diag in result.get('diagnostics', []):
                if 'source' not in diag:
                    diag['source'] = source.name
            return result

        return params

    def on_server_response(
        self,
        method: str | None,
        request_params: JSON,
        response_payload: JSON,
        is_error: bool,
        server: Server
    ) -> JSON:
        """
        Handle server responses.
        Returns the (potentially modified) response_payload.
        """
        # Extract server name and capabilities from initialize response
        if method == 'initialize' and not is_error:
            if 'name' in response_payload.get('serverInfo', {}):
                server.name = response_payload['serverInfo']['name']
            caps = response_payload.get('capabilities')
            server.capabilities = caps.copy() if caps else None

        return response_payload

    def get_notif_aggregation_key(self, method: str | None, payload: JSON) -> tuple | None:
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
            return 1000  # 1 second for diagnostics

        # Default for responses
        return 2000  # 2 seconds

    def aggregate_payloads(
        self,
        method: str,
        aggregate: JSON,
        payload: JSON,
        source: Server,
        is_error: bool
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
            return self._merge_initialize_payloads(
                aggregate, payload, source)
        elif method == 'shutdown':
            # Shutdown returns null, just return current aggregate
            return aggregate
        else:
            # Default: return current aggregate
            return aggregate

    def _merge_initialize_payloads(
        self,
        aggregate: JSON,
        payload: JSON,
        source: Server
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
                    return x == 1 or (isinstance(x, dict) and
                                      x.get("change") == 1)
                current_sync = merged_caps.get('textDocumentSync')
                if not t1sync(current_sync) and t1sync(cap_value):
                    merged_caps['textDocumentSync'] = cap_value
            elif cap_name in {'renameProvider', 'codeActionProvider'}:
                merged_caps[cap_name] = new_caps[cap_name]
            elif primary_payload:
                merged_caps[cap_name] = new_caps[cap_name]

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
                'version': merge_field('version', ',')
            }
        # Return the mutated aggregate
        return aggregate
