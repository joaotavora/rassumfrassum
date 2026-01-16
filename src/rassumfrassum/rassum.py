"""
rassumfrassum - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import argparse
import asyncio
import importlib
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Optional, cast

from .frassum import DirectResponse, PayloadItem, Server
from .json import (
    JSON,
)
from .json import (
    read_message as read_lsp_message,
)
from .json import (
    write_message as write_lsp_message,
)
from .util import event, log, warn, debug
from .stdio import create_stdin_reader, create_stdout_writer

# JSONRPC request IDs can be strings or integers
ReqId = str | int


class InferiorProcess:
    """A server subprocess and its associated logical server info."""

    def __init__(self, process, server):
        self.process = process
        self.server = server

    def __repr__(self):
        return f"InferiorProcess({self.name})"

    process: asyncio.subprocess.Process
    server: Server

    @property
    def stdin(self) -> asyncio.StreamWriter:
        return self.process.stdin  # ty:ignore[invalid-return-type]

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self.process.stdout  # ty:ignore[invalid-return-type]

    @property
    def stderr(self) -> asyncio.StreamReader:
        return self.process.stderr  # ty:ignore[invalid-return-type]

    @property
    def name(self) -> str:
        """Convenience property to access server name."""
        return self.server.name


@dataclass
class AggregationState:
    """State for tracking an ongoing message aggregation."""

    outstanding: set[InferiorProcess]
    id: ReqId
    method: str
    aggregate: dict[int, PayloadItem]
    dispatched: bool | str = False
    timeout_task: Optional[asyncio.Task] = field(default=None)


def log_message(direction: str, message: JSON, method: str) -> None:
    """
    Log a JSONRPC message to stderr with extra indications
    """
    id = message.get("id")
    prefix = method
    if id is not None:
        prefix += f"[{id}]"

    # Format: [timestamp] --> method_name {...json...}
    event(f"{direction} {prefix} {json.dumps(message, ensure_ascii=False)}")


async def forward_server_stderr(proc: InferiorProcess) -> None:
    """
    Forward server's stderr to our stderr, with appropriate prefixing.
    """
    try:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break

            # Decode and strip only the trailing newline (preserve other whitespace)
            line_str = line.decode("utf-8", errors="replace").rstrip("\n\r")
            log(f"[{proc.name}] {line_str}")
    except Exception as e:
        log(f"[{proc.name}] Error reading stderr: {e}")


async def launch_server(
    server_command: list[str], server_index: int
) -> InferiorProcess:
    """Launch a single LSP server subprocess."""
    basename = os.path.basename(server_command[0])
    # Make name unique by including index for multiple servers
    name = f"{basename}#{server_index}" if server_index > 0 else basename

    log(f"Launching {name}: {' '.join(server_command)}")

    process = await asyncio.create_subprocess_exec(
        *server_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    server = Server(name=name)
    proc = InferiorProcess(process=process, server=server)
    server.cookie = proc
    return proc


async def run_multiplexer(
    server_commands: list[list[str]], opts: argparse.Namespace
) -> None:
    """
    Main multiplexer.
    Blocks on asyncio.gather() until a bunch of loopy async tasks complete.

    """
    # Launch all servers
    procs: list[InferiorProcess] = []
    for i, cmd in enumerate(server_commands):
        p = await launch_server(cmd, i)
        procs.append(p)

    # Create message router using specified logic class
    class_name = opts.logic_class
    if '.' in class_name:
        # Fully qualified name: module.path.ClassName
        module_name, class_name = class_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        logic_class = getattr(module, class_name)
    else:
        # Simple name: look up in frassum module
        from . import frassum

        logic_class = getattr(frassum, class_name)
    log(f"Logic class: {logic_class}")

    # Track ongoing aggregations: key -> AggregationState
    response_aggregations: dict[ReqId, AggregationState] = {}

    # Track which request IDs need aggregation: id -> (method, params, responders)
    inflight_requests: dict[ReqId, tuple[str, JSON, set[InferiorProcess]]] = {}

    # Track server requests to remap IDs
    # remapped_id -> (original_server_id, server, method, params)
    server_request_mapping: dict[
        ReqId, tuple[ReqId, InferiorProcess, str, JSON]
    ] = {}
    next_remapped_id = 0

    # Track rass-originated requests to servers
    # rass_request_id -> (server, method, params, future)
    rass_request_mapping: dict[
        ReqId, tuple[InferiorProcess, str, JSON, asyncio.Future]
    ] = {}
    next_rass_request_id = 0

    # Track rass-originated requests to client
    # rass_request_id -> (method, params, future)
    rass_client_request_mapping: dict[
        ReqId, tuple[str, JSON, asyncio.Future]
    ] = {}

    # Track shutdown state
    shutting_down = False

    log(f"Primary server: {procs[0].name}")
    if len(procs) > 1:
        secondaries = [i.name for i in procs[1:]]
        log(f"Secondary servers: {', '.join(secondaries)}")
    if opts.delay_ms > 0:
        log(f"Delaying server responses by {opts.delay_ms}ms")

    # Get client streams
    client_reader = await create_stdin_reader()
    client_writer = await create_stdout_writer()

    async def _send_to_client(message: JSON, method: str, direction="<--"):
        """Send a message to the client, with optional delay."""

        async def send():
            log_message(direction, message, method)
            await write_lsp_message(client_writer, message)

        async def delayed_send():
            await asyncio.sleep(opts.delay_ms / 1000.0)
            await send()

        if opts.delay_ms > 0:
            asyncio.create_task(delayed_send())
        else:
            await send()

    async def _respond_to_client(id: ReqId, response: JSON, method: str):
        inflight_requests.pop(id, None)
        response["id"] = id
        response["jsonrpc"] = "2.0"
        await _send_to_client(response, method)

    async def notify_client(method: str, payload: JSON):
        """Send a notification to the client (for use by logic layer)."""
        if shutting_down:
            debug(f"Skipping notification to client (shutting down): {method}")
            return
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": payload,
        }
        await _send_to_client(message, method)

    async def request_client(method: str, payload: JSON) -> tuple[bool, JSON]:
        """
        Send a request to the client and wait for response (for use by logic layer).

        Returns:
            tuple of (is_error, response_payload)
        """
        nonlocal next_rass_request_id

        if shutting_down:
            debug(f"Skipping request to client (shutting down): {method}")
            return (True, {"message": "Shutting down"})

        # Allocate a unique string request ID
        rass_req_id = f"rass{next_rass_request_id}"
        next_rass_request_id += 1

        # Create a future to wait for the response
        future: asyncio.Future[tuple[bool, JSON]] = asyncio.Future()

        # Track this request
        rass_client_request_mapping[rass_req_id] = (method, payload, future)

        # Send the request to the client
        message = {
            "jsonrpc": "2.0",
            "id": rass_req_id,
            "method": method,
            "params": payload,
        }
        await _send_to_client(message, method)
        log_message("<-r", message, method)

        # Wait for the response
        is_error, response_payload = await future
        return (is_error, response_payload)

    async def request_server(
        server: Server, method: str, payload: JSON
    ) -> tuple[bool, JSON]:
        """
        Send a request to a server and wait for response (for use by logic layer).

        Returns:
            tuple of (is_error, response_payload)
        """
        nonlocal next_rass_request_id

        if shutting_down:
            debug(f"Skipping request to server (shutting down): {method}")
            return (True, {"message": "Shutting down"})

        # Get the proc for this server
        proc = cast(InferiorProcess, server.cookie)

        # Allocate a unique string request ID
        rass_req_id = f"rass{next_rass_request_id}"
        next_rass_request_id += 1

        # Create a future to wait for the response
        future: asyncio.Future[tuple[bool, JSON]] = asyncio.Future()

        # Track this request
        rass_request_mapping[rass_req_id] = (proc, method, payload, future)

        # Send the request to the server
        message = {
            "jsonrpc": "2.0",
            "id": rass_req_id,
            "method": method,
            "params": payload,
        }
        await write_lsp_message(proc.stdin, message)
        log_message(f"[{proc.name}] r->", message, method)

        # Wait for the response
        is_error, response_payload = await future
        return (is_error, response_payload)

    async def notify_server(server: Server, method: str, payload: JSON) -> None:
        """
        Send a notification to a server (for use by logic layer).
        """
        if shutting_down:
            debug(f"Skipping notification to server (shutting down): {method}")
            return

        # Get the proc for this server
        proc = cast(InferiorProcess, server.cookie)

        # Send the notification to the server
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": payload,
        }
        await write_lsp_message(proc.stdin, message)
        log_message(f"[{proc.name}] -->", message, method)

    # Instantiate logic with callbacks
    logic = logic_class(
        [p.server for p in procs],
        notify_client,
        request_client,
        request_server,
        notify_server,
        opts,
    )

    def _reconstruct(ag: AggregationState) -> JSON:
        """Reconstruct payload part of response from aggregation state."""

        payload, is_error = logic.process_responses(
            ag.method, list(ag.aggregate.values())
        )

        return {
            "error" if is_error else "result": payload,
        }

    def _start_aggregation(item, req_id, method, responders):
        """Start a new aggregation with the first response."""
        proc = cast(InferiorProcess, item.server.cookie)
        outstanding = responders.copy()
        outstanding.discard(proc)

        async def send_whatever_is_there(state: AggregationState, method):
            await asyncio.sleep(
                logic.get_aggregation_timeout_ms(method) / 1000.0
            )
            log(f"Timeout for aggregation for {method} ({id(state)})!")
            state.dispatched = "timed-out"
            await _respond_to_client(ag.id, _reconstruct(state), method)

        ag = AggregationState(
            outstanding=outstanding,
            id=req_id,
            method=method,
            aggregate={id(proc): item},
        )
        debug(
            f"Message from {item.server.name} starts aggregation for {method} ({id(ag)})"
        )
        ag.timeout_task = asyncio.create_task(
            send_whatever_is_there(ag, method)
        )
        response_aggregations[req_id] = ag

    async def _continue_aggregation(item, ag):
        """Continue an existing aggregation with an additional message."""
        proc = cast(InferiorProcess, item.server.cookie)
        method = ag.method
        debug(
            f"Message from {item.server.name} continues aggregation for {method} ({id(ag)})"
        )

        if ag.dispatched:
            debug(
                f"Tardy response from {item.server.name} for {method} ({id(ag)})"
            )
            return

        ag.aggregate[id(proc)] = item
        ag.outstanding.discard(proc)

        if not ag.outstanding:
            debug(f"Completing aggregation for {method} ({id(ag)})!")

            # Cancel timeout
            if ag.timeout_task:
                ag.timeout_task.cancel()

            # Send aggregated result to client (though check if hasn't
            # been cancelled first)
            await _respond_to_client(ag.id, _reconstruct(ag), method)
            ag.dispatched = True

    async def handle_client_request(req_id: ReqId, method: str,
                                    params: JSON | None):
        """Handle a single client request (spawned task to avoid blocking)."""
        nonlocal shutting_down

        # Track shutdown requests
        if method == "shutdown":
            shutting_down = True

        # Determine which servers to route to or get direct response
        result = await logic.on_client_request(
            method, params, [proc.server for proc in procs]
        )

        # Check if we should respond immediately without forwarding
        # (if we weren't cancelled, that is).
        if isinstance(result, DirectResponse) and inflight_requests.get(req_id):
            await _respond_to_client(
                req_id,
                {
                    "error" if result.is_error else "result": result.payload,
                },
                method,
            )
            return

        # Otherwise, forward to selected servers
        target_servers = result
        for t in target_servers:
            logic.process_request(method, params, t)
        target_procs = cast(
            list[InferiorProcess],
            [s.cookie for s in target_servers],
        )
        if target_procs:
            # Send to selected servers
            for p in target_procs:
                msg = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                }
                if params:
                    msg['params'] = params
                await write_lsp_message(p.stdin, msg)
                log_message(f"[{p.name}] -->", msg, method)

            # Update tracking to include server procs, but only if we
            # weren't cancelled already.
            if existing := inflight_requests.get(req_id):
                method_stored, params_stored, _ = existing
                inflight_requests[req_id] = (
                    method_stored,
                    params_stored,
                    set(target_procs),
                )
        else:
            # respond with rass error
            await _respond_to_client(
                req_id,
                {
                    "error": f"[rass] no servers to handle "
                    f"method='{method}' with params='{params}'!",
                },
                method,
            )

    async def handle_client_messages():
        """Read from client and route to appropriate servers."""
        nonlocal shutting_down
        try:
            while True:
                msg = await read_lsp_message(client_reader)
                if msg is None:
                    break

                method = msg.get("method")
                id = msg.get("id")

                if id is None and method is not None:
                    # Notification
                    log_message("-->", msg, method)
                    # Intercept '$/cancelRequest' and don't let the
                    # LspLogic decide this one
                    if method == "$/cancelRequest":
                        cancelled_id = msg.get("params", {}).get("id")
                        probe = inflight_requests.get(cancelled_id)
                        if probe:
                            # Prevents responses to the cancelled
                            # request from making it to the client...
                            _, _, target_procs = inflight_requests.pop(
                                cancelled_id
                            )
                            # ...but still forward $/cancelRequest to
                            # servers that got the request, of course.
                            for p in target_procs:
                                await write_lsp_message(p.stdin, msg)
                                log_message(f"[{p.name}] -->", msg, method)
                    else:
                        await logic.on_client_notification(
                            method, msg.get("params", {})
                        )
                elif method is not None:
                    # Client request
                    id = cast(ReqId, id)
                    log_message("-->", msg, method)
                    params = msg.get("params")

                    # Track ALL requests immediately (even DirectResponse ones)
                    # This allows $/cancelRequest to work uniformly
                    inflight_requests[id] = (
                        method,
                        cast(JSON, params),
                        set(),  # Will be updated by handler if forwarded to servers
                    )

                    # Spawn request handling as task to avoid blocking
                    asyncio.create_task(
                        handle_client_request(id, method, params)
                    )
                else:
                    # Response from client
                    id = cast(ReqId, id)
                    if info := rass_client_request_mapping.get(id):
                        # This is a response to a rass-originated request to client
                        req_method, req_params, future = info
                        del rass_client_request_mapping[id]

                        # Extract the response
                        is_error = "error" in msg
                        response_payload = (
                            msg.get("error") if is_error else msg.get("result")
                        )
                        log_message("r->", msg, req_method)

                        # Resolve the future
                        future.set_result(
                            (is_error, cast(JSON, response_payload))
                        )

                    elif info := server_request_mapping.get(id):
                        # This is a response to a server request - remap ID and route to correct server
                        original_id, target_proc, req_method, req_params = info
                        del server_request_mapping[id]

                        # Inform LspLogic
                        is_error = "error" in msg
                        response_payload = (
                            msg.get("error") if is_error else msg.get("result")
                        )
                        await logic.on_client_response(
                            req_method,
                            req_params,
                            cast(JSON, response_payload),
                            is_error,
                            target_proc.server,
                        )

                        # Remap ID back to original
                        msg["id"] = original_id
                        await write_lsp_message(target_proc.stdin, msg)
                        log_message(
                            f"[{target_proc.name}] s->", msg, req_method
                        )
                    else:
                        # Unknown response, log error
                        warn(f"Unknown request for response with id={id}!")

        except Exception as e:
            log(f"Error handling client messages: {e}")
        finally:
            # Close all server stdin
            for p in procs:
                p.stdin.close()
                await p.stdin.wait_closed()

    async def handle_server_messages(proc: InferiorProcess):
        """Read from a server and route back to client."""
        nonlocal next_remapped_id
        try:
            while True:
                msg = await read_lsp_message(proc.stdout)
                if msg is None:
                    # Server died - check if this was expected
                    if not shutting_down:
                        log(f"Error: Server {proc.name} died unexpectedly")
                        raise RuntimeError(f"Server {proc.name} crashed")
                    break

                # Distinguish message types.  Notifications won't have
                # id's, responses won't have method, requests will have both.
                req_id = msg.get("id")
                method = msg.get("method")

                # Server request: has both method and id
                if method and req_id is not None:
                    log_message(f"[{proc.name}] <-s", msg, method)
                    # Handle server request
                    params = msg.get("params", {})
                    direct_response = await logic.on_server_request(
                        method, cast(JSON, params), proc.server
                    )

                    # Check if we should respond immediately without forwarding
                    if direct_response:
                        response_msg = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error"
                            if direct_response.is_error
                            else "result": direct_response.payload,
                        }
                        await write_lsp_message(proc.stdin, response_msg)
                        log_message(f"[{proc.name}] s->", response_msg, method)
                        continue

                    # This is a request from server to client - remap ID
                    remapped_id = next_remapped_id
                    next_remapped_id += 1
                    server_request_mapping[remapped_id] = (
                        req_id,
                        proc,
                        method,
                        cast(JSON, params),
                    )

                    # Forward to client with remapped ID
                    remapped_msg = msg.copy()
                    remapped_msg["id"] = remapped_id
                    await _send_to_client(remapped_msg, method, "<-s")
                    continue

                if method is None:
                    req_id = cast(ReqId, req_id)
                    # Check if this is a response to a rass-originated request
                    if rass_info := rass_request_mapping.get(req_id):
                        _, rass_method, _, future = rass_info
                        del rass_request_mapping[req_id]

                        is_error = "error" in msg
                        payload = (
                            msg.get("error", {})
                            if is_error
                            else msg.get("result", {})
                        )
                        log_message(f"[{proc.name}] <-r", msg, rass_method)

                        # Resolve the future
                        future.set_result((is_error, cast(JSON, payload)))
                        continue

                    # Client-originated-request, do forwarding/aggregation
                    request_info = inflight_requests.get(req_id)
                    if not request_info:
                        log(f"Dropping response to unknown/cancelled {req_id}")
                        continue
                    method, req_params, responders = request_info
                    is_error = "error" in msg
                    payload = (
                        msg.get("error", {})
                        if is_error
                        else msg.get("result", {})
                    )
                    log_message(f"[{proc.name}] <--", msg, method)
                    await logic.on_server_response(
                        method,
                        req_params,
                        cast(JSON, payload),
                        is_error,
                        proc.server,
                    )
                    item = PayloadItem(payload, proc.server, is_error)

                    # Skip most of aggregation state business if the
                    # original request targeted only one server.
                    if len(responders) == 1:
                        logic.process_responses(method, [item])
                        await _respond_to_client(req_id, msg, method)
                        continue

                    # Response aggregation
                    if ag := response_aggregations.get(req_id):
                        await _continue_aggregation(item, ag)
                    else:
                        _start_aggregation(item, req_id, method, responders)
                else:
                    # Server notification - let logic layer handle it
                    log_message(f"[{proc.name}] <--", msg, method)
                    payload = msg.get("params", {})
                    await logic.on_server_notification(
                        method, cast(JSON, payload), proc.server
                    )

        except RuntimeError:
            # Server crashed - re-raise to propagate to main
            raise
        except Exception as e:
            log(f"Error handling messages from {proc.name}: {e}")
            print(traceback.format_exc(), file=sys.stderr)
        finally:
            pass

    # Create all tasks
    tasks = [handle_client_messages()]

    for p in procs:
        tasks.append(handle_server_messages(p))

        # Forward stderr
        if not opts.quiet_server:
            tasks.append(forward_server_stderr(p))

    try:
        await asyncio.gather(*tasks)
    except RuntimeError as e:
        log(f"Fatal error: {e}")
        sys.exit(1)

    # Wait for all servers to exit
    for p in procs:
        _ = await p.process.wait()
