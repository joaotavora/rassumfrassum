#!/usr/bin/env python3
"""
A second echo server for testing multi-server setup.
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
    print("Echo server 2 started", file=sys.stderr, flush=True)

    while True:
        try:
            message = read_lsp_message()
            if message is None:
                break

            # Echo it back with a modification to show it went through server 2
            if 'method' in message:
                if message['method'] == 'initialize':
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': {
                            'capabilities': {
                                'textDocumentSync': 1,
                                'completionProvider': {'triggerCharacters': ['.']},
                            },
                            'serverInfo': {'name': 'test-server-2', 'version': '1.0'}
                        }
                    }
                else:
                    response = {
                        'jsonrpc': '2.0',
                        'id': message.get('id'),
                        'result': f"Echo2: {message['method']}"
                    }
            else:
                response = message

            write_lsp_message(response)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            break

    print("Echo server 2 stopped", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
