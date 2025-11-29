#!/usr/bin/env python3
"""
Test client for diagnostic-aggregation-heroics test.
Tests version-aware diagnostic aggregation across multiple didChange notifications.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, do_shutdown, send_and_log, log
from jsonrpc import read_message_sync

def main():
    """Send didOpen and multiple didChange notifications."""

    do_initialize()
    do_initialized()

    # Send didOpen with implicit version 1
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
    assert msg.get('method') == 'textDocument/publishDiagnostics', f"Expected publishDiagnostics, got: {msg}"
    params = msg.get('params', {})
    assert params.get('version') == 1, f"Expected version 1, got: {params.get('version')}"
    log("client", f"Got diagnostics for version 1: {len(params.get('diagnostics', []))} diagnostics")

    # Send didChange with version 42
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didChange',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'version': 42
            },
            'contentChanges': [
                {'text': 'print("hello world")\n'}
            ]
        }
    }, "Sending didChange (version 42)")

    # Expect diagnostics for version 42
    msg = read_message_sync()
    assert msg is not None, "Expected publishDiagnostics for version 42"
    assert msg.get('method') == 'textDocument/publishDiagnostics', f"Expected publishDiagnostics, got: {msg}"
    params = msg.get('params', {})
    assert params.get('version') == 42, f"Expected version 42, got: {params.get('version')}"
    log("client", f"Got diagnostics for version 42: {len(params.get('diagnostics', []))} diagnostics")

    # Send didChange with version 43
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didChange',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'version': 43
            },
            'contentChanges': [
                {'text': 'print("goodbye")\n'}
            ]
        }
    }, "Sending didChange (version 43)")

    # Expect diagnostics for version 43
    msg = read_message_sync()
    assert msg is not None, "Expected publishDiagnostics for version 43"
    assert msg.get('method') == 'textDocument/publishDiagnostics', f"Expected publishDiagnostics, got: {msg}"
    params = msg.get('params', {})
    assert params.get('version') == 43, f"Expected version 43, got: {params.get('version')}"
    log("client", f"Got diagnostics for version 43: {len(params.get('diagnostics', []))} diagnostics")

    log("client", "All version-aware diagnostics received successfully!")

    do_shutdown()

if __name__ == '__main__':
    main()
