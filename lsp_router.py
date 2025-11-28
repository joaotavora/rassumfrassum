"""
LSP-specific message routing and merging logic.
"""

import asyncio
from typing import Any
from jsonrpc import JSON

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

    def on_server_message(self, server, msg: JSON) -> None:
        """
        Handle immediate processing of server message.
        Can perform side effects like updating server.name.
        """
        # Extract server name from initialize response
        if 'result' in msg:
            result = msg.get('result')
            if isinstance(result, dict):
                server_info = result.get('serverInfo', {})
                if 'name' in server_info:
                    server.name = server_info['name']

    def should_aggregate(self, msg: JSON) -> bool:
        """
        Check if this message needs aggregation from multiple servers.
        Works for both responses and notifications.
        """
        # Responses: check if it's a pending merge
        msg_id = msg.get('id')
        if msg_id is not None and 'result' in msg:
            return msg_id in self.pending_aggregations

        # Notifications: check method
        method = msg.get('method')
        if method:
            return method == 'textDocument/publishDiagnostics'

        return False

    async def aggregate_message(self, server_name: str, msg: JSON) -> tuple[bool, JSON | None]:
        """
        Add a message to aggregation.
        Returns (is_complete, aggregated_message).
        If is_complete is True, all messages received and aggregated_message is ready.
        """
        # Get or create aggregation key
        msg_id = msg.get('id')
        method = msg.get('method')

        if msg_id is not None:
            # Response: use ID as key
            key = msg_id
        elif method:
            # Notification: use method + params as key
            # For publishDiagnostics, use URI from params
            if method == 'textDocument/publishDiagnostics':
                params = msg.get('params', {})
                uri = params.get('uri', '')
                key = f"notif:{method}:{uri}"
            else:
                key = f"notif:{method}"
        else:
            return (False, None)

        # For notifications, create tracking entry if this is the first one
        if key not in self.pending_aggregations and method:
            self.pending_aggregations[key] = {
                'method': method,
                'messages': {},
                'expected_count': len(self.server_names)
            }

        if key not in self.pending_aggregations:
            return (False, None)

        agg_state = self.pending_aggregations[key]
        agg_state['messages'][server_name] = msg

        # Check if all messages collected
        if len(agg_state['messages']) == agg_state['expected_count']:
            method = agg_state['method']
            aggregated = await self._aggregate_messages(method, agg_state['messages'])
            del self.pending_aggregations[key]
            return (True, aggregated)

        return (False, None)

    def track_merge_request(self, request_id: int, method: str, server_count: int) -> None:
        """Start tracking a request that needs response merging."""
        self.pending_aggregations[request_id] = {
            'method': method,
            'messages': {},
            'expected_count': server_count
        }

    def is_pending_merge(self, request_id: int) -> bool:
        """Check if a request ID is pending merge."""
        return request_id in self.pending_aggregations

    async def add_response(self, request_id: int, server_name: str, response: JSON) -> tuple[bool, JSON | None]:
        """
        Add a server response to pending merge.
        Returns (is_complete, merged_response).
        If is_complete is True, all responses received and merged_response is ready.
        """
        if request_id not in self.pending_aggregations:
            return (False, None)

        merge_state = self.pending_aggregations[request_id]
        merge_state['messages'][server_name] = response

        # Check if all messages collected
        if len(merge_state['messages']) == merge_state['expected_count']:
            method = merge_state['method']
            merged = await self._aggregate_messages(method, merge_state['messages'])
            del self.pending_aggregations[request_id]
            return (True, merged)

        return (False, None)

    async def _aggregate_messages(self, method: str, messages: dict[str, dict]) -> dict:
        """Aggregate messages based on method type."""
        if method == 'initialize':
            return await merge_initialize_responses(messages)
        elif method == 'shutdown':
            # Shutdown returns null, just take first response
            return next(iter(messages.values()))
        elif method == 'textDocument/publishDiagnostics':
            # Aggregate diagnostics from all servers
            return await aggregate_diagnostics(messages)
        else:
            # Default: take primary's response (shouldn't reach here)
            return next(iter(messages.values()))


