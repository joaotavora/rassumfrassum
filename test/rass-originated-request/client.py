#!/usr/bin/env python3
"""
Client for rass-originated-request test.

Tests that LspLogic can use request_server to make independent requests to servers.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test rass-originated requests."""

    client = await LspTestEndpoint.create()

    # Initialize
    await client.initialize()

    # Send the notification that will trigger the custom logic
    log("client", "Sending dummy_client_notif")
    await client.notify('dummy_client_notif', {})

    # Wait for the notification from the custom logic
    log("client", "Waiting for dummy_server_notif")
    response = await client.read_notification('dummy_server_notif')
    log("client", f"Got dummy_server_notif: {response}")

    # Verify the response
    assert 'value' in response, f"Expected 'value' in response: {response}"
    assert response['value'] == 42, f"Expected value=42, got {response['value']}"

    log("client", "SUCCESS: Received correct response from rass-originated request")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
