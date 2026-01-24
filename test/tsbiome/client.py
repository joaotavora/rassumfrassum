#!/usr/bin/env python3
"""
Test client for TypeScript preset with Biome.
"""

import asyncio
import os

from rassumfrassum.test2 import LspTestEndpoint, log


async def main():
    """Test Biome diagnostics via TypeScript preset."""

    client = await LspTestEndpoint.create()

    # Set working directory to the test project fixture
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_project = os.path.join(test_dir, "fixture")
    os.chdir(test_project)

    # Initialize with workspace configuration and file watching capabilities
    capabilities = {
        'workspace': {
            'configuration': True,
            'didChangeWatchedFiles': {
                'dynamicRegistration': True,
                'relativePatternSupport': True,
            },
        },
        'textDocument': {
            'publishDiagnostics': {
                'relatedInformation': True,
                'tagSupport': {'valueSet': [1, 2]},
                'versionSupport': False,
            },
        },
    }

    # Initialize with workspaceFolders to match real LSP clients
    init_params = {
        'capabilities': capabilities,
        'rootUri': f"file://{test_project}",
        'workspaceFolders': [
            {'uri': f"file://{test_project}", 'name': 'fixture'}
        ],
    }

    log(client.name, "Sending initialize")
    req_id = await client.request('initialize', init_params)
    init_response = await client.read_response(req_id)
    log(client.name, "Got initialize response")
    server_info = init_response.get('result', {}).get('serverInfo', {})
    if server_info:
        log(
            client.name,
            f"Server: {server_info.get('name')} v{server_info.get('version')}",
        )

    # Send initialized notification
    log(client.name, "Sending initialized")
    await client.notify('initialized', {})

    # Verify we got capabilities
    result = init_response.get('result', {})
    server_caps = result.get('capabilities', {})
    assert server_caps, "Expected capabilities in initialize response"
    log(client.name, f"Server capabilities: {list(server_caps.keys())}")

    # Open the JavaScript file
    file_path = os.path.join(test_project, "simple.js")
    with open(file_path, 'r') as f:
        file_content = f.read()
    file_uri = f"file://{file_path}"

    log(client.name, f"Opening {file_uri}")
    await client.notify(
        'textDocument/didOpen',
        {
            'textDocument': {
                'uri': file_uri,
                'languageId': 'javascript',
                'version': 1,
                'text': file_content,
            }
        },
    )

    # Main message loop - handle all messages until we get diagnostics from both servers
    log(client.name, "Entering message loop...")
    sources_seen = set()
    all_diagnostics = []

    while len(sources_seen) < 2:
        # can't use simpler 'read_request', because requests and notification
        # come in intermingled.
        msg = await client.read_message()
        method = msg.get('method')
        msg_id = msg.get('id')

        # Handle server requests (have both 'method' and 'id').
        if method and msg_id is not None and 'result' not in msg:
            if method in ['client/unregisterCapability', 'client/registerCapability']:
                log(client.name, f"Responding to {method} #{msg_id}")
                await client.respond(msg_id, None)
            elif method == 'workspace/configuration':
                items = msg.get('params', {}).get('items', [])
                log(
                    client.name,
                    f"Responding to {method} #{msg_id} with {len(items)} null(s)",
                )
                await client.respond(msg_id, [None] * len(items))  # ty:ignore[invalid-argument-type]
            else:
                log(client.name, f"Ignoring server request: {method} #{msg_id}")

        # Handle notifications (have 'method' but no 'id')
        elif method and msg_id is None:
            if method == 'textDocument/publishDiagnostics':
                params = msg.get('params', {})
                diags = params.get('diagnostics', [])
                if diags:
                    for diag in diags:
                        source = diag.get('source', 'unknown')
                        sources_seen.add(source)
                    all_diagnostics.extend(diags)
                    log(
                        client.name,
                        f"Got {len(diags)} diagnostic(s), sources so far: {sources_seen}",
                    )
            else:
                log(client.name, f"Ignoring notification: {method}")

    # Check that we have diagnostics from both TypeScript and Biome
    biome_diags = [
        d for d in all_diagnostics if 'biome' in d.get('source', '').lower()
    ]
    ts_diags = [d for d in all_diagnostics if d.get('source') == 'typescript']
    log(client.name, f"Got {len(ts_diags)} TypeScript diagnostic(s)")
    log(client.name, f"Got {len(biome_diags)} Biome diagnostic(s)")
    assert len(biome_diags) > 0, "Expected at least one Biome diagnostic"
    assert len(ts_diags) > 0, "Expected at least one TypeScript diagnostic"

    log(client.name, "OK! Got diagnostics from both TypeScript and Biome!")

    # Shutdown
    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
