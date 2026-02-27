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

    Uses pnpm exec to resolve through pnpm's module resolution, then
    extracts the project-level node_modules as the probe location.
    tsserver looks for <probeLocation>/<plugin-name>, so passing the
    project's node_modules lets it find the plugin via pnpm's symlink.
    """
    try:
        result = subprocess.run(
            ['pnpm', 'exec', 'node', '-p',
             "require.resolve('@vue/typescript-plugin/package.json')"],
            capture_output=True, text=True, timeout=10,
        )
        resolved = result.stdout.strip()
        # In pnpm: .../node_modules/.pnpm/@vue+.../@vue/typescript-plugin/package.json
        # Extract the project-level node_modules (before .pnpm)
        idx = resolved.find('/node_modules/.pnpm/')
        if idx >= 0:
            return resolved[:idx + len('/node_modules')]
        # Non-pnpm: .../node_modules/@vue/typescript-plugin/package.json
        # Go up 3 levels to get node_modules
        return str(Path(resolved).parent.parent.parent)
    except Exception:
        return ''


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
