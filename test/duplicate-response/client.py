#!/usr/bin/env python3
"""
Test client that sends a single request and checks response handling.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Send a single request to test duplicate response handling."""

    client = await LspTestEndpoint.create()

    # Initialize
    response = await client.initialize()
    log("client", f"Got initialize response: {response.get('result', {}).get('serverInfo', {})}")

    # Send a custom request (not LSP-specific)
    log("client", "Sending custom/test request...")
    req_id = await client.request('custom/test', {'data': 'test'})

    # Read the first response
    msg = await client.read_response(req_id)
    log("client", f"Got first response: {msg}")
    assert msg.get('result', {}).get('response') == 1, "Expected first response"

    # Critical assertion: no duplicate response should arrive
    log("client", "Checking that no duplicate response arrives...")
    await client.assert_no_message_pending(timeout_sec=0.5)
    log("client", "No duplicate response - correct behavior!")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
