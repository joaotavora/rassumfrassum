"""Vue preset: vue-language-server + tailwindcss-language-server with custom logic."""

import asyncio
from pathlib import Path

from rassumfrassum.frassum import LspLogic, Server
from rassumfrassum.json import JSON
from rassumfrassum.util import dmerge


class VueLogic(LspLogic):
    """Custom logic LSP for Vue-friendly servers."""

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


def servers():
    """Return vue-language-server and tailwindcss-language-server."""
    return [
        ['vue-language-server', '--stdio'],
        ['tailwindcss-language-server', '--stdio'],
    ]


def logic_class():
    """Use custom VueLogic."""
    return VueLogic
