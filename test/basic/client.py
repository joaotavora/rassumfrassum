#!/usr/bin/env python
"""
A more complete test client that exercises various LSP messages.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Send a sequence of LSP messages."""

    client = await LspTestEndpoint.create()
    init_response = await client.initialize()

    # Verify merged serverInfo
    result = init_response['result']
    assert 'serverInfo' in result, f"Expected 'serverInfo' in result: {result}"
    server_info = result['serverInfo']
    # Primary server should always come first
    assert server_info.get('name') == 's1+s2', \
        f"Expected merged name 's1+s2', got '{server_info.get('name')}'"
    log("client", f"Verified merged server name: {server_info['name']}")

    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'languageId': 'python',
            'version': 1,
            'text': 'print("hello")\n'
        }
    })

    payload = await client.read_notification('textDocument/publishDiagnostics')
    log("client", f"Got diagnostics {payload}")

    # Hover request
    req_id = await client.request('textDocument/hover', {
        'textDocument': {'uri': 'file:///tmp/test.py'},
        'position': {'line': 0, 'character': 0}
    })

    hover_response = await client.read_response(req_id)
    assert 'result' in hover_response or 'error' in hover_response, \
        f"Expected 'result' or 'error' in hover response: {hover_response}"
    log("client", f"Got hover response {hover_response}")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
