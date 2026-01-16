#!/usr/bin/env python
"""
Test client that expects rass to exit when server crashes.
"""

import asyncio
import sys

from rassumfrassum.test2 import LspTestEndpoint, log
from rassumfrassum.json import read_message

async def main():
    """Send initialize and initialized, then expect connection to die."""

    client = await LspTestEndpoint.create()
    await client.initialize()

    # After initialized, one of the servers will crash
    # We expect rass to exit, so we should get EOF
    msg = await read_message(client.reader)
    if msg is not None:
        log("client", f"ERROR: Expected EOF but got message: {msg}")
        sys.exit(1)

    log("client", "Got EOF as expected - rass exited after server crash")

if __name__ == '__main__':
    asyncio.run(main())
