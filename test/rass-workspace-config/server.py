#!/usr/bin/env python
"""Server for rass-workspace-config test.

Sends a workspace/configuration request after initialized, then reports
the received config back to the client as a notification.
"""

import argparse
import asyncio

from rassumfrassum.json import read_message, write_message
from rassumfrassum.stdio import create_stdin_reader, create_stdout_writer
from rassumfrassum.test2 import log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

CONFIG_REQ_ID = 999

async def main():
    reader = await create_stdin_reader()
    writer = await create_stdout_writer()
    log(args.name, "Started!")

    async def send(msg):
        await write_message(writer, msg)

    while True:
        msg = await read_message(reader)
        if msg is None:
            break

        method = msg.get('method')
        msg_id = msg.get('id')

        if msg_id is not None and method:
            if method == 'initialize':
                await send({'jsonrpc': '2.0', 'id': msg_id, 'result': {
                    'capabilities': {},
                    'serverInfo': {'name': args.name, 'version': '1.0'},
                }})
            elif method == 'shutdown':
                await send({'jsonrpc': '2.0', 'id': msg_id, 'result': None})
                break
        elif method and msg_id is None:
            if method == 'initialized':
                log(args.name, "Sending workspace/configuration request")
                await send({'jsonrpc': '2.0', 'id': CONFIG_REQ_ID,
                            'method': 'workspace/configuration',
                            'params': {'items': [{'section': 'myserver'}]}})
        elif msg_id is not None and method is None:
            if msg_id == CONFIG_REQ_ID:
                result = msg.get('result') or []
                received = result[0] if result else None
                log(args.name, f"Got config: {received}")
                await send({'jsonrpc': '2.0',
                            'method': 'rass-test/configReceived',
                            'params': {'server': args.name, 'config': received}})

asyncio.run(main())
