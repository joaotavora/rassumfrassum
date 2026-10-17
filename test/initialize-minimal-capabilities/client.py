#!/usr/bin/env python
"""
Test initialize with an empty capabilities object (#60).

Every field of ClientCapabilities is optional, but rass read
capabilities.textDocument unconditionally and never answered.
"""

import asyncio
import os

from rassumfrassum.test2 import LspTestEndpoint, log


async def main():
    client = await LspTestEndpoint.create()

    req_id = await client.request(
        'initialize',
        {
            'processId': None,
            'rootUri': f'file://{os.getcwd()}',
            'capabilities': {},
        },
    )
    response = await asyncio.wait_for(client.read_response(req_id), timeout=5)
    assert 'result' in response, f"Expected a result, got: {response}"
    await client.notify('initialized', {})

    log('client', 'All assertions passed')
    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
