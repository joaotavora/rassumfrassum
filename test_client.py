#!/usr/bin/env python3
"""
A simple test client that sends an LSP message.
"""
import sys
import json


def write_lsp_message(message):
    """Write a single LSP message to stdout."""
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')
    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    sys.stdout.buffer.write(header.encode('utf-8'))
    sys.stdout.buffer.write(content_bytes)
    sys.stdout.buffer.flush()


def read_lsp_message():
    """Read a single LSP message from stdin."""
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.decode('utf-8').strip()
        if not line:
            break
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()

    content_length = int(headers.get('Content-Length', 0))
    if content_length == 0:
        return None

    content = sys.stdin.buffer.read(content_length)
    return json.loads(content.decode('utf-8'))


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
    write_lsp_message(message)

    # Read response
    print("Waiting for response...", file=sys.stderr)
    response = read_lsp_message()

    if response:
        print("Received response:", file=sys.stderr)
        print(json.dumps(response, indent=2), file=sys.stderr)
    else:
        print("No response received", file=sys.stderr)


if __name__ == '__main__':
    main()
