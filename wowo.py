"""
LSP-specific message routing and merging logic.
"""

from jsonrpc import JSON
from server_process import ServerProcess

class LspLogic:
    """
    Routes LSP messages between client and multiple servers.
    Handles request routing and response merging.
    """

    def __init__(self, primary_server: ServerProcess):
        """Initialize with reference to the primary server."""
        self.primary_server = primary_server
        # Track document versions: URI -> version number
        self.document_versions: dict[str, int] = {}

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        return method in ['initialize', 'shutdown']

    def on_client_notification(self, method: str, params: JSON) -> None:
        """
        Handle client notifications to track document state.
        Updates document version tracking for didOpen, didChange, and didClose.
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

    def on_server_message(
        self,
        method: str | None,
        payload: JSON,
        source: ServerProcess
    ) -> JSON:
        """
        Handle immediate processing of server message payload.
        Can perform side effects like updating source.name.
        Returns the (potentially modified) payload.
        """
        # Extract server name from initialize response
        if method == 'initialize' and 'name' in payload.get('serverInfo', {}):
            source.name = payload['serverInfo']['name']

        # Add source attribution to diagnostics
        if method == 'textDocument/publishDiagnostics':
            result = payload.copy()
            for diag in result.get('diagnostics', []):
                if 'source' not in diag:
                    diag['source'] = source.name
            return result

        return payload

    def should_aggregate(self, method: str | None) -> bool:
        """
        Check if this notification needs aggregation from multiple servers.
        """
        return method == 'textDocument/publishDiagnostics'

    def get_aggregation_key(self, method: str | None, payload: JSON) -> tuple:
        """
        Get a unique key identifying this aggregation session for a notification.
        """
        if method == 'textDocument/publishDiagnostics':
            # Notification: use method + URI
            uri = payload.get('uri', '')
            return ('notification', method, uri)

        return ('notification', method)

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
        source: ServerProcess
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
        source: ServerProcess
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
            probe = new_caps.get('textDocumentSync')
            if probe and probe == 1:
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
