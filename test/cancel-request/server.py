#!/usr/bin/env python3
"""
Server that delays hover responses and acknowledges $/cancelRequest.
"""

import argparse
import asyncio

from rassumfrassum.json import write_message_sync
from rassumfrassum.test2 import run_toy_server, log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

async def handle_completion(msg_id, params):
    """Handle completion with a delay, then respond."""
    log(args.name, "Got completion request, delaying 2 seconds...")
    await asyncio.sleep(2.0)
    log(args.name, "Delay done, responding to completion")
    return {
        "isIncomplete": False,
        "items": []
    }

def handle_cancel(params):
    """Handle $/cancelRequest notification."""
    cancelled_id = params.get('id')
    log(args.name, f"Got $/cancelRequest for id={cancelled_id}")
    # Send custom notification to confirm receipt
    write_message_sync({
        'jsonrpc': '2.0',
        'method': '$/yeahGotIt',
        'params': {'server': args.name}
    })

run_toy_server(
    name=args.name,
    capabilities={'completionProvider': {'triggerCharacters': ['.']}},
    request_handlers={'textDocument/completion': handle_completion},
    notification_handlers={'$/cancelRequest': handle_cancel}
)
