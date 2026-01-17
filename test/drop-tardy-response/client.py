#!/usr/bin/env python
"""
Test client for tardy-initialize-response test.
Verifies that tardy initialize responses are dropped.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that tardy initialize responses are dropped."""

    client = await LspTestEndpoint.create()

    # Send initialize (use helper to ensure proper capabilities)
    response = await client.initialize()
    result = response['result']
    server_info = result.get('serverInfo', {})

    log("client", f"Got initialize response from: {server_info.get('name', 'unknown')}")

    # Wait for potential tardy response from S2
    # S2 delays 3000, aggregation timeout is 2500
    # Wait 3200 total to ensure tardy response has arrived at rass
    log("client", "Waiting for potential tardy initialize response...")
    await asyncio.sleep(3.2)

    # Critical assertion: verify no duplicate initialize response
    await client.assert_no_message_pending(timeout_sec=0.1)
    log("client", "Tardy initialize response was correctly dropped!")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
