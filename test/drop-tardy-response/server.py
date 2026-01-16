#!/usr/bin/env python
"""
Server that can delay its initialize response.
Used to test tardy request response dropping.
"""

import argparse
import time

from rassumfrassum.test2 import run_toy_server, log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--initialize-delay', type=int, default=0,
                   help='Delay in milliseconds before responding to initialize')
args = parser.parse_args()

def handle_initialize(msg_id, params):
    """Handle initialize with optional delay."""
    if args.initialize_delay > 0:
        log(args.name, f"Delaying initialize response by {args.initialize_delay}ms")
        time.sleep(args.initialize_delay / 1000.0)

    return {
        'capabilities': {
            'textDocumentSync': 2,
            'hoverProvider': True,
        },
        'serverInfo': {
            'name': args.name,
            'version': '1.0.0'
        }
    }

run_toy_server(
    name=args.name,
    request_handlers={'initialize': handle_initialize}
)
