"""
Server process wrapper.
"""

import asyncio
from dataclasses import dataclass

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
