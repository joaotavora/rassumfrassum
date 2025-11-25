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
        # request_id -> {method: str, responses: {server_name: response}, expected_count: int}
        self.pending_merges : dict[int, dict[str, Any]]= {}  # pyright: ignore[reportExplicitAny]

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        return method in ['initialize', 'shutdown']

    def is_notification(self, msg: JSON) -> bool:
        """Check if message is a notification (no 'id' field)."""
        return 'id' not in msg

    def track_merge_request(self, request_id: int, method: str, server_count: int) -> None:
        """Start tracking a request that needs response merging."""
        self.pending_merges[request_id] = {
            'method': method,
            'responses': {},
            'expected_count': server_count
        }

    def is_pending_merge(self, request_id: int) -> bool:
        """Check if a request ID is pending merge."""
        return request_id in self.pending_merges

    async def add_response(self, request_id: int, server_name: str, response: JSON) -> tuple[bool, JSON | None, JSON]:
        """
        Add a server response to pending merge.
        Returns (is_complete, merged_response, metadata).
        If is_complete is True, all responses received and merged_response is ready.
        """
        if request_id not in self.pending_merges:
            return (False, None, {})

        merge_state = self.pending_merges[request_id]
        merge_state['responses'][server_name] = response

        # Check if all responses collected
        if len(merge_state['responses']) == merge_state['expected_count']:
            method = merge_state['method']
            merged = await self._merge_responses(method, merge_state['responses'])
            metadata = self._extract_metadata(method, merge_state['responses'])
            del self.pending_merges[request_id]
            return (True, merged, metadata)

        return (False, None, {})

    async def _merge_responses(self, method: str, responses: dict[str, dict]) -> dict:
        """Merge responses based on method type."""
        if method == 'initialize':
            return await merge_initialize_responses(responses)
        elif method == 'shutdown':
            # Shutdown returns null, just take first response
            return next(iter(responses.values()))
        else:
            # Default: take primary's response (shouldn't reach here)
            return next(iter(responses.values()))

    def _extract_metadata(self, method: str, responses: dict[str, dict]) -> dict:
        """Extract method-specific metadata for lspylex to process."""
        metadata = {}

        if method == 'initialize':
            # Extract serverInfo names for each server
            server_names = {}
            for server_name, response in responses.items():
                result = response.get('result', {})
                server_info = result.get('serverInfo', {})
                if 'name' in server_info:
                    server_names[server_name] = server_info['name']

            if server_names:
                metadata['server_names'] = server_names

        return metadata


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
