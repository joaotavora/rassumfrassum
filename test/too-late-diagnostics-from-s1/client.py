#!/usr/bin/env python3
"""
Test client for too-late diagnostics scenario.
s1's diagnostics arrive after the timeout and should be discarded.
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
    assert len(diagnostics) == 2, f"Expected 2 diagnostics (only from s2, s1 timed out), got {len(diagnostics)}: {diagnostics}"

    # Verify only s2 contributed (s1's diagnostics were too late)
    sources = {d.get('source') for d in diagnostics}
    assert 's2' in sources, f"Expected diagnostics from s2, got sources: {sources}"
    assert 's1' not in sources, f"Expected s1 diagnostics to be discarded, but got sources: {sources}"

    log("client", f"Got diagnostics only from s2 (s1 timed out): {msg}")

    do_shutdown()

if __name__ == '__main__':
    main()
