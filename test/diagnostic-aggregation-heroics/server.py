#!/usr/bin/env python3
"""Server for diagnostic-aggregation-heroics test"""

import sys
import time
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from server_common import run_server, make_diagnostic, write_message_sync, log
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--didopen-delay', type=int, default=0)
parser.add_argument('--didchange-delay', type=int, default=0)
args = parser.parse_args()

def send_diagnostics(uri, version, delay_ms):
    """Send diagnostics for a specific version with optional delay."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
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
    log(args.name, f"published diagnostics for {uri} version {version}")

run_server(
    name=args.name,
    on_didopen=lambda uri, text_doc: send_diagnostics(uri, text_doc.get('version', 0), args.didopen_delay),
    on_didchange=lambda uri, text_doc: send_diagnostics(uri, text_doc.get('version', 0), args.didchange_delay)
)
