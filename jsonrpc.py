"""
Generic JSONRPC message reading/writing using LSP framing.
LSP uses HTTP-style headers: Content-Length: N\r\n\r\n{json}
"""

import json
import asyncio
import sys
from typing import Any


async def read_message(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    """
    Read a single JSONRPC message from an async stream.
    Returns None on EOF.
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


async def write_message(writer: asyncio.StreamWriter, message: dict) -> None:
    """
    Write a single JSONRPC message to an async stream.
    """
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')

    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    writer.write(header.encode('utf-8'))
    writer.write(content_bytes)
    await writer.drain()


def read_message_sync(stream=None) -> dict[str, Any] | None:
    """
    Read a single JSONRPC message from stdin (or provided stream) synchronously.
    Returns None on EOF.
    """
    if stream is None:
        stream = sys.stdin.buffer

    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.decode('utf-8').strip()
        if not line:
            break
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()

    content_length = int(headers.get('Content-Length', 0))
    if content_length == 0:
        return None

    content = stream.read(content_length)
    return json.loads(content.decode('utf-8'))


def write_message_sync(message: dict, stream=None) -> None:
    """
    Write a single JSONRPC message to stdout (or provided stream) synchronously.
    """
    if stream is None:
        stream = sys.stdout.buffer

    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')
    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    stream.write(header.encode('utf-8'))
    stream.write(content_bytes)
    stream.flush()
