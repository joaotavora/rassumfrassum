#!/usr/bin/env python3
"""
A very silly dummy server for testing
"""

import sys
from pathlib import Path

parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from jsonrpc import read_message_sync, write_message_sync, JSON
import argparse
from typing import cast

def log(_prefix : str, s : str):
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


def main():
    parser = argparse.ArgumentParser(description='Test LSP server')
    _ = parser.add_argument('--name', default='test-server', help='Server name for serverInfo')
    _ = parser.add_argument('--version', default='1.0.0', help='Server version')
    _ = parser.add_argument('--capabilities', default='basedpyright',
                        choices=['basedpyright', 'ruff'],
                        help='Which capability set to use')
    _ = parser.add_argument('--publish-diagnostics', action='store_true',
                        help='Send diagnostics after didOpen')
    args = parser.parse_args()

    name = cast(str, args.name);

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
                        'capabilities': CAPABILITIES[cast(str, args.capabilities)],
                        'serverInfo': {
                            'name': name,
                            'version': cast(str, args.version)
                        }
                    }
                }
                write_message_sync(response)

            elif method == 'shutdown':
                # Reply to shutdown and exit
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

            elif method == 'textDocument/didOpen' and cast(bool, args.publish_diagnostics):
                # Handle didOpen and publish diagnostics
                params = cast(JSON, message.get('params', {}))
                text_doc = cast(JSON, params.get('textDocument', {}))
                uri = cast(str, text_doc.get('uri', 'file:///unknown'))

                log(name, f"got notification {method}")

                # Publish diagnostics for this file
                diagnostic_notification = {
                    'jsonrpc': '2.0',
                    'method': 'textDocument/publishDiagnostics',
                    'params': {
                        'uri': uri,
                        'diagnostics': [
                            {
                                'range': {
                                    'start': {'line': 0, 'character': 0},
                                    'end': {'line': 0, 'character': 5}
                                },
                                'severity': 1,  # Error
                                'message': f'An example error from {name}'
                            },
                            {
                                'range': {
                                    'start': {'line': 0, 'character': 7},
                                    'end': {'line': 0, 'character': 12}
                                },
                                'severity': 2,  # Warning
                                'message': f'An example warning from {name}'
                            }
                        ]
                    }
                }
                write_message_sync(diagnostic_notification)
                log(name, f"published diagnostics for {uri}")

            else:
                # Log all other requests and notifications
                if msg_id is not None:
                    log(name, f"request {method} (id={msg_id})")
                else:
                    log(name, f"notification {method}")

        except Exception as e:
            log(name, f"Error: {e}")
            break

    log(name, f"stopped")


if __name__ == '__main__':
    main()
