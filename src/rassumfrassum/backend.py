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


from abc import ABC, abstractmethod
from typing import Optional
from .frassum import Server
from .json import JSON


class Backend(ABC):
    server: Server

    @abstractmethod
    def name(self) -> str:
        """Return the name of the backend."""

    @abstractmethod
    def deliver_message(self, message: JSON) -> None:
        """Deliver an LSP message to this backend."""

    @abstractmethod
    def poll(self) -> Optional[JSON]:
        """Return the next LSP message from this backend, if any."""

    @abstractmethod
    async def close(self) -> None:
        """Close server intput stream, initiating a shutdown."""

    @abstractmethod
    async def wait_to_exit(self) -> None:
        """Wait backend to exit."""

    @abstractmethod
    async def poll_errors(self) -> Optional[str]:
        """Return potential error messages of the backend."""
