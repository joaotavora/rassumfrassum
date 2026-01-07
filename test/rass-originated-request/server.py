#!/usr/bin/env python3
"""Server for rass-originated-request test."""

from rassumfrassum.test2 import run_toy_server

def handle_dummy_method(msg_id, params):
    """Handle dummy_method request and return 42."""
    return 42

run_toy_server(
    name='test-server',
    request_handlers={'dummy_method': handle_dummy_method}
)
