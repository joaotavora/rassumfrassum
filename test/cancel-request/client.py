#!/usr/bin/env python3
"""
Test client for $/cancelRequest handling.
Verifies that cancelled requests don't get responses and that
the cancel notification is properly forwarded to servers.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that $/cancelRequest properly cancels requests."""

    client = await LspTestEndpoint.create()

    # Initialize
    response = await client.initialize()
    log("client", f"Got initialize response: {response.get('result', {}).get('serverInfo', {})}")

    # Send a completion request that will be delayed by the servers
    log("client", "Sending slow completion request...")
    req_id = await client.request('textDocument/completion', {
        'textDocument': {'uri': 'file:///tmp/test.py'},
        'position': {'line': 0, 'character': 0}
    })

    # Give rass time to forward the request to servers before cancelling
    await asyncio.sleep(0.1)

    # Now cancel it
    log("client", f"Sending $/cancelRequest for request {req_id}")
    await client.notify('$/cancelRequest', {'id': req_id})

    # Read the next two messages - should be $/yeahGotIt notifications
    # Using read_message() instead of read_notification() to catch any
    # buggy response that might slip through from rass
    log("client", "Waiting for first $/yeahGotIt notification...")
    msg1 = await client.read_message(timeout_sec=1.0)
    assert 'method' in msg1, f"Expected notification, got: {msg1}"
    assert msg1['method'] == '$/yeahGotIt', f"Expected $/yeahGotIt, got {msg1['method']}"
    server1 = msg1['params'].get('server')
    log("client", f"Got $/yeahGotIt from {server1}")

    log("client", "Waiting for second $/yeahGotIt notification...")
    msg2 = await client.read_message(timeout_sec=1.0)
    assert 'method' in msg2, f"Expected notification, got: {msg2}"
    assert msg2['method'] == '$/yeahGotIt', f"Expected $/yeahGotIt, got {msg2['method']}"
    server2 = msg2['params'].get('server')
    log("client", f"Got $/yeahGotIt from {server2}")

    # Verify we got one from each server
    servers = {server1, server2}
    assert servers == {'s1', 's2'}, f"Expected notifications from s1 and s2, got {servers}"

    # Now try to read another message - should timeout
    # The servers will actually respond to the completion (they're allowed to even
    # after receiving $/cancelRequest), but rass should block those responses
    log("client", "Waiting to ensure cancelled response doesn't arrive...")
    try:
        msg = await client.read_message(timeout_sec=2.5)
        # If we get here, we got a message when we shouldn't have
        raise AssertionError(f"Expected no response to cancelled request, but got: {msg}")
    except asyncio.TimeoutError:
        # This is what we expect - no message arrived
        log("client", "Cancelled request response was correctly blocked!")
        pass

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
