#!/usr/bin/env python3
"""
Test client for late diagnostics scenario.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, do_shutdown, send_and_log, log
from jaja import read_message_sync

def main():
    """Send a sequence of LSP messages."""

    do_initialize()
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
    diagnostics = msg['params'].get('diagnostics', [])
    assert len(diagnostics) == 4, f"Expected 4 diagnostics (2 from each server), got {len(diagnostics)}: {diagnostics}"

    # Verify both servers contributed
    sources = {d.get('source') for d in diagnostics}
    assert 's1' in sources, f"Expected diagnostics from s1, got sources: {sources}"
    assert 's2' in sources, f"Expected diagnostics from s2, got sources: {sources}"

    log("client", f"Got aggregated diagnostics from both servers: {msg}")

    do_shutdown()

if __name__ == '__main__':
    main()
