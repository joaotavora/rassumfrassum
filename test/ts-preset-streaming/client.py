#!/usr/bin/env python3
"""
Test client for TypeScript preset with ESLint in streaming mode.
"""

import asyncio
import os

from rassumfrassum.test2 import LspTestEndpoint, log
from rassumfrassum.json import write_message

async def main():
    """Test ESLint diagnostics via TypeScript preset in streaming mode."""

    client = await LspTestEndpoint.create()

    # Set working directory to the test project fixture
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_project = os.path.join(test_dir, "fixture")
    os.chdir(test_project)

    # Initialize with workspace configuration capability
    capabilities = {
        'workspace': {
            'configuration': True,
        },
        'textDocument': {
            'publishDiagnostics': {
                'relatedInformation': True,
                'tagSupport': {'valueSet': [1, 2]},
                'versionSupport': False,
            },
        },
    }

    init_response = await client.initialize(
        capabilities=capabilities, rootUri=f"file://{test_project}"
    )

    # Verify we got a response with capabilities
    result = init_response.get('result', {})
    server_caps = result.get('capabilities', {})
    assert server_caps, "Expected capabilities in initialize response"
    log(client.name, f"Server capabilities: {list(server_caps.keys())}")

    # Open the TypeScript file
    file_path = os.path.join(test_project, "src/index.ts")
    with open(file_path, 'r') as f:
        file_content = f.read()
    file_uri = f"file://{file_path}"

    log(client.name, f"Opening {file_uri}")
    await client.notify(
        'textDocument/didOpen',
        {
            'textDocument': {
                'uri': file_uri, 'languageId': 'typescript',
                'version': 1, 'text': file_content,
            }
        },
    )

    # Handle configuration requests (servers need these before sending diagnostics)
    # First configuration request (likely from eslint-language-server)
    sreq_id1, rparams1 = await client.read_request('workspace/configuration')
    items1 = rparams1.get('items', [])
    log(client.name, f"server req #{sreq_id1} for {len(items1)} item(s)")
    await write_message(
        client.writer,
        {'jsonrpc': '2.0', 'id': sreq_id1, 'result': [None] * len(items1)},
    )
    log(client.name, f"Sent null configuration response #{sreq_id1}")

    # Second configuration request (likely from typescript-language-server)
    sreq_id2, rparams2 = await client.read_request('workspace/configuration')
    items2 = rparams2.get('items', [])
    log(client.name, f"server req #{sreq_id2} for {len(items2)} item(s)")
    await write_message(
        client.writer,
        {'jsonrpc': '2.0', 'id': sreq_id2, 'result': [None] * len(items2)},
    )
    log(client.name, f"Sent null configuration response #{sreq_id2}")

    # In streaming mode, rass will automatically pull diagnostics and push them
    # Keep reading until we have diagnostics from both typescript and eslint
    log(client.name, "Reading diagnostic pushes...")
    sources_seen = set()
    all_diagnostics = []

    while len(sources_seen) < 2:
        push = await client.read_notification('$/streamDiagnostics')
        diags = push.get('diagnostics', [])
        if diags:
            source = diags[0].get('source', 'unknown')
            sources_seen.add(source)
            all_diagnostics.extend(diags)
            log(client.name, f"Got {len(diags)} diagnostic(s) from {source}")

    # Check that at least one diagnostic is from eslint
    eslint_diags = [d for d in all_diagnostics if d.get('source') == 'eslint']
    log(client.name, f"Got {len(eslint_diags)} ESLint diagnostic(s) total")
    assert len(eslint_diags) > 0, "Expected at least one ESLint diagnostic"

    log(client.name, "OK! Got diagnostics from both servers in streaming mode!")

    # Shutdown
    await client.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
