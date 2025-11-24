#!/usr/bin/env python3
"""
A simple echo server that mimics LSP protocol for testing.
"""
import sys
import json


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


def write_lsp_message(message):
    """Write a single LSP message to stdout."""
    content = json.dumps(message, ensure_ascii=False)
    content_bytes = content.encode('utf-8')
    header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
    sys.stdout.buffer.write(header.encode('utf-8'))
    sys.stdout.buffer.write(content_bytes)
    sys.stdout.buffer.flush()


def main():
    """Echo back any message received."""
    print("Echo server started", file=sys.stderr, flush=True)

    while True:
        try:
            message = read_lsp_message()
            if message is None:
                break

            # Echo it back with a modification to show it went through
            if 'method' in message:
                response = {
                    'jsonrpc': '2.0',
                    'id': message.get('id'),
                    'result': f"Echo: {message['method']}"
                }
            else:
                response = message

            write_lsp_message(response)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            break

    print("Echo server stopped", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
