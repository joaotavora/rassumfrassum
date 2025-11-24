#!/usr/bin/env python3
"""
Test client for diagnostic aggregation.
"""
import sys
import time
from jsonrpc import read_message_sync, write_message_sync


def send_and_log(message, description):
    """Send a message and log what we're doing."""
    print(f"\n==> {description}", file=sys.stderr)
    write_message_sync(message)


def main():
    """Send a sequence that triggers diagnostics."""

    # 1. Initialize
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    response = read_message_sync()
    print(f"<== Got initialize response", file=sys.stderr)

    # 2. Initialized notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized notification")

    # 3. didOpen notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didOpen',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'languageId': 'python',
                'version': 1,
                'text': 'print("hello")\n'
            }
        }
    }, "Sending didOpen notification")

    # Wait for merged diagnostics (aggregator has 1s timeout)
    print("\n==> Waiting 1.5s for aggregated diagnostics...", file=sys.stderr)
    time.sleep(1.5)

    print("==> Reading diagnostic message", file=sys.stderr)
    msg = read_message_sync()
    if msg:
        method = msg.get('method', 'response')
        print(f"<== Received {method}", file=sys.stderr)
        if method == 'textDocument/publishDiagnostics':
            params = msg.get('params', {})
            diags = params.get('diagnostics', [])
            print(f"    Diagnostics count: {len(diags)}", file=sys.stderr)
            for i, diag in enumerate(diags):
                source = diag.get('source', 'unknown')
                message = diag.get('message', '')
                severity = diag.get('severity', 0)
                print(f"    [{i}] {source} (severity={severity}): {message}", file=sys.stderr)
    else:
        print("    ERROR: No diagnostic received!", file=sys.stderr)

    # 4. Shutdown
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    response = read_message_sync()
    print(f"<== Got shutdown response", file=sys.stderr)

    # 5. Exit notification
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    print("\nDone!", file=sys.stderr)


if __name__ == '__main__':
    main()
