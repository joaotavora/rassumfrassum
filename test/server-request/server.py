#!/usr/bin/env python
"""Server for server-request test"""

import argparse

from rassumfrassum.test2 import run_toy_server, log
from rassumfrassum.json import write_message_sync

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--send-request-after-init', action='store_true')
args = parser.parse_args()

def handle_initialized(params):
    if args.send_request_after_init:
        log(args.name, "Sending request to client: workspace/configuration")
        write_message_sync({
            'jsonrpc': '2.0',
            'id': 999,
            'method': 'workspace/configuration',
            'params': {'items': [{'section': 'python'}]}
        })

run_toy_server(
    name=args.name,
    notification_handlers={'initialized': handle_initialized}
)
