"""
Relay server support for inter-server message forwarding.

Enables one LSP server to send requests through rass to another LSP server
and receive responses back. The primary use case is Volar v3's tsserver/request
protocol, where the Vue LS sends requests that need to be forwarded to a
TypeScript LS.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from .frassum import Server
from .json import JSON
from .util import debug, info, warn


@dataclass
class RelaySpec:
    """Specification for how to relay messages between servers."""

    match_method: str  # Notification method to intercept (e.g. "tsserver/request")
    send_method: str  # Request method to send to relay server (e.g. "workspace/executeCommand")
    respond_method: str  # Notification method to send back to source (e.g. "tsserver/response")
    command: str | None = None  # Command name for workspace/executeCommand
    init_options: JSON | None = None  # Extra initializationOptions for relay server
    forward_notifications: list[str] | None = None  # Client notifications to forward to relay server
    forward_requests: list[str] | None = None  # Client requests to also route to relay server


class RelayHandler:
    """Handles relaying notifications from source servers to a relay server."""

    def __init__(
        self,
        spec: RelaySpec,
        server: Server,
        request_server: Callable[[Server, str, JSON], Awaitable[tuple[bool, JSON]]],
        notify_server: Callable[[Server, str, JSON], Awaitable[None]],
    ):
        self.spec = spec
        self.server = server
        self.request_server = request_server
        self.notify_server = notify_server
        self.initialized = asyncio.Event()

    async def initialize(self, client_init_params: JSON) -> tuple[bool, JSON]:
        """Initialize the relay server using client's init params."""
        # Build init params from client's params
        init_params = {
            "processId": client_init_params.get("processId"),
            "rootUri": client_init_params.get("rootUri"),
            "workspaceFolders": client_init_params.get("workspaceFolders"),
            "capabilities": client_init_params.get("capabilities", {}),
        }

        # Merge preset-provided initializationOptions
        init_options = client_init_params.get("initializationOptions") or {}
        if self.spec.init_options:
            init_options = {**init_options, **self.spec.init_options}
        if init_options:
            init_params["initializationOptions"] = init_options

        info(f"Initializing relay server {self.server.name}")
        is_error, result = await self.request_server(
            self.server, "initialize", init_params
        )

        if not is_error:
            # Send initialized notification
            await self.notify_server(self.server, "initialized", {})
            # Extract capabilities
            caps = result.get("capabilities", {})
            self.server.caps = caps.copy() if caps else {}
            info(f"Relay server {self.server.name} initialized")
        else:
            warn(f"Relay server {self.server.name} failed to initialize: {result}")

        self.initialized.set()
        return is_error, result

    async def handle_notification(self, params: JSON, source: Server) -> None:
        """Handle an intercepted notification by relaying to the relay server.

        Protocol: inbound params are [[seq, ...args]], outbound wraps args in
        the send_method, response pairs seq with body.
        """
        await self.initialized.wait()

        # Extract correlation data: params is [[seq, command, args]]
        inner = params[0]
        seq = inner[0]
        rest = inner[1:]

        # Build the outbound request
        if self.spec.command:
            # workspace/executeCommand style
            outbound_params = {
                "command": self.spec.command,
                "arguments": list(rest),
            }
        else:
            outbound_params = {"arguments": list(rest)}

        debug(
            f"Relaying {self.spec.match_method} seq={seq} to "
            f"{self.server.name} via {self.spec.send_method}"
        )

        is_error, result = await self.request_server(
            self.server, self.spec.send_method, outbound_params
        )

        # Build response notification back to source
        if is_error:
            # Don't send error responses back — the source server already
            # handles missing responses (timeout), and sending raw error
            # objects as the body crashes Volar (TypeError on the body shape).
            warn(f"Relay request seq={seq} failed: {result}")
            return

        body = result.get("body", result) if isinstance(result, dict) else result

        response_params = [[seq, body]]
        debug(f"Sending {self.spec.respond_method} seq={seq} back to {source.name}")
        await self.notify_server(source, self.spec.respond_method, response_params)

    async def shutdown(self) -> None:
        """Shut down the relay server."""
        info(f"Shutting down relay server {self.server.name}")
        await self.request_server(self.server, "shutdown", None)
        await self.notify_server(self.server, "exit", None)
