#!/usr/bin/env python3
"""Server for basic test"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from server_common import run_server, make_diagnostic, write_message_sync
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

run_server(
    name=args.name,
    on_didopen=lambda uri, _: write_message_sync({
        'jsonrpc': '2.0',
        'method': 'textDocument/publishDiagnostics',
        'params': {
            'uri': uri,
            'diagnostics': [
                make_diagnostic(0, 0, 5, 1, f'An example error from {args.name}'),
                make_diagnostic(0, 7, 12, 2, f'An example warning from {args.name}')
            ]
        }
    })
)
