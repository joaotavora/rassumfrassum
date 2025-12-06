#!/usr/bin/env python3
"""
Simple test client for real LSP servers.
"""

from rassumfrassum.test import do_initialize, do_initialized, do_shutdown

def main():
    """Send initialize and shutdown to real servers."""

    # Initialize
    init_response = do_initialize()

    # Just verify we got a response with capabilities
    result = init_response.get('result', {})
    capabilities = result.get('capabilities', {})
    assert capabilities, "Expected capabilities in initialize response"

    # Send initialized notification
    do_initialized()

    # Shutdown
    do_shutdown()

if __name__ == '__main__':
    main()
