#!/usr/bin/env python3
"""
Server that sends duplicate responses to test response handling.
"""

import argparse

from rassumfrassum.test2 import run_toy_server, log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

def handle_custom_request(msg_id, params, send_message):
    """Handle custom request by sending TWO responses with the same ID."""
    log(args.name, f"Got custom request id={msg_id}, sending duplicate responses")

    # Send first response
    send_message({
        'jsonrpc': '2.0',
        'id': msg_id,
        'result': {'response': 1, 'from': args.name}
    })
    log(args.name, f"Sent first response for id={msg_id}")

    # Send second response with the SAME id
    send_message({
        'jsonrpc': '2.0',
        'id': msg_id,
        'result': {'response': 2, 'from': args.name}
    })
    log(args.name, f"Sent second (duplicate) response for id={msg_id}")

run_toy_server(
    name=args.name,
    raw_request_handlers={'custom/test': handle_custom_request}
)
