"""TypeScript preset: typescript-language-server + oxlint."""

import os

from rassumfrassum.frassum import LspLogic, Server
from rassumfrassum.json import JSON
from rassumfrassum.util import dmerge, info
from typing import cast, Any


def _find_workspace_folder(scope_uri: str) -> dict | None:
    """Find workspace folder by searching for package.json from scopeUri."""
    if not scope_uri.startswith('file://'):
        return None

    file_path = scope_uri[7:]  # Remove 'file://'
    current_dir = os.path.dirname(file_path)

    while current_dir and current_dir != '/':
        if os.path.exists(os.path.join(current_dir, 'package.json')):
            return {
                'uri': f'file://{current_dir}',
                'name': os.path.basename(current_dir),
            }
        parent = os.path.dirname(current_dir)
        if parent == current_dir:  # Reached root
            break
        current_dir = parent

    return None


def _oxlint_config(workspace_folder: dict | None = None) -> dict:
    """Return base oxlint configuration."""
    config = {
        'run': 'onType',
        'configPath': '',
    }
    if workspace_folder:
        config['workspaceFolder'] = workspace_folder
    return config


class TypeScriptOxlintLogic(LspLogic):
    """Custom logic for TypeScript + oxlint servers."""

    async def on_client_response(
        self,
        method: str,
        request_params: JSON,
        response_payload: JSON,
        is_error: bool,
        server: Server,
    ) -> None:
        """Enrich workspace/configuration responses for oxlint."""
        if (
            method == 'workspace/configuration'
            and not is_error
            and 'oxlint' in server.name.lower()
        ):
            info("Enriching workspace/configuration for oxlint")
            req_items = request_params.get('items', [])
            res_items = cast(list[Any], response_payload)
            if len(res_items) < len(req_items):
                res_items.extend([None] * (len(req_items) - len(res_items)))

            for i, item in enumerate(req_items):
                section = item.get('section', '')
                if section == '':
                    wfolder = _find_workspace_folder(item.get('scopeUri', ''))
                    cfg = _oxlint_config(wfolder)

                    if isinstance(res_items[i], dict):
                        res_items[i] = dmerge(res_items[i], cfg)
                    else:
                        res_items[i] = cfg

        await super().on_client_response(
            method, request_params, response_payload, is_error, server
        )


def servers():
    """Return typescript-language-server + oxlint."""
    return [
        ['typescript-language-server', '--stdio'],
        ['oxlint', '--lsp'],
    ]


def logic_class():
    """Use custom TypeScriptOxlintLogic."""
    return TypeScriptOxlintLogic
