#!/usr/bin/env python
"""Server for too-late-diagnostics-from-s1 test"""

import argparse
import time

from rassumfrassum.test2 import run_toy_server, make_diagnostic
from rassumfrassum.json import write_message_sync

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--delay-diagnostics', type=int, default=0)
args = parser.parse_args()

def handle_didopen(params):
    text_doc = params.get('textDocument', {})
    uri = text_doc.get('uri', 'file:///unknown')
    if args.delay_diagnostics > 0:
        time.sleep(args.delay_diagnostics / 1000.0)
    write_message_sync({
        'jsonrpc': '2.0',
        'method': 'textDocument/publishDiagnostics',
        'params': {
            'uri': uri,
            'diagnostics': [
                make_diagnostic(0, 0, 5, 1, f'An example error from {args.name}', args.name),
                make_diagnostic(0, 7, 12, 2, f'An example warning from {args.name}', args.name)
            ]
        }
    })

run_toy_server(
    name=args.name,
    notification_handlers={'textDocument/didOpen': handle_didopen}
)
