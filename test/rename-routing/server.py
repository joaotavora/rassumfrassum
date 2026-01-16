#!/usr/bin/env python
"""
Server that provides renameProvider capability.
"""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--has-rename', action='store_true',
                   help='Whether this server provides rename')
args = parser.parse_args()

# Build capabilities based on args
capabilities = {'hoverProvider': True}
if args.has_rename:
    capabilities['renameProvider'] = True

def handle_rename(msg_id, params):
    """Return a workspace edit from this server."""
    return {
        'changes': {
            'file:///test.py': [
                {
                    'range': {
                        'start': {'line': 0, 'character': 0},
                        'end': {'line': 0, 'character': 10}
                    },
                    'newText': f'renamed_by_{args.name}'
                }
            ]
        }
    }

run_toy_server(
    name=args.name,
    capabilities=capabilities,
    request_handlers={'textDocument/rename': handle_rename}
)
