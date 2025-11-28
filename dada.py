#!/usr/bin/env python3
"""
dada - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import json
import asyncio
import sys
import os

from wowo import MessageRouter
from jsonrpc import read_message as read_lsp_message, write_message as write_lsp_message, JSON
from server_process import ServerProcess
from typing import cast

def log(s : str):
    print(f"[dada] {s}", file=sys.stderr)

def log_message(direction: str, message: JSON) -> None:
    """
    Log a message to stderr with direction indicator.
    """
    # Determine message type
    if 'method' in message:
        msg_type = cast(str, message['method'])
    elif 'result' in message or 'error' in message:
        msg_type = 'response'
    else:
        msg_type = 'message'

    # Format: [dada] --> method_name {...json...}
    json_str = json.dumps(message, ensure_ascii=False)
    log(f"{direction} {msg_type} {json_str}")


async def forward_server_stderr(
    server: ServerProcess
) -> None:
    """
    Forward server's stderr to our stderr, prefixing each line with the server basename.
    """
    assert server.stderr
    try:
        while True:
            line = await server.stderr.readline()
            if not line:
                break

            # Decode and strip only the trailing newline (preserve other whitespace)
            line_str = line.decode('utf-8', errors='replace').rstrip('\n\r')
            log(f"[{server.name}] {line_str}")
    except Exception as e:
        log(f"[{server.name}] Error reading stderr: {e}")


async def launch_server(server_command: list[str], server_index: int) -> ServerProcess:
    """Launch a single LSP server subprocess."""
    basename = os.path.basename(server_command[0])
    # Make name unique by including index for multiple servers
    name = f"{basename}#{server_index}" if server_index > 0 else basename

    print(f"[dada] Launching {name}: {' '.join(server_command)}", file=sys.stderr, flush=True)

    process = await asyncio.create_subprocess_exec(
        *server_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    return ServerProcess(
        name=name,
        process=process
    )


async def run_multiplexer(
    server_commands: list[list[str]],
    quiet_server: bool = False,
    delay_ms: int = 0
) -> None:
    """
    Main multiplexer loop.
    Handles one or more LSP servers with intelligent message routing.
    """
    # Launch all servers
    servers : list[ServerProcess] = []
    for i, cmd in enumerate(server_commands):
        server = await launch_server(cmd, i)
        servers.append(server)

    # Create message router
    server_names = [s.name for s in servers]
    router = MessageRouter(server_names)

    # Track ongoing aggregations
    # key -> {expected_count, received_count, id, method, aggregate_payload, timeout_task}
    pending_aggregations = {}

    # Track which request IDs need aggregation: id -> method
    requests_needing_aggregation = {}

    # Track server requests to remap IDs
    # remapped_id -> (original_server_id, server_name)
    server_request_mapping = {}
    next_remapped_id = 0

    # Track shutdown state
    shutting_down = False

    print(f"[dada] Primary server: {servers[0].name}", file=sys.stderr, flush=True)
    if len(servers) > 1:
        secondaries = [s.name for s in servers[1:]]
        print(f"[dada] Secondary servers: {', '.join(secondaries)}", file=sys.stderr, flush=True)
    if delay_ms > 0:
        print(f"[dada] Delaying server responses by {delay_ms}ms", file=sys.stderr, flush=True)

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
            log_message('<--', message)
            await write_lsp_message(client_writer, message)

        if delay_ms > 0:
            # Spawn independent background task so delays don't accumulate
            asyncio.create_task(delayed_send())
        else:
            log_message('<--', message)
            await write_lsp_message(client_writer, message)

    async def handle_client_messages():
        """Read from client and route to appropriate servers."""
        nonlocal shutting_down
        try:
            while True:
                msg = await read_lsp_message(client_reader)
                if msg is None:
                    break

                log_message('-->', msg)

                method = msg.get('method')
                id = msg.get('id')

                # Track shutdown requests
                if method == 'shutdown':
                    shutting_down = True

                # Route based on message type
                if id is None and method is not None:  # notification
                    # Broadcast all notifications to all servers
                    for server in servers:
                        await write_lsp_message(server.stdin, msg)
                elif method is not None:
                    # Request from client to servers
                    if router.should_route_to_all(method):
                        # Send to all servers with original ID
                        for server in servers:
                            await write_lsp_message(server.stdin, msg)
                            log_message(f'[{server.name}] -->', msg)

                        # Track that this request needs aggregation
                        requests_needing_aggregation[id] = method
                    else:
                        # Send only to primary server with original ID
                        await write_lsp_message(servers[0].stdin, msg)
                        log_message(f'[{servers[0].name}] -->', msg)
                else:
                    # Response from client (to a server request)
                    if id in server_request_mapping:
                        # This is a response to a server request - remap ID and route to correct server
                        original_id, server_name = server_request_mapping[id]
                        del server_request_mapping[id]

                        # Find the server
                        target_server = next((s for s in servers if s.name == server_name), None)
                        if target_server:
                            # Remap ID back to original
                            remapped_msg = msg.copy()
                            remapped_msg['id'] = original_id
                            await write_lsp_message(target_server.stdin, remapped_msg)
                            log_message(f'[{target_server.name}] -->', remapped_msg)
                        else:
                            log(f"Error: Could not find server {server_name} for response")
                    else:
                        # Unknown response, log error
                        log(f"Warning: Received response with id={id} but no matching request")

        except Exception as e:
            print(f"[dada] Error handling client messages: {e}", file=sys.stderr, flush=True)
        finally:
            # Close all server stdin
            for server in servers:
                server.stdin.close()
                await server.stdin.wait_closed()

    def reconstruct_message(agg_state) -> JSON:
        """Reconstruct full JSONRPC message from aggregation state."""
        if agg_state['id'] is not None:
            # Response
            return {
                'jsonrpc': '2.0',
                'id': agg_state['id'],
                'result': agg_state['aggregate_payload']
            }
        else:
            # Notification
            return {
                'jsonrpc': '2.0',
                'method': agg_state['method'],
                'params': agg_state['aggregate_payload']
            }

    async def handle_aggregation_timeout(agg_key):
        """Handle timeout for an aggregation - send whatever we have."""
        agg_state = pending_aggregations.get(agg_key)
        if agg_state and agg_state['aggregate_payload'] is not None:
            final_msg = reconstruct_message(agg_state)
            await send_to_client(final_msg)
            del pending_aggregations[agg_key]

    async def handle_server_messages(server: ServerProcess):
        """Read from a server and route back to client."""
        nonlocal next_remapped_id
        try:
            while True:
                msg = await read_lsp_message(server.stdout)
                if msg is None:
                    # Server died - check if this was expected
                    if not shutting_down:
                        log(f"Error: Server {server.name} died unexpectedly")
                        raise RuntimeError(f"Server {server.name} crashed")
                    break

                log_message(f'[{server.name}] <--', msg)

                # Distinguish message types
                msg_id = msg.get('id')
                method = msg.get('method')

                # Server request: has both method and id
                if method is not None and msg_id is not None:
                    # This is a request from server to client - remap ID
                    remapped_id = next_remapped_id
                    next_remapped_id += 1
                    server_request_mapping[remapped_id] = (msg_id, server.name)

                    # Forward to client with remapped ID
                    remapped_msg = msg.copy()
                    remapped_msg['id'] = remapped_id
                    await send_to_client(remapped_msg)
                    continue

                # Server notification or response - extract payload
                if method is not None:
                    # Notification - payload is params
                    payload = msg.get('params', {})
                else:
                    # Response - payload is result, lookup method from request tracking
                    payload = msg.get('result')
                    method = requests_needing_aggregation.get(msg_id)

                # Immediate handling (e.g., server name discovery, source attribution)
                payload = router.on_server_message(method, cast(JSON, payload), server)

                # Check if message needs aggregation
                needs_aggregation = False
                agg_key = None
                if msg_id is not None and msg_id in requests_needing_aggregation:
                    # This is a response to a request that was sent to all servers
                    needs_aggregation = True
                    agg_key = ('response', msg_id)
                elif router.should_aggregate(method):
                    # This is a notification that needs aggregation
                    needs_aggregation = True
                    agg_key = router.get_aggregation_key(method, payload)

                if needs_aggregation:
                    agg_state = pending_aggregations.get(agg_key)
                    if agg_state:
                        # Not the first message - aggregate with previous
                        agg_state['aggregate_payload'] = await router.aggregate_payloads(
                            agg_state['method'],
                            agg_state['aggregate_payload'],
                            payload,
                            server
                        )
                        agg_state['received_count'] += 1
                    else:
                        timeout_task = asyncio.create_task(
                            asyncio.sleep(router.get_aggregation_timeout_ms(method) / 1000.0)
                        )
                        agg_state = {
                            'expected_count': len(servers),
                            'received_count': 1,
                            'id': msg_id,
                            'method': method,
                            'aggregate_payload': payload,
                            'timeout_task': timeout_task
                        }
                        pending_aggregations[agg_key] = agg_state;
                        # Setup timeout handler
                        async def timeout_handler():
                            await timeout_task
                            # Check if aggregation still pending (might have completed early)
                            if agg_key in pending_aggregations:
                                await handle_aggregation_timeout(agg_key)
                        asyncio.create_task(timeout_handler())

                    # Check if all messages received
                    if agg_state['received_count'] == agg_state['expected_count']:
                        # Cancel timeout
                        agg_state['timeout_task'].cancel()
                        # Send aggregated result to client
                        final_msg = reconstruct_message(agg_state)
                        await send_to_client(final_msg)
                        del pending_aggregations[agg_key]
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
            print(f"[dada] Error handling messages from {server.name}: {e}", file=sys.stderr, flush=True)
        finally:
            pass

    # Create all tasks
    tasks = [handle_client_messages()]

    for server in servers:
        tasks.append(handle_server_messages(server))

        # Forward stderr
        if not quiet_server:
            tasks.append(forward_server_stderr(server))

    try:
        await asyncio.gather(*tasks)
    except RuntimeError as e:
        # Server crashed unexpectedly
        log(f"Fatal error: {e}")
        sys.exit(1)

    # Wait for all servers to exit
    for server in servers:
        _ = await server.process.wait()


def parse_server_commands(args: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Split args on '--' separators.
    Returns (dada_args, [server_command1, server_command2, ...])
    """
    if '--' not in args:
        return args, []

    # Find all '--' separator indices
    separator_indices = [i for i, arg in enumerate(args) if arg == '--']

    # Everything before first '--' is dada options
    dada_args = args[:separator_indices[0]]

    # Split server commands
    server_commands : list[list[str]] = []
    for i, sep_idx in enumerate(separator_indices):
        # Find start and end of this server command
        start = sep_idx + 1
        end = separator_indices[i + 1] if i + 1 < len(separator_indices) else len(args)

        server_cmd : list[str] = args[start:end]
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
        print("[dada] Usage: dada [--quiet-server] [--delay-ms N] -- <primary-server> [args] [-- <secondary-server> [args]]...", file=sys.stderr)
        sys.exit(1)

    # Parse dada options
    quiet_server = '--quiet-server' in dada_args
    delay_ms = 0

    # Parse --delay-ms option
    if '--delay-ms' in dada_args:
        try:
            delay_idx = dada_args.index('--delay-ms')
            if delay_idx + 1 >= len(dada_args):
                print("[dada] Error: --delay-ms requires a numeric argument", file=sys.stderr)
                sys.exit(1)
            delay_ms = int(dada_args[delay_idx + 1])
            if delay_ms < 0:
                print("[dada] Error: --delay-ms must be non-negative", file=sys.stderr)
                sys.exit(1)
        except (ValueError, IndexError):
            print("[dada] Error: --delay-ms requires a numeric argument", file=sys.stderr)
            sys.exit(1)

    try:
        asyncio.run(run_multiplexer(server_commands, quiet_server=quiet_server, delay_ms=delay_ms))
    except KeyboardInterrupt:
        print("\n[dada] Shutting down...", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[dada] Fatal error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
