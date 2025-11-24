#!/usr/bin/env python3
"""
A configurable test LSP server for testing lspylex.
"""
import sys
import argparse
from jsonrpc import read_message_sync, write_message_sync

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

    print(f"Started!", file=sys.stderr, flush=True)

    while True:
        try:
            message = read_message_sync()
            if message is None:
                break

            method = message.get('method')
            msg_id = message.get('id')

            if method == 'initialize':
                # Return "realistic" initialize response
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': {
                        'capabilities': CAPABILITIES[args.capabilities],
                        'serverInfo': {
                            'name': args.name,
                            'version': args.version
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
                print(f"{args.name} shutting down", file=sys.stderr, flush=True)
                break

            elif method == 'textDocument/didOpen' and args.publish_diagnostics:
                # Handle didOpen and publish diagnostics
                params = message.get('params', {})
                text_doc = params.get('textDocument', {})
                uri = text_doc.get('uri', 'file:///unknown')

                print(f"got notification {method}", file=sys.stderr, flush=True)

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
                                'message': f'An example error from {args.name}'
                            },
                            {
                                'range': {
                                    'start': {'line': 0, 'character': 7},
                                    'end': {'line': 0, 'character': 12}
                                },
                                'severity': 2,  # Warning
                                'message': f'An example warning from {args.name}'
                            }
                        ]
                    }
                }
                write_message_sync(diagnostic_notification)
                print(f"published diagnostics for {uri}", file=sys.stderr, flush=True)

            else:
                # Log all other requests and notifications
                if msg_id is not None:
                    print(f"request {method} (id={msg_id})", file=sys.stderr, flush=True)
                else:
                    print(f"notification {method}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            break

    print(f"stopped", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
