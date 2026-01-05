#!/usr/bin/env python3
"""
Test client for TypeScript preset with ESLint.
"""

import asyncio
import os

from rassumfrassum.test2 import LspTestEndpoint, log
from rassumfrassum.json import write_message

async def main():
    """Test ESLint diagnostics via TypeScript preset."""

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

    # Request diagnostics (pull model)
    log(client.name, "Requesting diagnostics...")
    req_id = await client.request(
        'textDocument/diagnostic', {'textDocument': {'uri': file_uri}}
    )

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

    # Read pushed diagnostics (push notification)
    push_diags = (await client.read_notification(
        'textDocument/publishDiagnostics'
    )).get('diagnostics', [])
    log(client.name, f"Got {len(push_diags)} pushed diagnostics")

    # Test TypeScript diagnostics
    ts_diags = [d for d in push_diags if d.get('source') == 'typescript']
    log(client.name, f"Got {len(ts_diags)} TypeScript diagnostic(s)")
    assert len(ts_diags) > 0, ( "Expected at least one TypeScript diagnostic")

    # Pull some more diagnostics (pull response)
    diag_response = await client.read_response(req_id)
    result = diag_response.get('result', {})
    pull_diagnostics = result.get('items', [])

    # Test ESLint diagnostics
    eslint_diags = [d for d in pull_diagnostics if d.get('source') == 'eslint']
    log(client.name, f"Got {len(eslint_diags)} ESLint diagnostic(s)")
    assert len(eslint_diags) > 0, "Expected at least one ESLint diagnostic"

    log(client.name, "OK! Got diagnostics from both ESLint and TypeScript!")

    # Shutdown
    await client.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
