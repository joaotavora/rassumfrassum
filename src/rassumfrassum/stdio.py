"""Cross-platform asyncio-compatible stdin/stdout.

On Windows, this is unfortunately more complicated
"""

import asyncio
import platform
import socket
import sys
import threading


async def create_stdin_reader() -> asyncio.StreamReader:
    """Create an asyncio StreamReader for stdin.

    On Windows: Uses run_in_executor with blocking reads.
    On Unix: Direct connection to sys.stdin.
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()

    if platform.system() == 'Windows':
        # Windows: Use run_in_executor to avoid pipe issues
        async def read_stdin_loop():
            def blocking_read1():
                """Blocking read1 from stdin buffer - reads available data."""
                try:
                    # read1() reads whatever is available, doesn't block for full buffer
                    return sys.stdin.buffer.read1(4096)
                except Exception:
                    return b''

            try:
                while True:
                    chunk = await loop.run_in_executor(None, blocking_read1)
                    if not chunk:
                        break
                    reader.feed_data(chunk)
                reader.feed_eof()
            except Exception:
                reader.feed_eof()

        # Start the reading task in the background
        asyncio.create_task(read_stdin_loop())
        return reader
    else:
        # Unix: Direct connection works fine
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        return reader


class _WindowsStdoutWriter:
    """A StreamWriter-like wrapper for Windows stdout using run_in_executor."""

    def __init__(self, loop):
        self._loop = loop
        self._buffer = bytearray()

    def write(self, data):
        """Add data to the buffer."""
        self._buffer.extend(data)

    async def drain(self):
        """Flush the buffer to stdout using run_in_executor."""
        if not self._buffer:
            return

        data = bytes(self._buffer)
        self._buffer.clear()

        def blocking_write(data):
            """Blocking write to stdout buffer - runs in thread pool."""
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except Exception:
                pass

        await self._loop.run_in_executor(None, blocking_write, data)

    def close(self):
        """Close the writer."""
        pass

    async def wait_closed(self):
        """Wait for close to complete."""
        pass


async def create_stdout_writer() -> asyncio.StreamWriter:
    """Create an asyncio StreamWriter for stdout.

    On Windows: Uses run_in_executor with blocking writes.
    On Unix: Direct connection to sys.stdout.
    """
    loop = asyncio.get_event_loop()

    if platform.system() == 'Windows':
        # Windows: Use custom wrapper with run_in_executor
        return _WindowsStdoutWriter(loop)
    else:
        # Unix: Direct connection works fine
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(transport, protocol, None, loop)
        return writer
