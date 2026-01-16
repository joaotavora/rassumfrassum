#!/usr/bin/env python
"""
Test that textDocument/codeAction aggregates results from all servers
with codeActionProvider capability.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that code actions are aggregated from multiple servers."""

    client = await LspTestEndpoint.create()
    init_response = await client.initialize()

    result = init_response['result']
    capabilities = result.get('capabilities', {})
    has_code_actions = capabilities.get('codeActionProvider')

    log("client", f"Got initialize response with codeActionProvider={has_code_actions}")
    assert has_code_actions, "Expected codeActionProvider to be present in merged capabilities"

    # Send textDocument/codeAction request
    req_id = await client.request('textDocument/codeAction', {
        'textDocument': {'uri': 'file:///test.py'},
        'range': {
            'start': {'line': 0, 'character': 0},
            'end': {'line': 0, 'character': 10}
        },
        'context': {'diagnostics': []}
    })

    # Expect aggregated code action response
    response = await client.read_response(req_id)
    actions = response['result']
    log("client", f"Got {len(actions)} code actions")

    # Should have 2 code actions (from s2 and s3, but not s1)
    assert isinstance(actions, list), f"Expected array of code actions, got: {type(actions)}"
    assert len(actions) == 2, f"Expected 2 code actions (from s2 and s3), got {len(actions)}: {actions}"

    # Verify we got actions from both s2 and s3
    titles = [a['title'] for a in actions]
    assert 'Fix from s2' in titles, f"Expected action from s2, got titles: {titles}"
    assert 'Fix from s3' in titles, f"Expected action from s3, got titles: {titles}"

    log("client", "✓ Code actions correctly aggregated from servers with codeActionProvider")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
