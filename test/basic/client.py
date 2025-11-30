#!/usr/bin/env python3
"""
A more complete test client that exercises various LSP messages.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, do_shutdown, send_and_log, log
from jaja import read_message_sync

def main():
    """Send a sequence of LSP messages."""

    init_response = do_initialize()

    # Verify merged serverInfo
    result = init_response['result']
    assert 'serverInfo' in result, f"Expected 'serverInfo' in result: {result}"
    server_info = result['serverInfo']
    # Primary server should always come first
    assert server_info.get('name') == 's1+s2', \
        f"Expected merged name 's1+s2', got '{server_info.get('name')}'"
    log("client", f"Verified merged server name: {server_info['name']}")

    do_initialized()

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
    assert msg is not None, "Expected publishDiagnostics notification"
    assert msg.get('method') == 'textDocument/publishDiagnostics', f"Expected publishDiagnostics, got: {msg}"
    assert 'params' in msg, f"Expected 'params' in diagnostics: {msg}"
    log("client", f"Got diagnostics {msg}")

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
    assert msg is not None, "Expected hover response"
    assert 'id' in msg and msg['id'] == 2, f"Expected response with id=2: {msg}"
    assert 'result' in msg or 'error' in msg, f"Expected 'result' or 'error' in hover response: {msg}"
    log("client", f"Got hover response {msg}")

    do_shutdown()

if __name__ == '__main__':
    main()
