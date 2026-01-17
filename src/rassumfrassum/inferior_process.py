# Copyright (C) 2025-2026 João Távora
# Copyright (C) 2026 Felicián Németh
#
# This file is part of rassumfrassum.
#
# Rassumfrassum is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rassumfrassum is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Emacs.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import os
from typing import Optional

from .backend import Backend
from .frassum import Server
from .util import log
from .json import (
    read_message as read_lsp_message,
    write_message as write_lsp_message,
    JSON,
)


class InferiorProcess(Backend):
    """A server subprocess and its associated logical server info."""

    def __init__(self, server_command: list[str], server_index: int):
        basename = os.path.basename(server_command[0])
        # Make name unique by including index for multiple servers
        name = f"{basename}#{server_index}" if server_index > 0 else basename

        self.process = None
        self.server_command = server_command
        self.server = Server(name=name)
        self.server.cookie = self

    def __repr__(self):
        return f"InferiorProcess({self.name})"

    process: asyncio.subprocess.Process
    server_command: list[str]
    server: Server

    async def launch(self):
        """Launch a single LSP server subprocess."""
        log(f"Launching {self.name}: {' '.join(self.server_command)}")

        self.process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    @property
    def stdin(self) -> asyncio.StreamWriter:
        return self.process.stdin  # ty:ignore[invalid-return-type]

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self.process.stdout  # ty:ignore[invalid-return-type]

    @property
    def stderr(self) -> asyncio.StreamReader:
        return self.process.stderr  # ty:ignore[invalid-return-type]

    @property
    def name(self) -> str:
        """Convenience property to access server name."""
        return self.server.name

    async def deliver_message(self, msg: JSON):
        await write_lsp_message(self.stdin, msg)

    async def poll(self) -> Optional[JSON]:
        return await read_lsp_message(self.stdout)

    async def close(self):
        self.stdin.close()
        await self.stdin.wait_closed()

    async def wait_to_exit(self) -> None:
        await self.process.wait()

    async def poll_errors(self) -> Optional[str]:
        line = await self.stderr.readline()
        if not line:
            return

        # Decode and strip only the trailing newline (preserve other whitespace)
        line_str = line.decode("utf-8", errors="replace").rstrip("\n\r")
        return line_str
