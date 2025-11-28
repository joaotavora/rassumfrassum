#!/usr/bin/env python3
"""
Test client for late diagnostics scenario.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from jsonrpc import read_message_sync, write_message_sync, JSON

def log(prefix : str , msg : str):
    print(f'[{prefix}] {msg}', file=sys.stderr)

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
    assert msg is not None, "Expected initialize response"
    assert 'result' in msg, f"Expected 'result' in initialize response: {msg}"
    assert 'capabilities' in msg['result'], f"Expected 'capabilities' in initialize result: {msg}"
    log("client", f"Got initialize response {msg}")

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

    # 3. Shutdown
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    msg = read_message_sync()
    assert msg is not None, "Expected shutdown response"
    assert 'id' in msg and msg['id'] == 3, f"Expected response with id=3: {msg}"
    assert 'result' in msg, f"Expected 'result' in shutdown response: {msg}"
    log("client", f"Got shutdown response {msg}")

    # 4. Exit notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    log("client", "done!")

if __name__ == '__main__':
    main()
