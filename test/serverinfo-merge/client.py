#!/usr/bin/env python3
"""
Test client that verifies serverInfo merging in initialize response.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialized, do_shutdown, send_and_log, log
from jaja import read_message_sync

def main():
    """Send initialize and verify merged serverInfo."""

    # Send initialize
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    msg = read_message_sync()
    assert msg is not None, "Expected initialize response"
    assert 'result' in msg, f"Expected 'result' in initialize response: {msg}"
    result = msg['result']

    # Check capabilities exist
    assert 'capabilities' in result, f"Expected 'capabilities' in result: {result}"

    # Check serverInfo
    assert 'serverInfo' in result, f"Expected 'serverInfo' in result: {result}"
    server_info = result['serverInfo']

    # Verify merged name (should be "s1+s2")
    expected_name = "s1+s2"
    assert 'name' in server_info, f"Expected 'name' in serverInfo: {server_info}"
    assert server_info['name'] == expected_name, \
        f"Expected name '{expected_name}', got '{server_info['name']}'"
    log("client", f"Verified merged name: {server_info['name']}")

    # Verify merged version (should be "1.0.0,2.0.0")
    expected_version = "1.0.0,2.0.0"
    assert 'version' in server_info, f"Expected 'version' in serverInfo: {server_info}"
    assert server_info['version'] == expected_version, \
        f"Expected version '{expected_version}', got '{server_info['version']}'"
    log("client", f"Verified merged version: {server_info['version']}")

    log("client", "Got initialize response with correct merged serverInfo")

    do_initialized()
    do_shutdown()

if __name__ == '__main__':
    main()
