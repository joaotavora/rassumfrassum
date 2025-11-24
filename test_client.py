#!/usr/bin/env python3
"""
A simple test client that sends an LSP message.
"""
import sys
import json
from jsonrpc import read_message_sync, write_message_sync


def main():
    """Send a test message and read response."""
    # Send initialize request
    message = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }

    print("Sending initialize request...", file=sys.stderr)
    write_message_sync(message)

    # Read response
    print("Waiting for response...", file=sys.stderr)
    response = read_message_sync()

    if response:
        print("Received response:", file=sys.stderr)
        print(json.dumps(response, indent=2), file=sys.stderr)
    else:
        print("No response received", file=sys.stderr)


if __name__ == '__main__':
    main()
