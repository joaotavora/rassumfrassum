#!/usr/bin/env python3
"""
Test that didChangeWatchedFiles is filtered based on glob patterns.

This test verifies that when a file change notification is sent, rass only
forwards it to servers whose watchers match the changed file's URI.
"""

import asyncio
from pathlib import Path

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test file watcher filtering."""

    client = await LspTestEndpoint.create()

    # Get fixture directory path
    fixture_dir = Path(__file__).parent / 'fixture'
    root_uri = fixture_dir.resolve().as_uri()

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
    await client.initialize(capabilities=capabilities, rootUri=root_uri)

    # Handle client/registerCapability requests from servers
    # Both ty and ruff will send these
    log("client", "Handling registerCapability requests...")
    for _ in range(2):  # Expect 2 registerCapability requests (ty and ruff)
        req_id, params = await client.read_request('client/registerCapability')
        log("client", f"Got registerCapability: {params.get('registrations', [{}])[0].get('id')}")
        await client.respond(req_id, None)

    # Open main.py
    log("client", "Opening main.py")
    main_uri = (fixture_dir / 'main.py').resolve().as_uri()
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': main_uri,
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
    nearby_uri = (fixture_dir / 'nearby.py').resolve().as_uri()
    await client.notify('workspace/didChangeWatchedFiles', {
        'changes': [
            {
                'uri': nearby_uri,
                'type': 2  # Changed
            }
        ]
    })

    # Try to collect diagnostics after the nearby.py change
    # We should NOT get diagnostics since nearby.py was correctly filtered
    log("client", "Checking that nearby.py was filtered...")
    got_diag_after_nearby = False
    try:
        diag = await asyncio.wait_for(
            client.read_notification('$/streamDiagnostics'),
            timeout=1.0
        )
        log("client", f"WARNING: Got unexpected diagnostic for {diag.get('uri')}")
        got_diag_after_nearby = True
    except asyncio.TimeoutError:
        log("client", "Timeout - no diagnostics as expected")

    assert not got_diag_after_nearby, "Expected no diagnostics after nearby.py change"
    log("client", "SUCCESS: nearby.py notification correctly filtered out")

    # Now send didChangeWatchedFiles for pyproject.toml
    # This should match ruff's watchers (*.toml files)
    # We expect ruff to re-analyze and send diagnostics for main.py
    log("client", "Sending didChangeWatchedFiles for pyproject.toml...")
    toml_uri = (fixture_dir / 'pyproject.toml').resolve().as_uri()
    await client.notify('workspace/didChangeWatchedFiles', {
        'changes': [
            {
                'uri': toml_uri,
                'type': 2  # Changed
            }
        ]
    })

    # Wait for diagnostics from ruff for main.py
    log("client", "Waiting for diagnostic for main.py from ruff...")
    ruff_diag = await client.read_notification('$/streamDiagnostics')
    assert ruff_diag.get('uri') == main_uri, \
        f"Expected diagnostic for main.py, got {ruff_diag.get('uri')}"
    log("client", "SUCCESS: Got diagnostic for main.py from ruff after toml change")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
