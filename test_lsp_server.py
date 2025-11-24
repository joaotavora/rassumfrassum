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
    parser.add_argument('--name', default='test-server', help='Server name for serverInfo')
    parser.add_argument('--version', default='1.0.0', help='Server version')
    parser.add_argument('--capabilities', default='basedpyright',
                        choices=['basedpyright', 'ruff'],
                        help='Which capability set to use')
    args = parser.parse_args()

    print(f"{args.name} started", file=sys.stderr, flush=True)

    while True:
        try:
            message = read_message_sync()
            if message is None:
                break

            if 'method' in message:
                method = message['method']

                if method == 'initialize':
                    # Return realistic initialize response
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': {
                            'capabilities': CAPABILITIES[args.capabilities],
                            'serverInfo': {
                                'name': args.name,
                                'version': args.version
                            }
                        }
                    }
                elif method == 'initialized':
                    # Notification - no response needed
                    continue
                elif method == 'shutdown':
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': None
                    }
                else:
                    # Echo other methods
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': f"Echo: {method}"
                    }

                write_message_sync(response)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            break

    print(f"{args.name} stopped", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
