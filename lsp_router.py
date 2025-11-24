"""
LSP-specific message routing and merging logic.
"""

import asyncio
from typing import Optional
from collections import defaultdict


class ServerInfo:
    """Information about a connected LSP server."""
    def __init__(self, name: str, is_primary: bool):
        self.name = name
        self.is_primary = is_primary
        self.next_id = 1000 if is_primary else 2000  # Separate ID spaces


class MessageRouter:
    """
    Routes LSP messages between client and multiple servers.
    Handles ID mapping, request merging, and notification aggregation.
    """

    def __init__(self, server_names: list[str]):
        """
        Initialize router with server names.
        First server is primary, rest are secondary.
        """
        self.servers = [
            ServerInfo(name, i == 0)
            for i, name in enumerate(server_names)
        ]
        self.primary = self.servers[0]
        self.secondaries = self.servers[1:] if len(self.servers) > 1 else []

        # ID mapping: client_id -> {server_name: server_id}
        self.client_to_server_ids = {}

        # Reverse mapping: (server_name, server_id) -> client_id
        self.server_to_client_id = {}

        # Track pending diagnostics for aggregation
        self.pending_diagnostics = {}  # uri -> {server_name: diagnostics}
        self.diagnostic_timers = {}  # uri -> asyncio.Task

    def allocate_server_id(self, server: ServerInfo) -> int:
        """Allocate a new request ID for the given server."""
        request_id = server.next_id
        server.next_id += 1
        return request_id

    def map_client_request(self, client_msg: dict, servers: list[ServerInfo]) -> dict[str, dict]:
        """
        Map a client request to server requests.
        Returns {server_name: server_message}
        """
        client_id = client_msg.get('id')
        if client_id is None:
            # Notification - no ID mapping needed
            return {srv.name: client_msg for srv in servers}

        # Request - allocate server IDs and track mapping
        server_messages = {}
        server_id_map = {}

        for srv in servers:
            server_id = self.allocate_server_id(srv)
            server_msg = client_msg.copy()
            server_msg['id'] = server_id

            server_messages[srv.name] = server_msg
            server_id_map[srv.name] = server_id

            # Track mapping for response
            self.server_to_client_id[(srv.name, server_id)] = client_id

        self.client_to_server_ids[client_id] = server_id_map
        return server_messages

    def map_server_response(self, server_name: str, server_msg: dict) -> Optional[int]:
        """
        Map a server response back to client ID.
        Returns client_id if found, None otherwise.
        """
        server_id = server_msg.get('id')
        if server_id is None:
            return None

        key = (server_name, server_id)
        return self.server_to_client_id.get(key)

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
