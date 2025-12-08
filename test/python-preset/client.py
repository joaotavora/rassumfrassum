#!/usr/bin/env python3
"""
Simple test client for real LSP servers.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint

async def main():
    """Send initialize and shutdown to real servers."""

    client = await LspTestEndpoint.create()

    # Initialize
    init_response = await client.initialize()

    # Just verify we got a response with capabilities
    result = init_response.get('result', {})
    capabilities = result.get('capabilities', {})
    assert capabilities, "Expected capabilities in initialize response"

    # Shutdown
    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
