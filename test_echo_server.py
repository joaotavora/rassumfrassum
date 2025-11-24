#!/usr/bin/env python3
"""
A simple echo server that mimics LSP protocol for testing.
"""
import sys
from jsonrpc import read_message_sync, write_message_sync


def main():
    """Echo back any message received."""
    print("Echo server started", file=sys.stderr, flush=True)

    while True:
        try:
            message = read_message_sync()
            if message is None:
                break

            # Echo it back with a modification to show it went through
            if 'method' in message:
                if message['method'] == 'initialize':
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': {
                            'capabilities': {
                                'textDocumentSync': 2,
                                'hoverProvider': True,
                                'definitionProvider': True,
                            },
                            'serverInfo': {'name': 'test-server-1', 'version': '1.0'}
                        }
                    }
                else:
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': f"Echo: {message['method']}"
                    }
            else:
                response = message

            write_message_sync(response)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            break

    print("Echo server stopped", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
