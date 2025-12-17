#!/usr/bin/env python3
"""
Server that provides definitionProvider capability.
"""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--has-definition', action='store_true',
                   help='Whether this server provides definitions')
parser.add_argument('--as-dict', action='store_true',
                   help='Whether the definition provided is contained in a dictionary')
args = parser.parse_args()

capabilities = {}
if args.has_definition:
    capabilities['definitionProvider'] = True

definition = {
    'uri': f'file:///{args.name}.py',
    'range': {
        'start': {'line': 0, 'character': 0},
        'end': {'line': 0, 'character': 10}
    }
}

def build_handler(as_dict: bool):
    def handle_definition(msg_id, params):
        return definition if as_dict else [definition]

    return handle_definition

run_toy_server(
    name=args.name,
    capabilities=capabilities,
    request_handlers={'textDocument/definition': build_handler(args.as_dict)}
)
