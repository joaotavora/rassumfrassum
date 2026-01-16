#!/usr/bin/env python
"""Server for basic test"""

import argparse

from rassumfrassum.json import write_message_sync
from rassumfrassum.test2 import run_toy_server, make_diagnostic

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

def handle_didopen(params):
    text_doc = params.get('textDocument', {})
    uri = text_doc.get('uri', 'file:///unknown')
    write_message_sync({
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

run_toy_server(
    name=args.name,
    notification_handlers={'textDocument/didOpen': handle_didopen}
)
