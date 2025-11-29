"""
LSP-specific message routing adn merging logic.
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

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        return method in ['initialize', 'shutdown']

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
            new_diags = payload.get('diagnostics', []);

            # Add source to new diagnostics
            for diag in new_diags:
                if 'source' not in diag:
                    diag['source'] = source.name

            # Combine diagnostics
            result = aggregate.copy()
            result['diagnostics'] = current_diags + new_diags
            return result
        elif method == 'initialize':
            # Merge capabilities
            return await self._merge_initialize_payloads(aggregate, payload, source)
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
        result = aggregate.copy()
        current_caps = result.get('capabilities', {})
        new_caps = payload.get('capabilities', {})
        current_info = result.get('serverInfo', {})
        new_info = payload.get('serverInfo', {})

        # Determine which response is from primary
        current_is_primary = current_info.get('name') == self.primary_server.name
        new_is_primary = source == self.primary_server

        # Start with primary server's capabilities
        if new_is_primary:
            merged_caps = new_caps.copy()
        elif current_is_primary:
            merged_caps = current_caps.copy()
        else:
            # Neither is primary (shouldn't happen in 2-server case)
            merged_caps = current_caps.copy()

        # Special handling for textDocumentSync
        if 'textDocumentSync' in current_caps or 'textDocumentSync' in new_caps:
            current_sync = current_caps.get('textDocumentSync')
            new_sync = new_caps.get('textDocumentSync')

            # If either is the number 1, that wins
            if current_sync == 1 or new_sync == 1:
                merged_caps['textDocumentSync'] = 1
            # Otherwise use primary's value (already set above)

        result['capabilities'] = merged_caps

        # Merge serverInfo
        current_info = result.get('serverInfo', {})
        new_info = payload.get('serverInfo', {})

        if new_info:
            def merge_field(field: str, sep: str) -> str:
                current = current_info.get(field, '')
                new = new_info.get(field, '')

                if not (current and new):
                    return new or current

                # Check if we need to swap to ensure primary comes first
                current_is_primary = current_info.get('name') == self.primary_server.name
                new_is_primary = source == self.primary_server

                # If new is primary but current isn't, swap order
                if new_is_primary and not current_is_primary:
                    return f"{new}{sep}{current}"
                else:
                    return f"{current}{sep}{new}"

            result['serverInfo'] = {
                'name': merge_field('name', '+'),
                'version': merge_field('version', ',')
            }

        return result
