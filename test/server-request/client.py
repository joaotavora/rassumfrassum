#!/usr/bin/env python
"""
Test client that handles server requests.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

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
        await client.respond(id, [{'pythonPath': '/usr/bin/python3'}])
        log("client", f"Responding to server request id={id}")

    for i in range(2):
        _msg = await client.read_notification('custom/requestResponseOk')
        log("client", f"Got success notification {i+1}")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
