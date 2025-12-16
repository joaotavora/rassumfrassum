#!/usr/bin/env python3
"""
Test that textDocument/definition aggregates results from servers
with definitionProvider capability.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    client = await LspTestEndpoint.create()
    init_response = await client.initialize()

    result = init_response['result']
    capabilities = result.get('capabilities', {})
    has_definition = capabilities.get('definitionProvider')

    log("client", f"Got initialize response with definitionProvider={has_definition}")
    assert has_definition, "Expected definitionProvider to be present in merged capabilities"

    req_id = await client.request('textDocument/definition', {
        'textDocument': {'uri': 'file:///test.py'},
        'position': {'line': 101, 'character': 5}
    })

    response = await client.read_response(req_id)
    definitions = response['result']
    log("client", f"Got {len(definitions)} definitions")

    # Should have 3 definitions:
    # - s1 provides no definitions
    # - s2 and s3 provide 1 unique definition each
    # - s4 and s5 provide the same exact definition
    assert isinstance(definitions, list), f"Expected array of definitions, got: {type(definitions)}"
    assert len(definitions) == 3, f"Expected 3 definitions (from s2, s3 and s4/s5), got {len(definitions)}: {definitions}"

    uris = [d['targetUri'] for d in definitions]
    assert 'file:///s2.py' in uris, f"Expected definition from s2, got uris: {uris}"
    assert 'file:///s3.py' in uris, f"Expected definition from s3, got uris: {uris}"
    assert 'file:///s4.py' in uris or 'file:///s5.py' in uris, f"Expected definition from s4/s5, got uris: {uris}"

    log("client", "✓ Definitions correctly aggregated from servers with definitionProvider")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
