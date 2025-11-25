#!/usr/bin/env python3
"""
A more complete test client that exercises various LSP messages.
"""

import sys
from pathlib import Path

parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from jsonrpc import read_message_sync, write_message_sync
from utils import log, JSON

def send_and_log(message : JSON, description : str):
    """Send a message and log what we're doing."""
    log("client", description)
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

    msg = read_message_sync()
    log("client", f"Hopefully got initialize response {msg}")

    # 2. Initialized notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized notification")

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

    msg = read_message_sync()
    log("client", f"Hopefully got diagnostics {msg}")

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

    msg = read_message_sync()
    log("client", f"Hopefully got hover response {msg}")

    # 5. Shutdown
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    msg = read_message_sync()
    log("client", f"Hopefully got shutdown response {msg}")

    # 6. Exit notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    log("client", "done!")

if __name__ == '__main__':
    main()
