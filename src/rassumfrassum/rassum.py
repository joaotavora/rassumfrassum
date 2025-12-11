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

from .frassum import Server
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
        return self.process.stdin  # pyright: ignore[reportReturnType]

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self.process.stdout  # pyright: ignore[reportReturnType]

    @property
    def stderr(self) -> asyncio.StreamReader:
        return self.process.stderr  # pyright: ignore[reportReturnType]

    @property
    def name(self) -> str:
        """Convenience property to access server name."""
        return self.server.name


@dataclass
class AggregationState:
    """State for tracking an ongoing message aggregation."""

    outstanding: set[InferiorProcess]
    id: Optional[int]
    method: str
    aggregate: dict[int, tuple[JSON | list, Server, bool]]
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
    logic = logic_class([p.server for p in procs])

    # Track ongoing aggregations: key -> AggregationState
    pending_aggregations: dict[tuple, AggregationState] = {}

    # Track which request IDs need aggregation: id -> (method, params)
    inflight_requests = {}

    # Track server requests to remap IDs
    # remapped_id -> (original_server_id, server, method, params)
    server_request_mapping = {}
    next_remapped_id = 0

    # Track shutdown state
    shutting_down = False

    log(f"Primary server: {procs[0].name}")
    if len(procs) > 1:
        secondaries = [i.name for i in procs[1:]]
        log(f"Secondary servers: {', '.join(secondaries)}")
    if opts.delay_ms > 0:
        log(f"Delaying server responses by {opts.delay_ms}ms")

    # Get client streams
    loop = asyncio.get_event_loop()

    client_reader = asyncio.StreamReader()
    client_protocol = asyncio.StreamReaderProtocol(client_reader)
    _ = await loop.connect_read_pipe(lambda: client_protocol, sys.stdin)

    (
        client_writer_transport,
        client_writer_protocol,
    ) = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    client_writer = asyncio.StreamWriter(
        client_writer_transport, client_writer_protocol, None, loop
    )

    async def send_to_client(message: JSON, method: str, direction="<--"):
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
                    await logic.on_client_notification(method, msg.get("params", {}))

                    for p in procs:
                        await write_lsp_message(p.stdin, msg)
                        log_message(f"[{p.name}] -->", msg, method)
                elif method is not None:
                    # Request
                    log_message("-->", msg, method)
                    params = msg.get("params", {})
                    # Track shutdown requests.  FIXME: breaks
                    # abstraction
                    if method == "shutdown":
                        shutting_down = True
                    # Determine which servers to route to.
                    target_servers = await logic.on_client_request(
                        method, params, [proc.server for proc in procs]
                    )
                    target_procs = cast(
                        list[InferiorProcess],
                        [s.cookie for s in target_servers],
                    )

                    # Send to selected servers
                    for p in target_procs:
                        await write_lsp_message(p.stdin, msg)
                        log_message(f"[{p.name}] -->", msg, method)

                    inflight_requests[id] = (
                        method,
                        cast(JSON, params),
                        set(target_procs),
                    )
                else:
                    # Response from client (to a server request)
                    if info := server_request_mapping.get(id):
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

    def _reconstruct(ag: AggregationState) -> JSON:
        """Reconstruct full JSONRPC message from aggregation state."""

        payload = logic.aggregate_payloads(ag.method, list(ag.aggregate.values()))

        if ag.id is not None:
            # Response
            return {
                "jsonrpc": "2.0",
                "id": ag.id,
                "result": payload,
            }
        else:
            # Notification
            return {
                "jsonrpc": "2.0",
                "method": ag.method,
                "params": payload,
            }

    async def _aggregation_heroics(
            proc, aggregation_key, start_anew, method, targets, req_id, payload, is_error
    ):
        ag = not start_anew and pending_aggregations.get(aggregation_key)

        if not ag:
            outstanding = targets.copy()

            outstanding.discard(proc)

            # First message in this aggregation
            async def send_whatever_is_there(state: AggregationState, method):
                await asyncio.sleep(
                    logic.get_aggregation_timeout_ms(method) / 1000.0
                )
                log(f"Timeout for aggregation for {method} ({id(state)})!")
                state.dispatched = "timed-out"
                await send_to_client(_reconstruct(state), method)

            ag = AggregationState(
                outstanding=outstanding,
                id=req_id,
                method=method,
                aggregate={id(proc): (payload, proc.server, is_error)},
            )
            debug(f"Message from {proc.name} starts aggregation for {method} ({id(ag)})")
            ag.timeout_task = asyncio.create_task(
                send_whatever_is_there(ag, method)
            )
            pending_aggregations[aggregation_key] = ag
        else:
            method = ag.method
            debug(f"Message from {proc.name} starts aggregation for {method} ({id(ag)})")
            # Not the first message - aggregate with previous
            if ag.dispatched:
                debug(f"Tardy {proc.name} aggregation for {method} ({id(ag)})")
            ag.aggregate[id(proc)] = (payload, proc.server, is_error)
            ag.outstanding.discard(proc)
            if not ag.outstanding:
                # Aggregation is now complete
                if ag.dispatched == "timed-out":
                    if opts.drop_tardy:
                        warn(
                            f"Dropping tardy message for previously timed-out "
                            f"aggregation for {method} ({id(ag)})"
                        )
                        return
                    else:
                        debug(
                            f"Re-sending now-complete timed-out "
                            f"aggregation for {method} ({id(ag)})!"
                        )
                elif ag.dispatched:
                    if opts.drop_tardy:
                        warn(
                            f"Dropping tardy message for previously completed "
                            f"aggregation for {method} ({id(ag)})!"
                        )
                        return
                    else:
                        debug(
                            f"Re-sending enhancement of previously completed "
                            f"aggregation for {method} ({id(ag)})!"
                        )
                else:
                    debug(f"Completing aggregation for {method} ({id(ag)})!")
                # Cancel timeout
                if ag.timeout_task:
                    ag.timeout_task.cancel()
                # Send aggregated result to client
                await send_to_client(_reconstruct(ag), method)
                ag.dispatched = True
                # Remove from requests needing aggregation if it's a response
                if req_id is not None:
                    inflight_requests.pop(req_id, None)

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
                    await logic.on_server_request(
                        method, cast(JSON, params), proc.server
                    )

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
                    await send_to_client(remapped_msg, method, "<-s")
                    continue

                # Server response OR Server notification
                aggregation_key = None
                targets = set(procs)  # responses can override this
                is_error = False

                if method is None:
                    # Response - lookup method and params from request tracking
                    request_info = inflight_requests.get(req_id)
                    if not request_info:
                        log(f"Dropping response to unknown {req_id}")
                        continue
                    method, req_params, targets = request_info
                    is_error = "error" in msg
                    payload = (
                        msg.get("error") if is_error else msg.get("result")
                    )
                    log_message(f"[{proc.name}] <--", msg, method)
                    await logic.on_server_response(
                        method,
                        cast(JSON, req_params),
                        cast(JSON, payload),
                        is_error,
                        proc.server,
                    )
                    # Skip whole aggregation state business if the
                    # original request targeted only one server.
                    if len(targets) == 1:
                        await send_to_client(msg, method)
                        continue
                    aggregation_key = ("response", req_id)
                    start_anew = False
                else:
                    log_message(f"[{proc.name}] <--", msg, method)
                    payload = msg.get("params", {})
                    await logic.on_server_notification(
                        method, cast(JSON, payload), proc.server
                    )
                    aggregation_data = logic.get_notif_aggregation_key(
                        method, payload
                    )
                    # Logic can still dictate that aggregation will be
                    # skipped.
                    if aggregation_data == "drop":
                        log(f"Dropping message from {proc.name}: {method}")
                        continue
                    if aggregation_data is None:
                        await send_to_client(msg, method)
                        continue
                    (aggregation_key, start_anew) = aggregation_data

                # If we haven't continued the loop and we got here,
                # start aggregation heroics
                await _aggregation_heroics(
                    proc,
                    aggregation_key,
                    start_anew,
                    method,
                    targets,
                    req_id,
                    payload,
                    is_error,
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
