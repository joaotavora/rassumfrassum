#!/usr/bin/env python
"""
Test client for out-of-order diagnostic versions.
Verifies that stale diagnostics are dropped.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that stale diagnostics are dropped."""

    client = await LspTestEndpoint.create()
    await client.initialize()

    # Send didOpen with version 1
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'languageId': 'python',
            'version': 1,
            'text': 'print("hello")\n'
        }
    })

    # Expect diagnostics for version 1
    payload = await client.read_notification('textDocument/publishDiagnostics')
    assert payload.get('version') == 1
    diag_count_v1 = len(payload.get('diagnostics', []))
    log("client", f"Got diagnostics for version 1: {diag_count_v1} diagnostics")

    # Send didChange with version 2
    await client.notify('textDocument/didChange', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'version': 2
        },
        'contentChanges': [
            {'text': 'print("hello world")\n'}
        ]
    })

    # Expect diagnostics for version 2
    payload = await client.read_notification('textDocument/publishDiagnostics')
    assert payload.get('version') == 2
    diag_count_v2 = len(payload.get('diagnostics', []))
    log("client", f"Got diagnostics for version 2: {diag_count_v2} diagnostics")

    # Wait for potential stale v1 diagnostic (should NOT arrive)
    # Server sends it after 300ms. Aggregation timeout is 1000ms.
    # Wait 1500ms to make 100% sure we didn't start a new aggregation
    # which has timed out for some reason.
    log("client", "Checking that stale v1 diagnostic was dropped...")
    await client.assert_no_message_pending(timeout_sec=1.5)
    log("client", "Stale v1 diagnostic was correctly dropped!")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
