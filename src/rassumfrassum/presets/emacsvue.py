"""Vue preset: vue-language-server + typescript-language-server with relay."""

import subprocess
from pathlib import Path

from rassumfrassum.relay import RelaySpec


def init_options():
    """Resolve TypeScript SDK path and return initializationOptions."""
    try:
        proc = subprocess.run(
            ['pnpm', 'list', '--parseable', 'typescript'],
            capture_output=True, text=True, timeout=10,
        )
        first_line = proc.stdout.strip().split('\n')[-1]
        tsdk_path = str(Path(first_line) / 'lib')
    except Exception:
        tsdk_path = './node_modules/typescript/lib'
    return {'typescript': {'tsdk': tsdk_path}}


def servers():
    """Return vue-language-server."""
    return [
        ['pnpm', 'exec', 'vue-language-server', '--stdio'],
    ]


def relay_servers():
    """Return typescript-language-server as relay target."""
    return [
        ['pnpm', 'exec', 'typescript-language-server', '--stdio'],
    ]


def _resolve_vue_plugin_location() -> str:
    """Resolve the node_modules path containing @vue/typescript-plugin.

    tsserver looks for <probeLocation>/<plugin-name>, so we need to return
    the node_modules directory that contains @vue/typescript-plugin.

    Tries plain `node` first (works with any package manager), then falls
    back to `pnpm exec node` for pnpm's stricter module resolution.
    """
    resolve_script = "require.resolve('@vue/typescript-plugin/package.json')"
    commands = [
        ['node', '-p', resolve_script],
        ['pnpm', 'exec', 'node', '-p', resolve_script],
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
            resolved = result.stdout.strip()
            if not resolved or result.returncode != 0:
                continue
            return _extract_node_modules(resolved)
        except Exception:
            continue
    return ''


def _extract_node_modules(resolved_path: str) -> str:
    """Extract the probe-location node_modules from a resolved package path.

    Handles both pnpm (.pnpm symlink structure) and standard layouts.
    """
    # pnpm: .../node_modules/.pnpm/@vue+.../@vue/typescript-plugin/package.json
    idx = resolved_path.find('/node_modules/.pnpm/')
    if idx >= 0:
        return resolved_path[:idx + len('/node_modules')]
    # Standard: .../node_modules/@vue/typescript-plugin/package.json
    return str(Path(resolved_path).parent.parent.parent)


def relay_spec():
    """Volar v3 tsserver relay specification."""
    plugin_location = _resolve_vue_plugin_location()
    return RelaySpec(
        match_method='tsserver/request',
        send_method='workspace/executeCommand',
        respond_method='tsserver/response',
        command='typescript.tsserverRequest',
        init_options={
            'plugins': [
                {'name': '@vue/typescript-plugin', 'location': plugin_location, 'languages': ['vue']},
            ],
        },
        forward_notifications=[
            'textDocument/didOpen',
            'textDocument/didChange',
            'textDocument/didClose',
        ],
        forward_requests=[
            'textDocument/hover',
            'textDocument/completion',
            'textDocument/signatureHelp',
            'textDocument/definition',
            'textDocument/typeDefinition',
            'textDocument/implementation',
            'textDocument/declaration',
            'textDocument/references',
            'textDocument/codeAction',
        ],
    )
