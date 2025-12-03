#!/usr/bin/env python3
"""
Test client that handles server requests.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, do_shutdown, send_and_log, log
from jaja import read_message_sync, write_message_sync

def main():
    """Send a sequence of LSP messages and handle server requests."""

    do_initialize()
    do_initialized()

    # After initialized, we expect server requests for workspace/configuration
    # Handle requests from both servers
    for i in range(2):
        msg = read_message_sync()
        assert msg is not None, f"Expected server request {i+1}"
        assert 'method' in msg, f"Expected method in server request: {msg}"
        assert 'id' in msg, f"Expected id in server request: {msg}"
        assert msg.get('method') == 'workspace/configuration', f"Expected workspace/configuration request: {msg}"
        log("client", f"Got server request: {msg}")

        # Send response to server request
        response = {
            'jsonrpc': '2.0',
            'id': msg['id'],
            'result': [{'pythonPath': '/usr/bin/python3'}]
        }
        send_and_log(response, f"Responding to server request id={msg['id']}")

    for i in range(2):
        msg = read_message_sync()
        assert msg is not None, f"Expected success notification {i+1}"
        assert msg.get('method') == 'custom/requestResponseOk', \
               f"Expected custom/requestResponseOk notification: {msg}"

    do_shutdown()

if __name__ == '__main__':
    main()
