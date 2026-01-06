#!/usr/bin/env python3
"""
Test client that handles server requests.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log
from rassumfrassum.json import write_message

async def main():
    """Send a sequence of LSP messages and handle server requests."""

    client = await LspTestEndpoint.create()
    await client.initialize()

    # After initialized, we expect server requests for workspace/configuration
    # First, read both request IDs
    request_ids = []
    for i in range(2):
        id, payload = await client.read_request('workspace/configuration')
        log("client", f"Got server request: id={id} params={payload}")
        request_ids.append(id)

    # Then respond to both requests
    for id in request_ids:
        response = {
            'jsonrpc': '2.0',
            'id': id,
            'result': [{'pythonPath': '/usr/bin/python3'}]
        }
        await write_message(client.writer, response)
        log("client", f"Responding to server request id={id}")

    for i in range(2):
        _msg = await client.read_notification('custom/requestResponseOk')
        log("client", f"Got success notification {i+1}")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
