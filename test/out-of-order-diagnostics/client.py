#!/usr/bin/env python3
"""
Test client for out-of-order diagnostic versions.
Verifies that stale diagnostics are dropped.
"""

import sys
import time
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, do_shutdown, send_and_log, log, assert_no_message_pending
from jaja import read_message_sync

def main():
    """Test that stale diagnostics are dropped."""

    do_initialize()
    do_initialized()

    # Send didOpen with version 1
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
    }, "Sending didOpen (version 1)")

    # Expect diagnostics for version 1
    msg = read_message_sync()
    assert msg is not None, "Expected publishDiagnostics for version 1"
    assert msg.get('method') == 'textDocument/publishDiagnostics'
    params = msg.get('params', {})
    assert params.get('version') == 1
    diag_count_v1 = len(params.get('diagnostics', []))
    log("client", f"Got diagnostics for version 1: {diag_count_v1} diagnostics")

    # Send didChange with version 2
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didChange',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'version': 2
            },
            'contentChanges': [
                {'text': 'print("hello world")\n'}
            ]
        }
    }, "Sending didChange (version 2)")

    # Expect diagnostics for version 2
    msg = read_message_sync()
    assert msg is not None, "Expected publishDiagnostics for version 2"
    assert msg.get('method') == 'textDocument/publishDiagnostics'
    params = msg.get('params', {})
    assert params.get('version') == 2
    diag_count_v2 = len(params.get('diagnostics', []))
    log("client", f"Got diagnostics for version 2: {diag_count_v2} diagnostics")

    # Wait for potential stale v1 diagnostic (should NOT arrive)
    # Server sends it after 300ms. Aggregation timeout is 1000ms.
    # Wait 1500ms to make 100% sure we didn't start a new aggregation
    # which has timed out for some reason.
    log("client", "Checking that stale v1 diagnostic was dropped...")
    assert_no_message_pending(timeout_sec=1.5)
    log("client", "Stale v1 diagnostic was correctly dropped!")

    do_shutdown()

if __name__ == '__main__':
    main()
