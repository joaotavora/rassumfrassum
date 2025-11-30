#!/usr/bin/env python3
"""
Test that textDocumentSync=1 (Full) wins over textDocumentSync=2 (Incremental).
Even if the primary server reports Incremental, if any secondary server reports
Full, the merged capability should be Full.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import send_and_log, log
from jaja import read_message_sync

def main():
    """Test that textDocumentSync=1 wins."""

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
    text_doc_sync = capabilities.get('textDocumentSync')

    log("client", f"Got initialize response with textDocumentSync={text_doc_sync}")

    # The key assertion: textDocumentSync should be 1 (Full)
    # because s1 (secondary) has textDocumentSync=1, even though s2 (primary) has textDocumentSync=2
    assert text_doc_sync == 1, \
        f"Expected textDocumentSync=1 (Full) to win, but got: {text_doc_sync}"

    log("client", "✓ textDocumentSync=1 correctly won over textDocumentSync=2")

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
