#!/usr/bin/env python3
"""
dada - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import traceback
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
from lolo import log, warn, event
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
    Main multiplexer.
    Blocks on asyncio.gather() until a bunch of loopy async tasks complete.

    """
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

    client_writer_transport, client_writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    client_writer = asyncio.StreamWriter(
        client_writer_transport, client_writer_protocol, None, loop
    )

    async def send_to_client(message: JSON, method: str, direction = "<--"):
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
                    logic.on_client_notification(method, msg.get("params", {}))

                    # FIXME: This breaks abstraction
                    if method in ('textDocument/didOpen', 'textDocument/didChange'):
                        keys_to_delete = [k for k, v in pending_aggregations.items() if v["dispatched"]]
                        for k in keys_to_delete:
                            del pending_aggregations[k]

                    for p in procs:
                        await write_lsp_message(p.stdin, msg)
                elif method is not None:
                    # Request
                    log_message("-->", msg, method)
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
                        log_message(f"[{p.name}] -->", msg, method)

                    inflight_requests[id] = (method, cast(JSON, params), len(target_procs))
                else:
                    # Response from client (to a server request)
                    if info := server_request_mapping.get(id):
                        # This is a response to a server request - remap ID and route to correct server
                        original_id, target_proc, req_method, req_params = info
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
                        msg["id"] = original_id
                        log_message(f"[{target_proc.name}] s->", msg, req_method)
                        await write_lsp_message(target_proc.stdin, msg)
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

    def _reconstruct(agg_state) -> JSON:
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

    async def _aggregation_heroics(
            proc, aggregation_key, method,
            expected_count, req_id, payload, is_error):
        agg_state = pending_aggregations.get(aggregation_key)
        if not agg_state:
            # First message in this aggregation
            async def send_whatever_is_there(state, method):
                await asyncio.sleep(
                    logic.get_aggregation_timeout_ms(method) / 1000.0
                )
                log(f"Timeout for aggregation for {method} ({id(state)})!")
                state["dispatched"] = "timed-out"
                await send_to_client(_reconstruct(state), method)

            agg_state = {
                "expected_count": expected_count,
                "received_count": 1,
                "id": req_id,
                "method": method,
                "aggregate_payload": payload,
                "dispatched": False,
            }
            agg_state["timeout_task"] = asyncio.create_task(
                send_whatever_is_there(agg_state, method))
            pending_aggregations[aggregation_key] = agg_state
        else:
            method = agg_state["method"]
            # Not the first message - aggregate with previous
            if agg_state["dispatched"]:
                log(f"Tardy {proc.name} aggregation for {method} ({id(agg_state)})")
            agg_state[
               "aggregate_payload"
            ] = logic.aggregate_payloads(
                agg_state["method"],
                agg_state["aggregate_payload"],
                payload,
                proc.server,
                is_error,
            )
            agg_state["received_count"] += 1
            # Check if all messages received
            if agg_state["received_count"] == agg_state["expected_count"]:
                if (agg_state["dispatched"] == "timed-out"):
                    if opts.drop_tardy:
                        log(f"Dropping now-complete timed-out "
                            f"aggregation for {method} ({id(agg_state)})")
                        return
                    else:
                        log(f"Re-sending now-complete timed-out"
                            f"aggregation for {method} ({id(agg_state)})!")
                elif (agg_state["dispatched"]):
                    log(f"Not re-sending re-completed "
                        f"aggregation for {method} ({id(agg_state)})!")
                    return
                else:
                    log(f"Completing aggregation for {method} ({id(agg_state)})!")
                # Cancel timeout
                agg_state["timeout_task"].cancel()
                # Send aggregated result to client
                await send_to_client(_reconstruct(agg_state), method)
                agg_state["dispatched"] = True
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
                    logic.on_server_request(
                        method, cast(JSON, params), proc.server)

                    # This is a request from server to client - remap ID
                    remapped_id = next_remapped_id
                    next_remapped_id += 1
                    server_request_mapping[remapped_id] = (
                        req_id, proc, method, cast(JSON, params)
                    )

                    # Forward to client with remapped ID
                    remapped_msg = msg.copy()
                    remapped_msg["id"] = remapped_id
                    await send_to_client(remapped_msg, method, "<-s")
                    continue

                # Server response OR Server notification
                aggregation_key = None
                expected_count = None
                is_error = False

                if method is None:
                    # Response - lookup method and params from request tracking
                    request_info = inflight_requests.get(req_id)
                    if not request_info:
                        log(f"Dropping response to unknown {req_id}")
                        continue
                    method, req_params, expected_count = request_info
                    is_error = "error" in msg
                    payload = msg.get("error") if is_error else msg.get("result")
                    payload = logic.on_server_response(
                        method, cast(JSON, req_params), cast(JSON, payload),
                        is_error, proc.server
                    )
                    log_message(f"[{proc.name}] <--", msg, method)
                    # Skip whole aggregation state business if the
                    # original request targeted only one server.
                    if expected_count == 1:
                        await send_to_client(msg, method)
                        continue
                    aggregation_key = ("response", req_id)
                else:
                    log_message(f"[{proc.name}] <--", msg, method)
                    payload = msg.get("params", {})
                    payload = logic.on_server_notification(
                        method, cast(JSON, payload), proc.server
                    )
                    expected_count = len(procs)
                    aggregation_key = logic.get_notif_aggregation_key(
                        method, payload)
                    # Logic can still dictate that aggregation will be
                    # skipped.
                    if aggregation_key == ("drop",):
                        log(f"Dropping message from {proc.name}: {method}")
                        continue
                    if aggregation_key is None:
                        await send_to_client(msg, method)
                        continue

                # If we haven't 'continue'd the loop and we got here,
                # start aggregation heroics
                await _aggregation_heroics(
                    proc, aggregation_key, method, expected_count,
                    req_id, payload, is_error)

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
    parser.add_argument('--delay-ms', type=int, default=0, metavar='N',
                        help='Delay all messages from dada.py by N ms.')
    parser.add_argument('--drop-tardy', action='store_true',
                        help='Drop tardy messages instead of re-sending complete aggregations')

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
