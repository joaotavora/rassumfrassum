#!/usr/bin/env python3
"""
Server that sends out-of-order diagnostics to test version staleness detection.
After sending v2 diagnostics, s1 will send a stale v1 diagnostic.
"""

import sys
import time
import threading
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from server_common import run_server, make_diagnostic, write_message_sync, log
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--send-stale-v1', action='store_true', help='Send stale v1 after v2')
args = parser.parse_args()

def send_diagnostics(uri, version):
    """Send diagnostics for a specific version."""
    write_message_sync({
        'jsonrpc': '2.0',
        'method': 'textDocument/publishDiagnostics',
        'params': {
            'uri': uri,
            'version': version,
            'diagnostics': [
                make_diagnostic(0, 0, 5, 1, f'Error from {args.name} v{version}'),
                make_diagnostic(0, 7, 12, 2, f'Warning from {args.name} v{version}')
            ]
        }
    })
    log(args.name, f"sent diagnostics for {uri} version {version}")

def send_stale_diagnostic_later(uri):
    """Send a stale v1 diagnostic after a delay."""
    time.sleep(0.3)  # Wait 300ms
    log(args.name, f"sending STALE v1 diagnostic for {uri}")
    send_diagnostics(uri, 1)

def on_didchange_handler(uri, text_doc):
    """Handle didChange - send current version, and maybe send stale v1."""
    version = text_doc.get('version', 0)
    send_diagnostics(uri, version)

    # If this is v2 and we're configured to send stale, spawn thread to send v1 later
    if version == 2 and args.send_stale_v1:
        thread = threading.Thread(target=send_stale_diagnostic_later, args=(uri,))
        thread.daemon = True
        thread.start()

run_server(
    name=args.name,
    on_didopen=lambda uri, text_doc: send_diagnostics(uri, text_doc.get('version', 0)),
    on_didchange=on_didchange_handler
)
