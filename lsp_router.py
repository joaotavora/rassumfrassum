"""
LSP-specific message routing and merging logic.
"""

import asyncio
from typing import Optional


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
        self.server_names = server_names
        self.primary_name = server_names[0]
        self.secondary_names = server_names[1:] if len(server_names) > 1 else []

    def should_route_to_all(self, method: str) -> bool:
        """Determine if a request should go to all servers."""
        # Only 'initialize' goes to all servers for now
        return method == 'initialize'

    def is_notification(self, msg: dict) -> bool:
        """Check if message is a notification (no 'id' field)."""
        return 'id' not in msg


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
        diagnostics: list,
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
