#!/usr/bin/env python
"""Server for rass-init-opts test: records received initializationOptions."""

import argparse
from rassumfrassum.json import write_message_sync
from rassumfrassum.test2 import run_toy_server, log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

received_init_opts = None

def handle_initialize(msg_id, params):
    global received_init_opts
    received_init_opts = (params or {}).get('initializationOptions')
    return {'capabilities': {}, 'serverInfo': {'name': args.name, 'version': '1.0'}}

def handle_initialized(params):
    write_message_sync({
        'jsonrpc': '2.0',
        'method': 'rass-test/initOptions',
        'params': {'server': args.name, 'initializationOptions': received_init_opts}
    })
    log(args.name, f"Sent initializationOptions: {received_init_opts}")

run_toy_server(
    name=args.name,
    request_handlers={'initialize': handle_initialize},
    notification_handlers={'initialized': handle_initialized},
)
