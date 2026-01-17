#!/usr/bin/env python
"""
Test client for late diagnostics scenario.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Send a sequence of LSP messages."""

    client = await LspTestEndpoint.create()
    await client.initialize()

    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'languageId': 'python',
            'version': 1,
            'text': 'print("hello")\n'
        }
    })

    payload = await client.read_notification('textDocument/publishDiagnostics')
    diagnostics = payload.get('diagnostics', [])
    assert len(diagnostics) == 4, f"Expected 4 diagnostics (2 from each server), got {len(diagnostics)}: {diagnostics}"

    # Verify both servers contributed
    sources = {d.get('source') for d in diagnostics}
    assert 's1' in sources, f"Expected diagnostics from s1, got sources: {sources}"
    assert 's2' in sources, f"Expected diagnostics from s2, got sources: {sources}"

    log("client", f"Got aggregated diagnostics from both servers")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
