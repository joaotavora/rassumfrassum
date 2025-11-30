#!/usr/bin/env python3
"""
Test that textDocument/codeAction aggregates results from all servers
with codeActionProvider capability.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import send_and_log, log
from jaja import read_message_sync

def main():
    """Test that code actions are aggregated from multiple servers."""

    # Send initialize
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    # Expect initialize response
    msg = read_message_sync()
    assert msg is not None, "Expected initialize response"
    assert 'result' in msg, f"Expected 'result' in initialize response: {msg}"

    result = msg['result']
    capabilities = result.get('capabilities', {})
    has_code_actions = capabilities.get('codeActionProvider')

    log("client", f"Got initialize response with codeActionProvider={has_code_actions}")
    assert has_code_actions, "Expected codeActionProvider to be present in merged capabilities"

    # Send initialized notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized")

    # Send textDocument/codeAction request
    send_and_log({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'textDocument/codeAction',
        'params': {
            'textDocument': {'uri': 'file:///test.py'},
            'range': {
                'start': {'line': 0, 'character': 0},
                'end': {'line': 0, 'character': 10}
            },
            'context': {'diagnostics': []}
        }
    }, "Sending textDocument/codeAction")

    # Expect aggregated code action response
    msg = read_message_sync()
    assert msg is not None, "Expected codeAction response"
    assert 'result' in msg, f"Expected 'result' in codeAction response: {msg}"
    assert msg.get('id') == 2, f"Expected response with id=2: {msg}"

    actions = msg['result']
    log("client", f"Got {len(actions)} code actions")

    # Should have 2 code actions (from s2 and s3, but not s1)
    assert isinstance(actions, list), f"Expected array of code actions, got: {type(actions)}"
    assert len(actions) == 2, f"Expected 2 code actions (from s2 and s3), got {len(actions)}: {actions}"

    # Verify we got actions from both s2 and s3
    titles = [a['title'] for a in actions]
    assert 'Fix from s2' in titles, f"Expected action from s2, got titles: {titles}"
    assert 'Fix from s3' in titles, f"Expected action from s3, got titles: {titles}"

    log("client", "✓ Code actions correctly aggregated from servers with codeActionProvider")

    # Send shutdown
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    msg = read_message_sync()
    assert msg is not None, "Expected shutdown response"
    assert 'id' in msg and msg['id'] == 3, f"Expected response with id=3: {msg}"
    log("client", "Got shutdown response")

    # Send exit
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    log("client", "done!")

if __name__ == '__main__':
    main()
