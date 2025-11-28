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

    def should_aggregate(self, msg: JSON) -> bool:
        """
        Check if this message (notification) needs aggregation from multiple servers.
        For responses, aggregation is tracked by lspylex when the request is sent out.
        """
        method = msg.get('method')

        # Notifications that need aggregation
        if method:
            return method == 'textDocument/publishDiagnostics'

        return False

    def get_aggregation_key(self, msg: JSON):
        """
        Get a unique key identifying this aggregation session.
        """
        msg_id = msg.get('id')
        if msg_id is not None:
            # Response: use ID as key
            return ('response', msg_id)

        method = msg.get('method')
        if method == 'textDocument/publishDiagnostics':
            # Notification: use method + URI
            params = msg.get('params', {})
            uri = params.get('uri', '')
            return ('notification', method, uri)

        return None

    def get_aggregation_timeout_ms(self, msg: JSON) -> int:
        """
        Get timeout in milliseconds for this aggregation.
        """
        method = msg.get('method')
        if method == 'textDocument/publishDiagnostics':
            return 1000  # 1 second for diagnostics

        # Responses to requests
        if msg.get('id') is not None:
            return 5000  # 5 seconds for responses

        return 1000  # Default

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

    async def aggregate_message(self, server, msg: JSON) -> tuple[bool, JSON | None]:
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
        agg_state['messages'][id(server)] = (server, msg)

        # Check if all messages collected
        if len(agg_state['messages']) == agg_state['expected_count']:
            method = agg_state['method']
            # Convert to dict[server, msg] for aggregation functions
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

    async def add_response(self, request_id: int, server, response: JSON) -> tuple[bool, JSON | None]:
        """
        Add a server response to pending merge.
        Returns (is_complete, merged_response).
        If is_complete is True, all responses received and merged_response is ready.
        """
        if request_id not in self.pending_aggregations:
            return (False, None)

        merge_state = self.pending_aggregations[request_id]
        merge_state['messages'][id(server)] = (server, response)

        # Check if all messages collected
        if len(merge_state['messages']) == merge_state['expected_count']:
            method = merge_state['method']
            merged = await self._aggregate_messages(method, merge_state['messages'])
            del self.pending_aggregations[request_id]
            return (True, merged)

        return (False, None)

    async def _aggregate_messages(self, method: str, messages: dict) -> dict:
        """Aggregate messages based on method type.
        messages is dict[id(server), (server, msg)]
        """
        if method == 'initialize':
            return await merge_initialize_responses(messages)
        elif method == 'shutdown':
            # Shutdown returns null, just take first response
            _, msg = next(iter(messages.values()))
            return msg
        elif method == 'textDocument/publishDiagnostics':
            # Aggregate diagnostics from all servers
            return await aggregate_diagnostics(messages)
        else:
            # Default: take primary's response (shouldn't reach here)
            _, msg = next(iter(messages.values()))
            return msg


async def merge_initialize_responses(responses: dict) -> dict:
    """
    Merge initialize responses from multiple servers.
    Combines capabilities from all servers.
    responses is dict[id(server), (server, msg)]
    """
    if not responses:
        raise ValueError("No responses to merge")

    # Start with primary's response as base
    primary_response = None
    for server, response in responses.values():
        if 'basedpyright' in server.name.lower() or 'pyright' in server.name.lower():
            primary_response = response
            break

    if primary_response is None:
        # Fallback to first response
        _, primary_response = next(iter(responses.values()))

    merged = primary_response.copy()

    # Get the capabilities object
    if 'result' not in merged or 'capabilities' not in merged['result']:
        return merged

    merged_caps = merged['result']['capabilities']

    # Merge capabilities from other servers
    for server, response in responses.values():
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


async def aggregate_diagnostics(notifications: dict) -> dict:
    """
    Aggregate textDocument/publishDiagnostics notifications from multiple servers.
    Merges diagnostics for the same URI.
    notifications is dict[id(server), (server, msg)]
    """
    if not notifications:
        return {}

    # Take first notification as base
    _, base_notification = next(iter(notifications.values()))
    base_notification = base_notification.copy()

    # Get the URI from params
    base_params = base_notification.get('params', {})
    uri = base_params.get('uri', '')

    # Collect all diagnostics from all servers
    all_diagnostics = []
    for server, notification in notifications.values():
        params = notification.get('params', {})
        diags = params.get('diagnostics', [])

        # Add source field to each diagnostic
        for diag in diags:
            if 'source' not in diag:
                diag['source'] = server.name
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
