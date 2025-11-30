#!/usr/bin/env python3
"""
dada - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import argparse
import asyncio
import json
import os
import sys

from wowo import LspLogic, Server
from jaja import (
    read_message as read_lsp_message,
    write_message as write_lsp_message,
    JSON,
)
from typing import cast
from dataclasses import dataclass


@dataclass
class InferiorProcess:
    """A server subprocess and its associated logical server info."""
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


def log(s: str):
    print(f"[dada] {s}", file=sys.stderr)


def log_message(direction: str, message: JSON) -> None:
    """
    Log a message to stderr with direction indicator.
    """
    # Determine message type
    if "method" in message:
        msg_type = cast(str, message["method"])
    elif "result" in message or "error" in message:
        msg_type = "response"
    else:
        msg_type = "message"

    # Format: [dada] --> method_name {...json...}
    json_str = json.dumps(message, ensure_ascii=False)
    log(f"{direction} {msg_type} {json_str}")


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


async def launch_server(server_command: list[str], server_index: int) -> InferiorProcess:
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
    return InferiorProcess(process=process, server=server)


async def run_multiplexer(
    server_commands: list[list[str]], opts: argparse.Namespace
) -> None:
    """
    Main multiplexer loop.
    Handles one or more LSP servers with intelligent message routing.
    """
    quiet_server = opts.quiet_server
    delay_ms = opts.delay_ms
    # Launch all servers
    procs: list[InferiorProcess] = []
    for i, cmd in enumerate(server_commands):
        p = await launch_server(cmd, i)
        procs.append(p)

    # Create message router
    logic = LspLogic(procs[0].server)

    # Track ongoing aggregations
    # key -> {expected_count, received_count, id, method, aggregate_payload, timeout_task}
    pending_aggregations = {}

    # Track which request IDs need aggregation: id -> (method, params)
    requests_needing_aggregation = {}

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
    if delay_ms > 0:
        log(f"Delaying server responses by {delay_ms}ms")

    # Get client streams
    loop = asyncio.get_event_loop()

    client_reader = asyncio.StreamReader()
    client_protocol = asyncio.StreamReaderProtocol(client_reader)
    _ = await loop.connect_read_pipe(lambda: client_protocol, sys.stdin)

    client_writer_transport, client_writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    client_writer = asyncio.StreamWriter(
        client_writer_transport, client_writer_protocol, None, loop
    )

    async def send_to_client(message: JSON):
        """Send a message to the client, with optional delay."""

        async def delayed_send():
            await asyncio.sleep(delay_ms / 1000.0)
            log_message("<--", message)
            await write_lsp_message(client_writer, message)

        if delay_ms > 0:
            # Spawn independent background task so delays don't accumulate
            asyncio.create_task(delayed_send())
        else:
            log_message("<--", message)
            await write_lsp_message(client_writer, message)

    async def handle_client_messages():
        """Read from client and route to appropriate servers."""
        nonlocal shutting_down
        try:
            while True:
                msg = await read_lsp_message(client_reader)
                if msg is None:
                    break

                log_message("-->", msg)

                method = msg.get("method")
                id = msg.get("id")

                # Route based on message type
                if id is None and method is not None:  # notification
                    # Inform LspLogic and route to all
                    logic.on_client_notification(method, msg.get("params", {}))

                    # FIXME: This breaks abstraction - dada.py should not know about LSP-specific methods.
                    # We should refactor this so wowo.py tells us which aggregations to clean up.
                    # Clean up old aggregations for updated documents
                    if method in ('textDocument/didOpen', 'textDocument/didChange'):
                        params = msg.get("params", {})
                        uri = params.get('textDocument', {}).get('uri')
                        if uri:
                            keys_to_remove = [k for k in pending_aggregations.keys()
                                            if isinstance(k, tuple) and len(k) >= 3 and k[2] == uri]
                            for key in keys_to_remove:
                                del pending_aggregations[key]

                    for p in procs:
                        await write_lsp_message(p.stdin, msg)
                elif method is not None: # request
                    # Inform LspLogic
                    params = msg.get("params", {})
                    logic.on_client_request(method, params)
                    # Track shutdown requests
                    if method == "shutdown":
                        shutting_down = True
                    # Request from client to servers
                    # Determine which servers to route to
                    target_procs = []
                    for proc in procs:  # procs is already ordered with primary first
                        decision = logic.should_route_to_server(method, params, proc.server)

                        if decision == "stop":
                            target_procs.append(proc)
                            break  # Early termination
                        elif decision is True:
                            target_procs.append(proc)
                        # decision is False: skip this server, continue

                    # Send to selected servers
                    for p in target_procs:
                        await write_lsp_message(p.stdin, msg)
                        log_message(f"[{p.name}] -->", msg)

                    # Track for aggregation if multiple servers
                    if len(target_procs) > 1:
                        requests_needing_aggregation[id] = (method, cast(JSON, params), len(target_procs))
                else:
                    # Response from client (to a server request)
                    if id in server_request_mapping:
                        # This is a response to a server request - remap ID and route to correct server
                        original_id, target_proc, req_method, req_params = server_request_mapping[id]
                        del server_request_mapping[id]

                        # Inform LspLogic
                        is_error = "error" in msg
                        response_payload = msg.get("error") if is_error else msg.get("result")
                        logic.on_client_response(
                            req_method,
                            req_params,
                            cast(JSON, response_payload),
                            is_error,
                            target_proc.server
                        )

                        # Remap ID back to original
                        remapped_msg = msg.copy()
                        remapped_msg["id"] = original_id
                        await write_lsp_message(target_proc.stdin, remapped_msg)
                        log_message(f"[{target_proc.name}] -->", remapped_msg)
                    else:
                        # Unknown response, log error
                        log(
                            f"Warning: Received response with id={id} but no matching request"
                        )

        except Exception as e:
            log(f"Error handling client messages: {e}")
        finally:
            # Close all server stdin
            for p in procs:
                p.stdin.close()
                await p.stdin.wait_closed()

    def reconstruct_message(agg_state) -> JSON:
        """Reconstruct full JSONRPC message from aggregation state."""
        if agg_state["id"] is not None:
            # Response
            return {
                "jsonrpc": "2.0",
                "id": agg_state["id"],
                "result": agg_state["aggregate_payload"],
            }
        else:
            # Notification
            return {
                "jsonrpc": "2.0",
                "method": agg_state["method"],
                "params": agg_state["aggregate_payload"],
            }

    async def handle_aggregation_timeout(agg_key):
        """Handle timeout for an aggregation - send whatever we have."""
        agg_state = pending_aggregations.get(agg_key)
        if agg_state and agg_state["aggregate_payload"] is not None:
            final_msg = reconstruct_message(agg_state)
            await send_to_client(final_msg)
            agg_state["dispatched"] = True

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

                log_message(f"[{proc.name}] <--", msg)

                # Distinguish message types
                msg_id = msg.get("id")
                method = msg.get("method")

                # Server request: has both method and id
                if method is not None and msg_id is not None:
                    # Handle server request
                    params = msg.get("params", {})
                    logic.on_server_request(method, cast(JSON, params), proc.server)

                    # This is a request from server to client - remap ID
                    remapped_id = next_remapped_id
                    next_remapped_id += 1
                    server_request_mapping[remapped_id] = (
                        msg_id, proc, method, cast(JSON, params)
                    )

                    # Forward to client with remapped ID
                    remapped_msg = msg.copy()
                    remapped_msg["id"] = remapped_id
                    await send_to_client(remapped_msg)
                    continue

                # Server notification or response - extract payload and handle
                if method is not None:
                    # Notification - payload is params
                    payload = msg.get("params", {})
                    payload = logic.on_server_notification(
                        method, cast(JSON, payload), proc.server
                    )
                    is_error = False
                else:
                    # Response - lookup method and params from request tracking
                    request_info = requests_needing_aggregation.get(msg_id)
                    if request_info:
                        method, req_params, expected_count = request_info
                    else:
                        method, req_params, expected_count = None, {}, len(procs)

                    is_error = "error" in msg
                    payload = msg.get("error") if is_error else msg.get("result")
                    payload = logic.on_server_response(
                        method, cast(JSON, req_params), cast(JSON, payload), is_error, proc.server
                    )

                # Check if message needs aggregation
                aggregation_key = None
                if msg_id is not None and msg_id in requests_needing_aggregation:
                    # This is a response to a request that was sent to all servers
                    aggregation_key = ("response", msg_id)
                else:
                    # Check if this notification needs aggregation
                    aggregation_key = logic.get_aggregation_key(method, payload)

                # Check if logic wants us to drop this message
                if aggregation_key == ("drop",):
                    log(f"Dropping message from {proc.name}: {method}")
                    continue

                if aggregation_key is not None:
                    agg_state = pending_aggregations.get(aggregation_key)
                    if agg_state:
                        # Drop if already dispatched
                        if agg_state["dispatched"]:
                            log(f"Dropping tardy message from {proc.name}: {method}")
                            continue
                        # Not the first message - aggregate with previous
                        agg_state[
                            "aggregate_payload"
                        ] = await logic.aggregate_payloads(
                            agg_state["method"],
                            agg_state["aggregate_payload"],
                            payload,
                            proc.server,
                            is_error,
                        )
                        agg_state["received_count"] += 1
                    else:
                        timeout_task = asyncio.create_task(
                            asyncio.sleep(
                                logic.get_aggregation_timeout_ms(method) / 1000.0
                            )
                        )
                        agg_state = {
                            "expected_count": expected_count,
                            "received_count": 1,
                            "id": msg_id,
                            "method": method,
                            "aggregate_payload": payload,
                            "timeout_task": timeout_task,
                            "dispatched": False,
                        }
                        pending_aggregations[aggregation_key] = agg_state

                        # Setup timeout handler
                        async def timeout_handler():
                            await timeout_task
                            # Check if aggregation still pending (might have completed early)
                            if aggregation_key in pending_aggregations:
                                await handle_aggregation_timeout(aggregation_key)

                        asyncio.create_task(timeout_handler())

                    # Check if all messages received
                    if agg_state["received_count"] == agg_state["expected_count"]:
                        # Cancel timeout
                        agg_state["timeout_task"].cancel()
                        # Send aggregated result to client
                        final_msg = reconstruct_message(agg_state)
                        await send_to_client(final_msg)
                        agg_state["dispatched"] = True
                        # Remove from requests needing aggregation if it's a response
                        if msg_id is not None:
                            requests_needing_aggregation.pop(msg_id, None)
                else:
                    # Forward immediately to client
                    await send_to_client(msg)

        except RuntimeError:
            # Server crashed - re-raise to propagate to main
            raise
        except Exception as e:
            log(f"Error handling messages from {proc.name}: {e}")
        finally:
            pass

    # Create all tasks
    tasks = [handle_client_messages()]

    for p in procs:
        tasks.append(handle_server_messages(p))

        # Forward stderr
        if not quiet_server:
            tasks.append(forward_server_stderr(p))

    try:
        await asyncio.gather(*tasks)
    except RuntimeError as e:
        # Server crashed unexpectedly
        log(f"Fatal error: {e}")
        sys.exit(1)

    # Wait for all servers to exit
    for p in procs:
        _ = await p.process.wait()


def parse_server_commands(args: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Split args on '--' separators.
    Returns (dada_args, [server_command1, server_command2, ...])
    """
    if "--" not in args:
        return args, []

    # Find all '--' separator indices
    separator_indices = [i for i, arg in enumerate(args) if arg == "--"]

    # Everything before first '--' is dada options
    dada_args = args[: separator_indices[0]]

    # Split server commands
    server_commands: list[list[str]] = []
    for i, sep_idx in enumerate(separator_indices):
        # Find start and end of this server command
        start = sep_idx + 1
        end = separator_indices[i + 1] if i + 1 < len(separator_indices) else len(args)

        server_cmd: list[str] = args[start:end]
        if server_cmd:  # Only add non-empty commands
            server_commands.append(server_cmd)

    return dada_args, server_commands


def main() -> None:
    """
    Parse arguments and start the multiplexer.
    """
    args = sys.argv[1:]

    # Parse multiple '--' separators for multiple servers
    dada_args, server_commands = parse_server_commands(args)

    if not server_commands:
        log("Usage: dada [OPTIONS] -- <primary-server> [args] [-- <secondary-server> [args]]...")
        sys.exit(1)

    # Parse dada options with argparse
    parser = argparse.ArgumentParser(
        prog='dada',
        add_help=False,
    )
    parser.add_argument('--quiet-server', action='store_true')
    parser.add_argument('--delay-ms', type=int, default=0, metavar='N')

    opts = parser.parse_args(dada_args)

    # Validate
    assert opts.delay_ms >= 0, "--delay-ms must be non-negative"

    try:
        asyncio.run(run_multiplexer(server_commands, opts))
    except KeyboardInterrupt:
        log("\nShutting down...")
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