async def merge_initialize_responses(responses: dict[str, dict]) -> dict:
    """
    Merge initialize responses from multiple servers.
    Combines capabilities from all servers.
    """
    if not responses:
        raise ValueError("No responses to merge")

    # Start with primary's response as base
    primary_response = None
    for server_name, response in responses.items():
        if 'basedpyright' in server_name.lower() or 'pyright' in server_name.lower():
            primary_response = response
            break

    if primary_response is None:
        # Fallback to first response
        primary_response = next(iter(responses.values()))

    merged = primary_response.copy()

    # Get the capabilities object
    if 'result' not in merged or 'capabilities' not in merged['result']:
        return merged

    merged_caps = merged['result']['capabilities']

    # Merge capabilities from other servers
    for server_name, response in responses.items():
        if response == primary_response:
            continue

        if 'result' not in response or 'capabilities' not in response['result']:
            continue

        other_caps = response['result']['capabilities']

        # Merge by taking union of capabilities
        # For simple boolean/object fields, prefer having them
        for key, value in other_caps.items():
            if key not in merged_caps:
                merged_caps[key] = value
            elif isinstance(value, dict) and isinstance(merged_caps[key], dict):
                # Merge nested dicts (like codeActionProvider)
                merged_caps[key] = {**merged_caps[key], **value}
            elif isinstance(value, list) and isinstance(merged_caps[key], list):
                # Merge lists (like codeActionKinds)
                merged_caps[key] = list(set(merged_caps[key] + value))

    return merged


async def aggregate_diagnostics(notifications: dict[str, dict]) -> dict:
    """
    Aggregate textDocument/publishDiagnostics notifications from multiple servers.
    Merges diagnostics for the same URI.
    """
    if not notifications:
        return {}

    # Take first notification as base
    base_notification = next(iter(notifications.values())).copy()

    # Get the URI from params
    base_params = base_notification.get('params', {})
    uri = base_params.get('uri', '')

    # Collect all diagnostics from all servers
    all_diagnostics = []
    for server_name, notification in notifications.items():
        params = notification.get('params', {})
        diags = params.get('diagnostics', [])

        # Add source field to each diagnostic
        for diag in diags:
            if 'source' not in diag:
                diag['source'] = server_name
        all_diagnostics.extend(diags)

    # Update base notification with merged diagnostics
    base_notification['params'] = {
        'uri': uri,
        'diagnostics': all_diagnostics
    }

    return base_notification


class DiagnosticAggregator:
    """
    Aggregates diagnostics from multiple servers with timeout.
    """

    def __init__(self, timeout_ms: int = 1000):
        self.timeout_ms = timeout_ms
        self.pending = {}  # uri -> {server_name: diagnostics}
        self.tasks = {}  # uri -> asyncio.Task

    async def add_diagnostic(
        self,
        uri: str,
        server_name: str,
        diagnostics: list[JSON],
        callback
    ):
        """
        Add diagnostics from a server.
        Starts timer on first diagnostic, sends merged result on timeout or when all received.
        """
        if uri not in self.pending:
            self.pending[uri] = {}
            # Start timeout timer
            self.tasks[uri] = asyncio.create_task(
                self._timeout_and_send(uri, callback)
            )

        self.pending[uri][server_name] = diagnostics

        # TODO: If we receive from all servers, cancel timer and send immediately

    async def _timeout_and_send(self, uri: str, callback):
        """Wait for timeout, then send merged diagnostics."""
        await asyncio.sleep(self.timeout_ms / 1000.0)

        if uri in self.pending:
            merged = self._merge_diagnostics(uri)
            await callback(uri, merged)

            # Clean up
            del self.pending[uri]
            if uri in self.tasks:
                del self.tasks[uri]

    def _merge_diagnostics(self, uri: str) -> list:
        """Merge diagnostics from all servers for a given URI."""
        if uri not in self.pending:
            return []

        # Simply concatenate all diagnostics
        all_diagnostics = []
        for server_name, diags in self.pending[uri].items():
            # Could add 'source' field to identify which server
            for diag in diags:
                if 'source' not in diag:
                    diag['source'] = server_name
            all_diagnostics.extend(diags)

        return all_diagnostics
