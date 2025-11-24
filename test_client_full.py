#!/usr/bin/env python3
"""
A more complete test client that exercises various LSP messages.
"""
import sys
from jsonrpc import read_message_sync, write_message_sync


def send_and_log(message, description):
    """Send a message and log what we're doing."""
    print(f"\n==> {description}", file=sys.stderr)
    write_message_sync(message)


def main():
    """Send a sequence of LSP messages."""

    # 1. Initialize
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    response = read_message_sync()
    print(f"<== Got initialize response", file=sys.stderr)

    # 2. Initialized notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized notification")

    # 3. didOpen notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didOpen',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'languageId': 'python',
                'version': 1,
                'text': 'print("hello")\n'
            }
        }
    }, "Sending didOpen notification")

    # 4. Hover request
    send_and_log({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'textDocument/hover',
        'params': {
            'textDocument': {'uri': 'file:///tmp/test.py'},
            'position': {'line': 0, 'character': 0}
        }
    }, "Sending hover request")

    # 5. Shutdown
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    response = read_message_sync()
    print(f"<== Got shutdown response", file=sys.stderr)

    # 6. Exit notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    print("\nDone!", file=sys.stderr)


if __name__ == '__main__':
    main()
