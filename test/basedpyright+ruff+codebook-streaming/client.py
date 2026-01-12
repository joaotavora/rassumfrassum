#!/usr/bin/env python3
"""
Test client for basedpyright + ruff + codebook servers in streaming mode.
Tests three-server diagnostic streaming (no aggregation).
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, scaled_timeout, log

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

    diagnostics_by_uri_and_source = {}  # uri -> source -> [diags]
    log("client", "Waiting diagnostics (including tardy)...")

    async def collect_diags():
        """Collect diagnostic notifications."""
        while payload := await client.read_notification('$/streamDiagnostics'):
            uri = payload['uri']
            diags = payload.get('diagnostics', [])

            if diags:
                source = diags[0].get('source', 'unknown')
                diagnostics_by_uri_and_source.setdefault(uri, {})[source] = diags
                log("client", f"Got {len(diags)} diagnostic(s) from {source} for {uri}")

    try:
        await asyncio.wait_for(collect_diags(), scaled_timeout(2))
    except asyncio.TimeoutError:
        log("client", "Timeout reached, done collecting diagnostics")

    # Report final diagnostics grouped by URI
    for uri in ['file:///tmp/test1.py', 'file:///tmp/test2.py']:
        sources_dict = diagnostics_by_uri_and_source.get(uri, {})
        total_diags = sum(len(diags) for diags in sources_dict.values())
        log("client", f"\n{uri}: {total_diags} total diagnostic(s)")

        sources_count = {}
        for source, diags in sources_dict.items():
            sources_count[source] = len(diags)
            for diag in diags:
                log("client", f"  [{source}] {diag.get('message', '')[:60]}")

        log("client", f"  Sources: {sources_count}")

        # Assertions: expect exactly 5 diagnostics per file from all 3 servers
        assert total_diags == 5, f"Expected 5 diagnostics for {uri}, got {total_diags}"
        assert sources_count.get('Ruff', 0) == 2, f"Expected 2 Ruff diagnostics for {uri}, got {sources_count.get('Ruff', 0)}"
        assert sources_count.get('Codebook', 0) == 1, f"Expected 1 Codebook diagnostic for {uri}, got {sources_count.get('Codebook', 0)}"
        assert sources_count.get('basedpyright', 0) == 2, f"Expected 2 basedpyright diagnostics for {uri}, got {sources_count.get('basedpyright', 0)}"

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
