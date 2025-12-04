#!/usr/bin/env python3
"""Server for too-late-diagnostics-from-s1 test"""


from rassumfrassum.tete import run_server, make_diagnostic, write_message_sync
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--delay-diagnostics', type=int, default=0)
args = parser.parse_args()

run_server(
    name=args.name,
    on_didopen=lambda uri, _: (
        time.sleep(args.delay_diagnostics / 1000.0) if args.delay_diagnostics > 0 else None,
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
    )[1]
)
