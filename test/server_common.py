#!/usr/bin/env python3
"""
Common server utilities for testing
"""

import sys
import time
from pathlib import Path
from typing import Callable, cast

project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from jaja import JSON, read_message_sync, write_message_sync

def log(prefix: str, s: str):
    print(f"{s}", file=sys.stderr)

# Realistic capability responses based on real LSP servers
CAPABILITIES = {
    'basedpyright': {
        'textDocumentSync': {'willSave': True, 'change': 2, 'openClose': True},
        'definitionProvider': {'workDoneProgress': True},
        'hoverProvider': {'workDoneProgress': True},
        'completionProvider': {
            'triggerCharacters': ['.', '[', '"', "'"],
            'resolveProvider': True,
            'workDoneProgress': True
        },
        'signatureHelpProvider': {'triggerCharacters': ['(', ',', ')']},
        'codeActionProvider': {'codeActionKinds': ['quickfix', 'source.organizeImports']},
    },
    'ruff': {
        'codeActionProvider': {
            'codeActionKinds': [
                'quickfix',
                'source.fixAll.ruff',
                'source.organizeImports.ruff'
            ],
            'resolveProvider': True
        },
        'diagnosticProvider': {'identifier': 'Ruff', 'interFileDependencies': False},
        'documentFormattingProvider': True,
        'documentRangeFormattingProvider': True,
        'hoverProvider': True,
        'textDocumentSync': {'change': 2, 'openClose': True}
    }
}

def make_diagnostic(line: int, char_start: int, char_end: int,
                    severity: int, message: str, source: str | None = None) -> JSON:
    """Create a diagnostic object."""
    diag: JSON = {
        'range': {
            'start': {'line': line, 'character': char_start},
            'end': {'line': line, 'character': char_end}
        },
        'severity': severity,
        'message': message
    }
    if source:
        diag['source'] = source
    return diag


def run_server(
    name: str,
    version: str = '1.0.0',
    capabilities: str = 'basedpyright',
    on_didopen: Callable[[str, JSON], None] | None = None,
    on_didchange: Callable[[str, JSON], None] | None = None,
    on_initialized: Callable[[], None] | None = None
) -> None:
    """
    Run a generic LSP server for testing.

    Args:
        name: Server name for serverInfo
        version: Server version
        capabilities: Which capability set to use ('basedpyright' or 'ruff')
        on_didopen: Callback for textDocument/didOpen notifications (uri, text_doc)
        on_didchange: Callback for textDocument/didChange notifications (uri, text_doc)
        on_initialized: Callback for initialized notification
    """

    log(name, "Started!")

    while True:
        try:
            message = read_message_sync()
            if message is None:
                break

            method = message.get('method')
            msg_id = message.get('id')

            if method == 'initialize':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': {
                        'capabilities': CAPABILITIES[capabilities],
                        'serverInfo': {
                            'name': name,
                            'version': version
                        }
                    }
                }
                write_message_sync(response)

            elif method == 'shutdown':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': None
                }
                write_message_sync(response)
                log(name, "shutting down")
                break

            elif method == 'textDocument/hover':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': {
                        "contents": {
                            "kind": "markdown",
                            "value": "oh yeah "
                        },
                        "range": {
                            "start": {"line": 0, "character": 5 },
                            "end": {"line": 0, "character": 10 }
                        }
                    }
                }
                write_message_sync(response)

            elif method == 'textDocument/didOpen' and on_didopen:
                params = cast(JSON, message.get('params', {}))
                text_doc = cast(JSON, params.get('textDocument', {}))
                uri = cast(str, text_doc.get('uri', 'file:///unknown'))
                log(name, f"got notification {method}")
                on_didopen(uri, text_doc)

            elif method == 'textDocument/didChange' and on_didchange:
                params = cast(JSON, message.get('params', {}))
                text_doc = cast(JSON, params.get('textDocument', {}))
                uri = cast(str, text_doc.get('uri', 'file:///unknown'))
                log(name, f"got notification {method}")
                on_didchange(uri, text_doc)

            elif method == 'initialized':
                log(name, f"got notification {method}")
                if on_initialized:
                    on_initialized()

            elif msg_id == 999 and method is None:
                log(name, f"Got response to workspace/configuration request: {message}")
                # Validate response and send notification if correct
                result = message.get('result')
                if (isinstance(result, list) and len(result) == 1 and
                    isinstance(result[0], dict) and result[0].get('pythonPath') == '/usr/bin/python3'):
                    # Response is correct, send success notification
                    write_message_sync({
                        'jsonrpc': '2.0',
                        'method': 'custom/requestResponseOk',
                        'params': {'server': name}
                    })
                    log(name, "Response validation passed, sent success notification")
                else:
                    log(name, f"Response validation FAILED: {result}")

            else:
                if msg_id is not None:
                    log(name, f"request {method} (id={msg_id})")
                else:
                    log(name, f"notification {method}")

        except Exception as e:
            log(name, f"Error: {e}")
            break

    log(name, "stopped")
