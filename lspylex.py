#!/usr/bin/env python3
"""
lspylex - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import json
import asyncio
import sys
import os
from dataclasses import dataclass

from lsp_router import MessageRouter
from jsonrpc import read_message as read_lsp_message, write_message as write_lsp_message, JSON
from typing import cast

def log(s : str):
    print(f"[lspylex] {s}", file=sys.stderr)

@dataclass
class ServerProcess:
    """Information about a running server subprocess."""
    name: str
    process: asyncio.subprocess.Process

    @property
    def stdin(self) -> asyncio.StreamWriter:
        return self.process.stdin  # pyright: ignore[reportReturnType]

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self.process.stdout  # pyright: ignore[reportReturnType]

    @property
    def stderr(self) -> asyncio.StreamReader:
        return self.process.stderr  # pyright: ignore[reportReturnType]

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

    # Format: [lspylex] --> method_name {...json...}
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

    print(f"[lspylex] Launching {name}: {' '.join(server_command)}", file=sys.stderr, flush=True)

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

    print(f"[lspylex] Primary server: {servers[0].name}", file=sys.stderr, flush=True)
    if len(servers) > 1:
        secondaries = [s.name for s in servers[1:]]
        print(f"[lspylex] Secondary servers: {', '.join(secondaries)}", file=sys.stderr, flush=True)
    if delay_ms > 0:
        print(f"[lspylex] Delaying server responses by {delay_ms}ms", file=sys.stderr, flush=True)

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
        try:
            while True:
                msg = await read_lsp_message(client_reader)
                if msg is None:
                    break

                log_message('-->', msg)

                # Route based on message type
                if router.is_notification(msg):
                    # Broadcast all notifications to all servers
                    for server in servers:
                        await write_lsp_message(server.stdin, msg)
                else:
                    # Request - check if it should go to all servers
                    method = cast(str, msg.get('method'))
                    client_id = cast(int, msg.get('id'))

                    if router.should_route_to_all(method):
                        # Send to all servers with original ID
                        for server in servers:
                            await write_lsp_message(server.stdin, msg)
                            log_message(f'[{server.name}] -->', msg)

                        # Track for merging
                        router.track_merge_request(client_id, method, len(servers))
                    else:
                        # Send only to primary server with original ID
                        await write_lsp_message(servers[0].stdin, msg)
                        log_message(f'[{servers[0].name}] -->', msg)

        except Exception as e:
            print(f"[lspylex] Error handling client messages: {e}", file=sys.stderr, flush=True)
        finally:
            # Close all server stdin
            for server in servers:
                server.stdin.close()
                await server.stdin.wait_closed()

    async def handle_server_messages(server: ServerProcess):
        """Read from a server and route back to client."""
        try:
            while True:
                msg = await read_lsp_message(server.stdout)
                if msg is None:
                    break

                log_message(f'[{server.name}] <--', msg)

                # Immediate handling (e.g., server name discovery)
                router.on_server_message(server, msg)

                # Check if message needs aggregation
                if router.should_aggregate(msg):
                    is_complete, aggregated = await router.aggregate_message(server, msg)
                    if is_complete:
                        assert aggregated
                        # Restore ID for responses
                        if 'id' in msg:
                            aggregated['id'] = msg.get('id')
                        await send_to_client(aggregated)
                else:
                    # Forward immediately to client
                    await send_to_client(msg)

        except Exception as e:
            print(f"[lspylex] Error handling messages from {server.name}: {e}", file=sys.stderr, flush=True)
        finally:
            pass

    # Create all tasks
    tasks = [handle_client_messages()]

    for server in servers:
        tasks.append(handle_server_messages(server))

        # Forward stderr
        if not quiet_server:
            tasks.append(forward_server_stderr(server))

    _ = await asyncio.gather(*tasks, return_exceptions=True)

    # Wait for all servers to exit
    for server in servers:
        _ = await server.process.wait()


def parse_server_commands(args: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Split args on '--' separators.
    Returns (lspylex_args, [server_command1, server_command2, ...])
    """
    if '--' not in args:
        return args, []

    # Find all '--' separator indices
    separator_indices = [i for i, arg in enumerate(args) if arg == '--']

    # Everything before first '--' is lspylex options
    lspylex_args = args[:separator_indices[0]]

    # Split server commands
    server_commands : list[list[str]] = []
    for i, sep_idx in enumerate(separator_indices):
        # Find start and end of this server command
        start = sep_idx + 1
        end = separator_indices[i + 1] if i + 1 < len(separator_indices) else len(args)

        server_cmd : list[str] = args[start:end]
        if server_cmd:  # Only add non-empty commands
            server_commands.append(server_cmd)

    return lspylex_args, server_commands


def main() -> None:
    """
    Parse arguments and start the multiplexer.
    """
    args = sys.argv[1:]

    # Parse multiple '--' separators for multiple servers
    lspylex_args, server_commands = parse_server_commands(args)

    if not server_commands:
        print("[lspylex] Usage: lspylex [--quiet-server] [--delay-ms N] -- <primary-server> [args] [-- <secondary-server> [args]]...", file=sys.stderr)
        sys.exit(1)

    # Parse lspylex options
    quiet_server = '--quiet-server' in lspylex_args
    delay_ms = 0

    # Parse --delay-ms option
    if '--delay-ms' in lspylex_args:
        try:
            delay_idx = lspylex_args.index('--delay-ms')
            if delay_idx + 1 >= len(lspylex_args):
                print("[lspylex] Error: --delay-ms requires a numeric argument", file=sys.stderr)
                sys.exit(1)
            delay_ms = int(lspylex_args[delay_idx + 1])
            if delay_ms < 0:
                print("[lspylex] Error: --delay-ms must be non-negative", file=sys.stderr)
                sys.exit(1)
        except (ValueError, IndexError):
            print("[lspylex] Error: --delay-ms requires a numeric argument", file=sys.stderr)
            sys.exit(1)

    try:
        asyncio.run(run_multiplexer(server_commands, quiet_server=quiet_server, delay_ms=delay_ms))
    except KeyboardInterrupt:
        print("\n[lspylex] Shutting down...", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[lspylex] Fatal error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
