"""
LSP-specific message routing and merging logic.
"""

import asyncio
from typing import Any
from jsonrpc import JSON
from server_process import ServerProcess

class MessageRouter:
    """
    Routes LSP messages between client and multiple servers.
    Handles request routing and response merging.
    """

    def __init__(self, server_names: list[str]):
        """
        Initialize router with server names.
        First server is primary, rest are secondary.
        """
        self.server_names : list[str] = server_names
        self.primary_name : str = server_names[0]
        self.secondary_names : list[str] = server_names[1:] if len(server_names) > 1 else []

        # Track requests that need response merging
        # message_key -> {method: str, messages: {server_name: message}, expected_count: int}
        self.pending_aggregations : dict[Any, dict[str, Any]]= {}  # pyright: ignore[reportExplicitAny]

        # For notifications without IDs, we generate transient keys
        self.notification_key_counter = 0

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        return method in ['initialize', 'shutdown']

    def is_notification(self, msg: JSON) -> bool:
        """Check if message is a notification (no 'id' field)."""
        return 'id' not in msg

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

        # Merge capabilities
        for key, value in new_caps.items():
            if key not in current_caps:
                current_caps[key] = value
            elif isinstance(value, dict) and isinstance(current_caps[key], dict):
                current_caps[key] = {**current_caps[key], **value}
            elif isinstance(value, list) and isinstance(current_caps[key], list):
                current_caps[key] = list(set(current_caps[key] + value))

        return result
