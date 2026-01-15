#!/usr/bin/env python3
"""
Server that provides definitionProvider capability.
"""

import argparse
import random

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--has-definition', action='store_true',
                   help='Whether this server provides definitions')
parser.add_argument('--in-dict', action='store_true',
                   help='Whether the definition location provided is contained in a dictionary')
parser.add_argument('--as-link', action='store_true',
                   help='Whether the definition location returned provided is a link')
parser.add_argument('--const', action='store_true',
                   help='Whether the definition location returned contains always the same range')
args = parser.parse_args()

capabilities = {}
if args.has_definition:
    capabilities['definitionProvider'] = True

def handle_find_definition(msg_id, params):
    startLine, startChar = 0, 0
    endLine, endChar = 0, 10
    if not args.const:
        startLine, startChar = random.randint(11, 10000), random.randint(0, 1000)
        endLine, endChar = startLine, startChar + random.randint(1, 1000)

    definition = {
        'uri': f'file:///{args.name}.py',
        'range': {
            'start': {'line': startLine, 'character': startChar},
            'end': {'line': endLine, 'character': endChar}
        }
    }

    if args.as_link:
        definition = {
            'targetUri': definition['uri'],
            'targetSelectionRange': definition['range'],
            'targetRange': definition['range']
        }

    return definition if args.in_dict else [definition]

run_toy_server(
    name=args.name,
    capabilities=capabilities,
    request_handlers={'textDocument/definition': handle_find_definition}
)
