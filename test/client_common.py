"""
Common test utilities for LSP client tests.
"""

import sys
import select
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from jaja import read_message_sync, write_message_sync, JSON

def log(prefix: str, msg: str):
    print(f'[{prefix}] {msg}', file=sys.stderr)

def send_and_log(message: JSON, description: str):
    """Send a message and log what we're doing."""
    log("client", description)
    write_message_sync(message)

def do_initialize() -> JSON:
    """Send initialize request and return the response."""
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
    log("client", "Got initialize response")
    return msg

def do_initialized():
    """Send initialized notification."""
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized notification")

def do_shutdown():
    """Send shutdown request and exit notification."""
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
    log("client", "Got shutdown response")

    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    log("client", "done!")

def assert_no_message_pending(timeout_sec: float = 0.1):
    """
    Assert that no message is available on stdin within timeout.
    Raises assertion error if a message is available.
    """
    readable, _, _ = select.select([sys.stdin.buffer], [], [], timeout_sec)
    if readable:
        msg = read_message_sync()
        raise AssertionError(f"Unexpected message received (should have been dropped): {msg}")
    log("client", f"Verified no message pending (waited {timeout_sec}s)")
