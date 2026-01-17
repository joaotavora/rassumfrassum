#!/usr/bin/env python
"""
Test client that verifies serverInfo merging in initialize response.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Send initialize and verify merged serverInfo."""

    client = await LspTestEndpoint.create()

    # Send initialize
    init_response = await client.initialize()
    result = init_response['result']

    # Check capabilities exist
    assert 'capabilities' in result, f"Expected 'capabilities' in result: {result}"

    # Check serverInfo
    assert 'serverInfo' in result, f"Expected 'serverInfo' in result: {result}"
    server_info = result['serverInfo']

    # Verify merged name (should be "s1+s2")
    expected_name = "s1+s2"
    assert 'name' in server_info, f"Expected 'name' in serverInfo: {server_info}"
    assert server_info['name'] == expected_name, \
        f"Expected name '{expected_name}', got '{server_info['name']}'"
    log("client", f"Verified merged name: {server_info['name']}")

    # Verify merged version (should be "1.0.0,2.0.0")
    expected_version = "1.0.0,2.0.0"
    assert 'version' in server_info, f"Expected 'version' in serverInfo: {server_info}"
    assert server_info['version'] == expected_version, \
        f"Expected version '{expected_version}', got '{server_info['version']}'"
    log("client", f"Verified merged version: {server_info['version']}")

    log("client", "Got initialize response with correct merged serverInfo")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
