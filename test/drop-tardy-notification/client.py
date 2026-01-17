#!/usr/bin/env python
"""
Test client for too-late diagnostics scenario.
s1's diagnostics arrive after the timeout and should be discarded.
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
    assert len(diagnostics) == 2, f"Expected 2 diagnostics (only from s2, s1 timed out), got {len(diagnostics)}: {diagnostics}"

    # Verify only s2 contributed (s1's diagnostics were too late)
    sources = {d.get('source') for d in diagnostics}
    assert 's2' in sources, f"Expected diagnostics from s2, got sources: {sources}"
    assert 's1' not in sources, f"Expected s1 diagnostics to be discarded, but got sources: {sources}"

    log("client", f"Got diagnostics only from s2 (s1 timed out)")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
