#!/usr/bin/env python3
"""
Test that didChange on one file doesn't clear diagnostics for other files.

Regression test for bug where didChange cleanup deleted ALL dispatched
aggregations, causing other files' diagnostics to be reset to empty.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log, scaled_timeout


async def main():
    """Test that diagnostics persist for unchanged files."""

    client = await LspTestEndpoint.create()

    # Initialize with workspace support so ruff tracks files properly
    init_caps = {
        'workspace': {
            'workspaceFolders': True,
        }
    }
    _ = await client.initialize(capabilities=init_caps, rootUri='file:///tmp')

    # Open file A with a typo
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/fileA.py',
            'version': 0,
            'languageId': 'python',
            'text': '# comment with typo: speling\nBLA=str;\n'
        }
    })

    # Open file B with a typo
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/fileB.py',
            'version': 0,
            'languageId': 'python',
            'text': '# comment with typo: speling\n'
        }
    })

    # Collect initial diagnostics
    diagnostics_by_uri = {}
    async def collect_diags():
        """Collect diagnostic notifications."""
        while payload := await client.read_notification('textDocument/publishDiagnostics'):
            uri = payload['uri']
            diags = payload.get('diagnostics', [])
            diagnostics_by_uri[uri] = diags
            log("client", f"Got {len(diags)} diagnostic(s) for {uri}")

    try:
        await asyncio.wait_for(collect_diags(), timeout=scaled_timeout(1.5))
    except asyncio.TimeoutError:
        pass

    # Check we got initial diagnostics for fileB
    a_before = diagnostics_by_uri.get('file:///tmp/fileA.py', [])
    b_before = diagnostics_by_uri.get('file:///tmp/fileB.py', [])
    assert len(a_before) > 0, "fileA should have initial diagnostics!"
    assert len(b_before) > 0, "fileB should have initial diagnostics!"

    # Now change fileA
    await client.notify('textDocument/didChange', {
        'textDocument': {
            'uri': 'file:///tmp/fileA.py',
            'version': 1
        },
        'contentChanges': [{'text': '# changed comment, still has typo: speling\nBLA=str;\n'}]
    })
    await client.notify('workspace/didChangeWatchedFiles', {
        "changes": [
            {
                "uri": 'file:///tmp/fileA.py',
                "type": 2
            }
        ]
    })
    # Save fileA
    await client.notify('textDocument/didSave', {
        'textDocument': {
            'uri': 'file:///tmp/fileA.py'
        }
    })

    # Collect diagnostics after the change
    try:
        await asyncio.wait_for(collect_diags(), timeout=scaled_timeout(1.5))
    except asyncio.TimeoutError:
        pass

    a_after = diagnostics_by_uri.get('file:///tmp/fileA.py', [])
    b_after = diagnostics_by_uri.get('file:///tmp/fileB.py', [])

    assert b_after == b_before, "fileB should have kept diagnostics!"

    assert len(a_after) == len(a_before), "fileA should have kept diagnostics!"
    # brittle, since order could be changed...
    assert [s['source'] for s in a_after] == [s['source'] for s in a_before]

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
