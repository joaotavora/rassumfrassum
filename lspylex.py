#!/usr/bin/env python3
"""
lspylex - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import asyncio
import sys
import json
import os
from typing import Optional


async def read_lsp_message(reader: asyncio.StreamReader) -> Optional[dict]:
    """
    Read a single LSP message from the stream.
    LSP uses HTTP-style headers: Content-Length: N\r\n\r\n{json}
    """
    headers = {}

    while True:
        line = await reader.readline()
        if not line:
            return None

        line = line.decode('utf-8').strip()
        if not line:
            # Empty line signals end of headers
            break

        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()

    content_length = headers.get('Content-Length')
    if not content_length:
        return None

    content = await reader.readexactly(int(content_length))
    return json.loads(content.decode('utf-8'))


async def write_lsp_message(writer: asyncio.StreamWriter, message: dict) -> None:
    """
    Write a single LSP message to the stream.
    """
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')

    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    writer.write(header.encode('utf-8'))
    writer.write(content_bytes)
    await writer.drain()


def log_message(direction: str, message: dict) -> None:
    """
    Log a message to stderr with direction indicator.
    direction: '-->' for client->server, '<--' for server->client
    """
    # Determine message type
    if 'method' in message:
        msg_type = message['method']
    elif 'result' in message or 'error' in message:
        msg_type = 'response'
    else:
        msg_type = 'message'

    # Format: [lspylex] --> method_name {...json...}
    json_str = json.dumps(message, ensure_ascii=False)
    print(f"[lspylex] {direction} {msg_type} {json_str}", file=sys.stderr, flush=True)


async def forward_client_to_server(
    client_reader: asyncio.StreamReader,
    server_writer: asyncio.StreamWriter
) -> None:
    """
    Forward messages from client to server.
    """
    try:
        while True:
            message = await read_lsp_message(client_reader)
            if message is None:
                break

            log_message('-->', message)
            await write_lsp_message(server_writer, message)
    except Exception as e:
        print(f"[lspylex] Error in client->server forwarding: {e}", file=sys.stderr, flush=True)
    finally:
        server_writer.close()
        await server_writer.wait_closed()


async def forward_server_to_client(
    server_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    delay_ms: int = 0
) -> None:
    """
    Forward messages from server to client.
    Optionally delays each message by delay_ms milliseconds.
    """
    try:
        while True:
            message = await read_lsp_message(server_reader)
            if message is None:
                break

            log_message('<--', message)

            # Optional delay before forwarding to client
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

            await write_lsp_message(client_writer, message)
    except Exception as e:
        print(f"[lspylex] Error in server->client forwarding: {e}", file=sys.stderr, flush=True)
    finally:
        client_writer.close()
        await client_writer.wait_closed()


async def forward_server_stderr(
    server_stderr: asyncio.StreamReader,
    server_name: str
) -> None:
    """
    Forward server's stderr to our stderr, prefixing each line with the server basename.
    """
    try:
        while True:
            line = await server_stderr.readline()
            if not line:
                break

            # Decode and strip only the trailing newline (preserve other whitespace)
            line_str = line.decode('utf-8', errors='replace').rstrip('\n\r')
            print(f"[{server_name}] {line_str}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[{server_name}] Error reading stderr: {e}", file=sys.stderr, flush=True)


async def run_multiplexer(
    server_command: list[str],
    quiet_server: bool = False,
    delay_ms: int = 0
) -> None:
    """
    Main multiplexer loop.
    """
    # Extract basename for stderr prefixing
    server_basename = os.path.basename(server_command[0])

    print(f"[lspylex] Starting LSP server: {' '.join(server_command)}", file=sys.stderr, flush=True)
    if delay_ms > 0:
        print(f"[lspylex] Delaying server responses by {delay_ms}ms", file=sys.stderr, flush=True)

    # Start the LSP server subprocess
    server_process = await asyncio.create_subprocess_exec(
        *server_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE  # Capture stderr to prefix it
    )

    # Get client streams (stdin/stdout of this process)
    loop = asyncio.get_event_loop()

    client_reader = asyncio.StreamReader()
    client_protocol = asyncio.StreamReaderProtocol(client_reader)
    await loop.connect_read_pipe(lambda: client_protocol, sys.stdin)

    client_writer_transport, client_writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    client_writer = asyncio.StreamWriter(
        client_writer_transport, client_writer_protocol, None, loop
    )

    # Server streams from subprocess
    server_reader = server_process.stdout
    server_writer = server_process.stdin
    server_stderr = server_process.stderr

    # Create bidirectional forwarding tasks
    tasks = [
        forward_client_to_server(client_reader, server_writer),
        forward_server_to_client(server_reader, client_writer, delay_ms),
    ]

    # Only forward server stderr if not suppressed
    if not quiet_server:
        tasks.append(forward_server_stderr(server_stderr, server_basename))

    await asyncio.gather(*tasks, return_exceptions=True)

    # Wait for server to exit
    await server_process.wait()


def main() -> None:
    """
    Parse arguments and start the multiplexer.
    """
    args = sys.argv[1:]

    # Find the '--' separator
    if '--' not in args:
        print("[lspylex] Usage: lspylex [--quiet-server] [--delay-ms N] -- <server-command> [server-args...]", file=sys.stderr)
        sys.exit(1)

    separator_index = args.index('--')
    lspylex_args = args[:separator_index]
    server_command = args[separator_index + 1:]

    if not server_command:
        print("[lspylex] Error: No server command specified after '--'", file=sys.stderr)
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
        asyncio.run(run_multiplexer(server_command, quiet_server=quiet_server, delay_ms=delay_ms))
    except KeyboardInterrupt:
        print("\n[lspylex] Shutting down...", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[lspylex] Fatal error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
