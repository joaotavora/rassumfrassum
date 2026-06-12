"""Vue preset: vue-language-server + tailwindcss-language-server.

With vue-language-server v3, a typescript-language-server (>= 4.4) is
also launched, because v3 no longer runs its own tsserver: it expects
the *client* to broker its 'tsserver/request' notifications over to a
TypeScript server loaded with the '@vue/typescript-plugin' (see
https://github.com/vuejs/language-tools/discussions/5456).  Editors
like Emacs's Eglot don't implement this protocol extension, so this
preset does it for them (Vue3Logic).

With vue-language-server v2, behaves as before: just the Vue and
Tailwind servers, with v2's 'hybridMode' turned off (Vue2Logic).
"""

import asyncio
import json
import os
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import cast

from rassumfrassum.frassum import LspLogic, Server
from rassumfrassum.json import JSON
from rassumfrassum.util import dmerge, warn


@cache
def _vue_server_info() -> tuple[int, str | None]:
    """Find and identify the vue-language-server in PATH.

    Returns (major_version, package_dir) where package_dir is the
    '@vue/language-server' installation directory, suitable as a
    tsserver plugin probe location for '@vue/typescript-plugin' (which
    is a dependency of '@vue/language-server').  Returns (0, None) if
    nothing can be found.
    """
    # Resolve the executable's symlink and walk up to the containing
    # npm package.
    if exe := shutil.which('vue-language-server'):
        for dir in Path(os.path.realpath(exe)).parents:
            pkgjson = dir / 'package.json'
            if not pkgjson.exists():
                continue
            try:
                pkg = json.loads(pkgjson.read_text())
                if pkg.get('name') == '@vue/language-server':
                    return (int(pkg['version'].split('.')[0]), str(dir))
            except (OSError, ValueError, KeyError):
                pass
            break

    # Some installations (e.g. Windows .cmd shims) defeat the above.
    # Ask node to resolve the package from the current project.
    try:
        proc = subprocess.run(
            ['node', '-p', "require.resolve('@vue/language-server/package.json')"],
            capture_output=True, text=True, timeout=10,
        )
        pkgjson = Path(proc.stdout.strip())
        pkg = json.loads(pkgjson.read_text())
        return (int(pkg['version'].split('.')[0]), str(pkgjson.parent))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        pass

    # Last resort: ask the executable itself (no plugin location).
    try:
        proc = subprocess.run(
            ['vue-language-server', '--version'],
            capture_output=True, text=True, timeout=10,
        )
        return (int(proc.stdout.strip().split('.')[0]), None)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return (0, None)


class Vue2Logic(LspLogic):
    """Custom logic for vue-language-server v2 + friends."""

    async def on_client_request(
        self, method: str, params: JSON, servers: list[Server]
    ):
        if method == 'initialize':
            # vue-language server absolutely needs a TypeScript SDK
            # path. Find it via npm
            try:
                proc = await asyncio.create_subprocess_exec(
                    'npm', 'list', '--global', '--parseable', 'typescript',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                first_line = stdout.decode().strip().split('\n')[0]
                tsdk_path = str(Path(first_line) / 'lib')
            except Exception:
                tsdk_path = '/usr/local/lib/node_modules/typescript/lib'

            params['initializationOptions'] = dmerge(
                params.get('initializationOptions') or {},
                {
                    'typescript': {'tsdk': tsdk_path},
                    'vue': {'hybridMode': False},
                },
            )
        return await super().on_client_request(method, params, servers)


# Backward-compatible alias (this used to be the only logic class here)
VueLogic = Vue2Logic


class Vue3Logic(LspLogic):
    """Custom logic for vue-language-server v3 + friends.

    Brokers vue-language-server's 'tsserver/request' protocol
    extension to the typescript-language-server, which answers it via
    the 'typescript.tsserverRequest' command of the
    '@vue/typescript-plugin' loaded into its tsserver.
    """

    def __init__(self, servers: list[Server], *args):
        super().__init__(servers, *args)
        # Order fixed by servers() below
        self.vue = servers[0]
        self.ts = servers[1]

    async def on_client_request(
        self, method: str, params: JSON, servers: list[Server]
    ):
        if method == 'initialize':
            _, location = _vue_server_info()
            params['initializationOptions'] = dmerge(
                params.get('initializationOptions') or {},
                {
                    # Tells typescript-language-server to load the
                    # plugin that makes tsserver understand .vue files.
                    # The other servers ignore this key.
                    'plugins': [
                        {
                            'name': '@vue/typescript-plugin',
                            'location': location,
                            'languages': ['vue'],
                            'configNamespace': 'typescript',
                        }
                    ],
                },
            )
        # In the v3 architecture the TypeScript server, not
        # vue-language-server, answers for the <script> parts of .vue
        # files, so route these to every capable server instead of
        # just the primary.
        elif cap := {
            'textDocument/hover': 'hoverProvider',
            'textDocument/signatureHelp': 'signatureHelpProvider',
        }.get(method):
            return [s for s in servers if s.caps.get(cap) is not None]
        return await super().on_client_request(method, params, servers)

    async def on_server_notification(
        self, method: str, params: JSON, source: Server
    ) -> None:
        if method == 'tsserver/request' and source is self.vue:
            if not isinstance(params, list):
                warn(f"Malformed tsserver/request: {params}")
                return
            for request in params:
                seq, command, payload = (list(request) + [None] * 3)[:3]
                # Each round-trip in its own task: brokering must not
                # block other traffic, and replies may come out of order.
                asyncio.create_task(self._broker(seq, command, payload))
            return
        await super().on_server_notification(method, params, source)

    async def _broker(self, seq, command, payload) -> None:
        """Do one 'tsserver/request' round-trip."""
        is_error, response = await self.request_server(
            self.ts,
            'workspace/executeCommand',
            {
                'command': 'typescript.tsserverRequest',
                'arguments': [command, payload],
            },
        )
        if is_error:
            warn(f"tsserver relay: '{command}' failed: {response}")
        body = None if is_error else (cast(JSON, response) or {}).get('body')
        # Always answer, else vue-language-server hangs forever
        await self.notify_server(self.vue, 'tsserver/response', [[seq, body]])


def servers():
    """Vue + Tailwind servers, plus TypeScript for vue-language-server v3."""
    major, _ = _vue_server_info()
    vue = ['vue-language-server', '--stdio']
    tailwind = ['tailwindcss-language-server', '--stdio']
    if major >= 3:
        if shutil.which('typescript-language-server') is None:
            warn(
                "vue-language-server v3 needs typescript-language-server"
                " (>= 4.4) in PATH.  Try"
                " 'npm install -g typescript-language-server'."
            )
        return [vue, ['typescript-language-server', '--stdio'], tailwind]
    if major == 0:
        warn("Can't find/identify vue-language-server, assuming v2")
    return [vue, tailwind]


def logic_class():
    """Vue3Logic or Vue2Logic, depending on the installed server."""
    major, _ = _vue_server_info()
    return Vue3Logic if major >= 3 else Vue2Logic
