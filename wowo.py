"""
LSP-specific message routing and merging logic.
"""

import asyncio
from dataclasses import dataclass
from jsonrpc import JSON


@dataclass
class Server:
    """Information about a running server subprocess."""
    name: str
    process: asyncio.subprocess.Process
    capabilities: JSON | None = None

    @property
    def stdin(self) -> asyncio.StreamWriter:
        return self.process.stdin  # pyright: ignore[reportReturnType]

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self.process.stdout  # pyright: ignore[reportReturnType]

    @property
    def stderr(self) -> asyncio.StreamReader:
        return self.process.stderr  # pyright: ignore[reportReturnType]

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

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        return method in ['initialize', 'shutdown']

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
            server.capabilities = response_payload.get('capabilities')

        return response_payload

    def get_aggregation_key(self, method: str | None, payload: JSON) -> tuple | None:
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
        return 5000  # 5 seconds

    async def aggregate_payloads(
        self,
        method: str,
        aggregate: JSON,
        payload: JSON,
        source: Server
    ) -> JSON:
        """
        Aggregate a new payload with the current aggregate.
        Returns the new aggregate payload.
        """
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
        elif method == 'initialize':
            # Merge capabilities
            return await self._merge_initialize_payloads(
                aggregate, payload, source)
        elif method == 'shutdown':
            # Shutdown returns null, just return current aggregate
            return aggregate
        else:
            # Default: return current aggregate
            return aggregate

    async def _merge_initialize_payloads(
        self,
        aggregate: JSON,
        payload: JSON,
        source: Server
    ) -> JSON:
        """Merge initialize response payloads (result objects)."""

        # Determine if this response is from primary
        primary_payload = source == self.primary_server

        # Merge capabilities.  Be very naive and almost always use the
        # primary server's capabilities
        current_caps = aggregate.get('capabilities', {})
        new_caps = payload.get('capabilities', {})
        merged_caps = new_caps if primary_payload else current_caps

        # Merge textDocumentSync capability.  If one server only
        # supports full text, then be it  ¯\_(ツ)_/¯
        if 'textDocumentSync' in current_caps or 'textDocumentSync' in new_caps:
            current_sync = current_caps.get('textDocumentSync')
            new_sync = new_caps.get('textDocumentSync')
            if current_sync == 1 or new_sync == 1:
                merged_caps['textDocumentSync'] = 1

        aggregate['capabilities'] = merged_caps

        # Merge serverInfo
        s_info = payload.get('serverInfo', {})
        if s_info:
            def merge_field(field: str, s: str) -> str:
                current_info = aggregate.get('serverInfo', {})
                cur = current_info.get(field, '')
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
