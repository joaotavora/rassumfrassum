#!/usr/bin/env python3
"""
Test that textDocument/rename routes to the first server with renameProvider.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import send_and_log, log
from jaja import read_message_sync

def main():
    """Test that rename routes to first server with renameProvider."""

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
    has_rename = capabilities.get('renameProvider')

    log("client", f"Got initialize response with renameProvider={has_rename}")
    assert has_rename, "Expected renameProvider to be present in merged capabilities"

    # Send initialized notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized")

    # Send textDocument/rename request
    send_and_log({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'textDocument/rename',
        'params': {
            'textDocument': {'uri': 'file:///test.py'},
            'position': {'line': 0, 'character': 0},
            'newName': 'newName'
        }
    }, "Sending textDocument/rename")

    # Expect rename response from ONLY s2 (first server with renameProvider)
    msg = read_message_sync()
    assert msg is not None, "Expected rename response"
    assert 'result' in msg, f"Expected 'result' in rename response: {msg}"
    assert msg.get('id') == 2, f"Expected response with id=2: {msg}"

    workspace_edit = msg['result']
    log("client", f"Got rename response: {workspace_edit}")

    # Should be from s2 only (no aggregation, early termination)
    changes = workspace_edit.get('changes', {})
    assert 'file:///test.py' in changes, f"Expected changes for file:///test.py"

    edits = changes['file:///test.py']
    assert len(edits) == 1, f"Expected 1 edit (from s2 only), got {len(edits)}: {edits}"

    new_text = edits[0]['newText']
    assert new_text == 'renamed_by_s2', f"Expected rename from s2, got: {new_text}"

    log("client", "✓ Rename correctly routed to first server with renameProvider (s2)")

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
