#!/usr/bin/env python3
"""
Test that didChangeWatchedFiles is filtered based on glob patterns.

This test verifies that when a file change notification is sent, rass only
forwards it to servers whose watchers match the changed file's URI.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test file watcher filtering."""

    client = await LspTestEndpoint.create()

    # Initialize with didChangeWatchedFiles and streaming diagnostics support
    capabilities = {
        'workspace': {
            'didChangeWatchedFiles': {
                'dynamicRegistration': True,
                'relativePatternSupport': True,
            }
        },
        'textDocument': {
            '$streamingDiagnostics': {
                'dynamicRegistration': False
            }
        }
    }
    await client.initialize(capabilities=capabilities, rootUri='file:///tmp/test-project')

    # Handle client/registerCapability requests from servers
    # Both ty and ruff will send these
    log("client", "Handling registerCapability requests...")
    for _ in range(2):  # Expect 2 registerCapability requests (ty and ruff)
        req_id, params = await client.read_request('client/registerCapability')
        log("client", f"Got registerCapability: {params.get('registrations', [{}])[0].get('id')}")
        await client.respond(req_id, None)

    # Open main.py
    log("client", "Opening main.py")
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test-project/main.py',
            'version': 1,
            'languageId': 'python',
            'text': 'def foo():\n    pass\n'
        }
    })

    # Collect initial diagnostics (expect exactly 2: from ty and ruff)
    log("client", "Collecting initial diagnostics...")
    await client.read_notification('$/streamDiagnostics')
    log("client", "Got first diagnostic for main.py")
    await client.read_notification('$/streamDiagnostics')
    log("client", "Got second diagnostic for main.py")

    # Now send didChangeWatchedFiles for nearby.py
    # This should only match ty's watchers (watching **/*, i.e., all Python files)
    # It should NOT match ruff's watchers (only *.toml files)
    log("client", "Sending didChangeWatchedFiles for nearby.py...")
    await client.notify('workspace/didChangeWatchedFiles', {
        'changes': [
            {
                'uri': 'file:///tmp/test-project/nearby.py',
                'type': 2  # Changed
            }
        ]
    })

    # Try to collect diagnostics after the file change notification
    # We should NOT get diagnostics for main.py again
    log("client", "Checking for spurious diagnostics...")
    post_change_main_diag_count = 0
    try:
        async def collect_post_change():
            nonlocal post_change_main_diag_count
            while payload := await client.read_notification('$/streamDiagnostics'):
                uri = payload.get('uri')
                log("client", f"Got diagnostic for {uri}")
                if uri == 'file:///tmp/test-project/main.py':
                    post_change_main_diag_count += 1
                    log("client", f"WARNING: Got spurious diagnostic for main.py!")

        await asyncio.wait_for(collect_post_change(), timeout=1.0)
    except asyncio.TimeoutError:
        log("client", "Timeout - no more diagnostics")

    # Assert we didn't get diagnostics for main.py after the file change
    assert post_change_main_diag_count == 0, \
        f"Expected no diagnostics for main.py after nearby.py change, got {post_change_main_diag_count}"

    log("client", "SUCCESS: No spurious diagnostics for main.py")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
