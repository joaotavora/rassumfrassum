#!/usr/bin/env python3
"""
Test client for basedpyright + ruff + codebook servers.
Tests three-server diagnostic aggregation with tardy updates using async.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log, maybe_timeout

async def main():
    """Test three-server diagnostics with tardy updates."""

    client = await LspTestEndpoint.create()
    await client.initialize(rootUri='file:///tmp')

    # Open documents with errors
    log("client", "Opening test1.py")
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test1.py',
            'version': 1,
            'languageId': 'python',
            'text': '''\
# This is a tset comment
def foo(x: int) -> int:
    return x;

foo("wrong");  # Type error: passing str to int
'''
        }
    })

    log("client", "Opening test2.py")
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test2.py',
            'version': 1,
            'languageId': 'python',
            'text': '''\
# Speling mistake here
def bar(s: str) -> str:
    return s.upper();

bar(42);  # Type error: passing int to str
'''
        }
    })

    diagnostics_by_uri = {}
    log("client", "Waiting 3.5 seconds for diagnostics (including tardy)...")

    async def collect_diags():
        """Collect diagnostic notifications."""
        while payload := await client.read_notification('textDocument/publishDiagnostics'):
            uri = payload['uri']
            diags = payload.get('diagnostics', [])

            old_count = len(diagnostics_by_uri.get(uri, []))
            diagnostics_by_uri[uri] = diags

            if old_count > 0:
                log("client", f"Got {len(diags)} diagnostic(s) for {uri} (replacing {old_count})")
            else:
                log("client", f"Got {len(diags)} diagnostic(s) for {uri}")

    try:
        await asyncio.wait_for(collect_diags(), timeout=maybe_timeout(2))
    except asyncio.TimeoutError:
        log("client", "Timeout reached, done collecting diagnostics")

    # Report final diagnostics
    for uri in ['file:///tmp/test1.py', 'file:///tmp/test2.py']:
        diags = diagnostics_by_uri.get(uri, [])
        log("client", f"\n{uri}: {len(diags)} total diagnostic(s)")

        sources = {}
        for diag in diags:
            source = diag.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1
            log("client", f"  [{source}] {diag.get('message', '')[:60]}")

        log("client", f"  Sources: {sources}")

        # Assertions: expect diagnostics from all 3 servers
        assert len(diags) == 5, f"Expected 5 diagnostics for {uri}, got {len(diags)}"
        assert sources.get('Ruff', 0) == 2, f"Expected 2 Ruff diagnostics for {uri}"
        assert sources.get('Codebook', 0) == 1, f"Expected 1 Codebook diagnostic for {uri}"
        assert sources.get('basedpyright', 0) == 2, f"Expected 2 basedpyright diagnostics for {uri}"

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
