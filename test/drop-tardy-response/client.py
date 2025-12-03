#!/usr/bin/env python3
"""
Test client for tardy-initialize-response test.
Verifies that tardy initialize responses are dropped.
"""

import sys
import time
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import send_and_log, log, assert_no_message_pending
from jaja import read_message_sync

def main():
    """Test that tardy initialize responses are dropped."""

    # Send initialize
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    # Expect initialize response (aggregated, but only from S1 due to timeout)
    msg = read_message_sync()
    assert msg is not None, "Expected initialize response"
    assert 'result' in msg, f"Expected 'result' in initialize response: {msg}"
    assert msg.get('id') == 1, f"Expected response with id=1: {msg}"

    result = msg['result']
    capabilities = result.get('capabilities', {})
    server_info = result.get('serverInfo', {})

    log("client", f"Got initialize response from: {server_info.get('name', 'unknown')}")

    # Wait for potential tardy response from S2
    # S2 delays 2500ms, aggregation timeout is 2000ms
    # Wait 2700ms total to ensure tardy response has arrived at dada
    log("client", "Waiting for potential tardy initialize response...")
    time.sleep(2.7)

    # Critical assertion: verify no duplicate initialize response
    assert_no_message_pending(timeout_sec=0.1)
    log("client", "Tardy initialize response was correctly dropped!")

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
