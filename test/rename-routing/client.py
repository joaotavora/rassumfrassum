#!/usr/bin/env python
"""
Test that textDocument/rename routes to the first server with renameProvider.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that rename routes to first server with renameProvider."""

    client = await LspTestEndpoint.create()
    init_response = await client.initialize()

    result = init_response['result']
    capabilities = result.get('capabilities', {})
    has_rename = capabilities.get('renameProvider')

    log("client", f"Got initialize response with renameProvider={has_rename}")
    assert has_rename, "Expected renameProvider to be present in merged capabilities"

    # Send textDocument/rename request
    req_id = await client.request('textDocument/rename', {
        'textDocument': {'uri': 'file:///test.py'},
        'position': {'line': 0, 'character': 0},
        'newName': 'newName'
    })

    # Expect rename response from ONLY s2 (first server with renameProvider)
    response = await client.read_response(req_id)
    workspace_edit = response['result']
    log("client", f"Got rename response: {workspace_edit}")

    # Should be from s2 only (no aggregation, early termination)
    changes = workspace_edit.get('changes', {})
    assert 'file:///test.py' in changes, f"Expected changes for file:///test.py"

    edits = changes['file:///test.py']
    assert len(edits) == 1, f"Expected 1 edit (from s2 only), got {len(edits)}: {edits}"

    new_text = edits[0]['newText']
    assert new_text == 'renamed_by_s2', f"Expected rename from s2, got: {new_text}"

    log("client", "✓ Rename correctly routed to first server with renameProvider (s2)")

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
