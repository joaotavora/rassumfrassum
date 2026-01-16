#!/usr/bin/env python
"""
Server that provides codeActionProvider capability.
"""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--has-code-actions', action='store_true',
                   help='Whether this server provides code actions')
args = parser.parse_args()

# Build capabilities based on args
capabilities = {'hoverProvider': True}
if args.has_code_actions:
    capabilities['codeActionProvider'] = True

def handle_code_action(msg_id, params):
    """Return a code action specific to this server."""
    return [
        {
            'title': f'Fix from {args.name}',
            'kind': 'quickfix'
        }
    ]

run_toy_server(
    name=args.name,
    capabilities=capabilities,
    request_handlers={'textDocument/codeAction': handle_code_action}
)
