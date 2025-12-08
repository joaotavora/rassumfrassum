"""Vue preset: vue-language-server + tailwindcss-language-server with custom logic."""

import subprocess
from pathlib import Path

from rassumfrassum.frassum import LspLogic, Server
from rassumfrassum.json import JSON
from rassumfrassum.util import dmerge


class VueLogic(LspLogic):
    """Custom logic LSP for Vue-friendly servers."""

    def on_client_request(
        self, method: str, params: JSON, servers: list[Server]
    ):
        if method == 'initialize':
            # vue-language server absolutely needs a TypeScript SDK
            # path. Find it via npm
            try:
                npm_output = subprocess.run(
                    ['npm', 'list', '--global', '--parseable', 'typescript'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                first_line = npm_output.stdout.strip().split('\n')[0]
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
        return super().on_client_request(method, params, servers)


def get_servers():
    """Return vue-language-server and tailwindcss-language-server."""
    return [
        ['vue-language-server', '--stdio'],
        ['tailwindcss-language-server', '--stdio'],
    ]


def get_logic_class():
    """Use custom VueLogic."""
    return VueLogic
