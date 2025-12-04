"""
Generic JSONRPC message reading/writing using LSP framing.
LSP uses HTTP-style headers: Content-Length: N\r\n\r\n{json}
"""

import json
import asyncio
import sys
from typing import BinaryIO, cast, Any

JSON = dict[str, Any]

async def read_message(reader: asyncio.StreamReader) -> JSON | None:
    """
    Read a single JSONRPC message from an async stream.
    Returns None on EOF.
    """
    headers: dict[str, str] = {}

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
    return cast(JSON, json.loads(content.decode('utf-8')))


async def write_message(writer: asyncio.StreamWriter, message: JSON) -> None:
    """
    Write a single JSONRPC message to an async stream.
    """
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')

    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    writer.write(header.encode('utf-8'))
    writer.write(content_bytes)
    await writer.drain()


def read_message_sync(stream: BinaryIO = sys.stdin.buffer) -> JSON | None:
    """
    Read a single JSONRPC message from stdin (or provided stream) synchronously.
    Returns None on EOF.
    """
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line_str = line.decode('utf-8').strip()
        if not line_str:
            break
        if ':' in line_str:
            key, value = line_str.split(':', 1)
            headers[key.strip()] = value.strip()
    content_length = int(headers.get('Content-Length', '0'))
    if content_length == 0:
        return None
    content = stream.read(content_length)
    return cast(JSON, json.loads(content.decode('utf-8')))


def write_message_sync(message: JSON, stream : BinaryIO = sys.stdout.buffer) -> None:
    """
    Write a single JSONRPC message to stdout (or provided stream) synchronously.
    """
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')
    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    _ = stream.write(header.encode('utf-8'))
    _ = stream.write(content_bytes)
    _ = stream.flush()
