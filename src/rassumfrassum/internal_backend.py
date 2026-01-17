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
from typing import Optional

from .backend import Backend
from .frassum import Server
from .json import JSON
from .util import trace, log_levels, set_log_level_from_string


class InternalBackend(Backend):
    """Rassumfrassum's own LSP server."""

    def __init__(self):
        self.server = Server(name='internal')
        self.server.cookie = self
        self.queue = asyncio.Queue()  # For s->c messages.
        self.message_id = 0  # Outgoing message-id (s->c).
        self.pending_requests = {}  # Direction: s->c.

    def __repr__(self):
        return f"InternalBackend({self.name})"

    server: Server

    @property
    def name(self) -> str:
        """Convenience property to access server name."""
        return self.server.name

    async def deliver_message(self, msg: JSON):
        if not msg.get('id'):
            # msg is notification.
            return
        if msg.get('result'):
            callback = self.pending_requests[msg['id']]
            callback(msg['result'])
            del self.pending_requests[msg['id']]
            return
        method = msg.get('method', '').replace('/', '_')
        try:
            handler = getattr(self, f'handle_{method}')
        except AttributeError:
            trace(f'method not implemented: {method}')
            return
        self.outgoing_messages = []
        response = {
            'jsonrpc': '2.0',
            'id': msg['id'],
            'result': handler(msg.get('params', {})),
        }
        outgoing_messages = self.outgoing_messages
        await self.queue.put(response)
        for msg in outgoing_messages:
            await self.queue.put(msg)

    def queue_outgoing_request(self, request, callback):
        """Queue a request, method and params must already be set.
        Call 'callback' with the result."""
        self.message_id += 1
        request.update({
            'jsonrpc': '2.0',
            'id': self.message_id,
        })
        self.pending_requests[self.message_id] = callback
        self.outgoing_messages.append(request)

    async def poll(self) -> Optional[JSON]:
        return await self.queue.get()

    async def close(self):
        await self.queue.put(None)

    async def wait_to_exit(self) -> None:
        pass

    async def poll_errors(self) -> Optional[str]:
        pass

    def handle_initialize(self, params):
        capabilities = {
            # TODO: We can collect the commands with dir().
            'executeCommandProvider': ['rassumfrassum.set-log-level'],
        }
        obj = params
        for f in ['capabilities', 'textDocument', 'codeActionLiteralSupport']:
            obj = obj.get(f, {})
        if obj:
            # LSP spec: "The `CodeActionOptions` return type is
            # only valid if the client signals code action literal
            # support"
            capabilities['codeActionProvider'] = {""}
        else:
            capabilities['codeActionProvider'] = True

        return {
            'capabilities': capabilities,
            'serverInfo': {
                'name': 'Rassumfrassum',
                'version': 'N/A',  # Must return something, otherwise
                                   # the aggregated names/versions
                                   # miss-aligns.
            },
        }

    def handle_textDocument_codeAction(self, params):
        """Return code-action 'set-log-level' if point in the first line."""
        def recursive_get(d, keys):
            if keys:
                key = keys.pop(0)
                return recursive_get(d.get(key, {}), keys)
            return d

        start_line = recursive_get(params, ['range', 'start', 'line'])
        if start_line != 0:
            return []
        return [{
            'title': 'Rassumfrassum: set log-level',
            'kind': '',  # Empty codeActionKind
            'command': {
                'title': 'Rassumfrassum: set log-level',
                'command': 'rassumfrassum.set-log-level',
            }
        }]

    def handle_workspace_executeCommand(self, params):
        cmd = params.get('command', '')
        args = params.get('arguments')
        method = cmd.replace('-', '_').replace('.', '_')
        try:
            handler = getattr(self, f'execute_{method}')
        except AttributeError:
            # We should not receive commands that we do not advertise.
            raise Exception(f'unknown command: {cmd}')
        return handler(args)

    def handle_shutdown(self, _params):
        return {}

    def execute_rassumfrassum_set_log_level(self, _args):
        actions = []
        for level in log_levels:
            actions.append({'title': level[4:]})
        self.queue_outgoing_request({
            'method': 'window/showMessageRequest',
            'params': {
                'type': 3,  # Info
                'message': 'Select the new log-level',
                'actions': actions,
            },
        }, callback=self.set_log_level)
        return {}

    def set_log_level(self, result):
        if result.get('title'):
            set_log_level_from_string(f'LOG_{result["title"]}')
