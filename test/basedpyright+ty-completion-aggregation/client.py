#!/usr/bin/env python3
"""
Test client for basedpyright + ty servers.
Tests multi-server completion support.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log


async def main():
    """Test multi-server completions with real servers."""

    client = await LspTestEndpoint.create()

    # Initialize with completion capabilities
    completion_caps = {
        'textDocument': {
            'completion': {
                'dynamicRegistration': False,
                'completionItem': {
                    'snippetSupport': True,
                    'deprecatedSupport': True,
                    'resolveSupport': {
                        'properties': ['documentation', 'details', 'additionalTextEdits']
                    },
                    'tagSupport': {'valueSet': [1]},
                    'insertReplaceSupport': True,
                },
                'contextSupport': True,
            }
        }
    }

    init_response = await client.initialize(capabilities=completion_caps)

    # Verify completionProvider is present
    capabilities = init_response.get('result', {}).get('capabilities', {})
    assert capabilities.get('completionProvider'), "Expected completionProvider in merged capabilities"
    log("client", f"Got completionProvider: {capabilities.get('completionProvider')}")

    # Open a test document
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'version': 0,
            'languageId': 'python',
            'text': 'import sys\n\nsys.'
        }
    })

    # Request completions at position after "sys."
    req_id = await client.request('textDocument/completion', {
        'textDocument': {'uri': 'file:///tmp/test.py'},
        'position': {'line': 2, 'character': 4},
        'context': {'triggerKind': 2, 'triggerCharacter': '.'}
    })

    # Read completion response
    comp_response = await client.read_response(req_id)
    result = comp_response['result']
    items = result.get('items', [])

    log("client", f"Got {len(items)} completion items")
    assert len(items) > 0, "Expected at least one completion item"

    # Check if items have data fields (should be stashed)
    items_with_data = [item for item in items if 'data' in item]
    log("client", f"Found {len(items_with_data)} items with data fields")

    # Find an item without documentation to resolve
    probe = next((item for item in items if 'data' in item and 'documentation' not in item), None)
    assert probe is not None, "Expected to find at least one item with data but no documentation"
    log("client", f"Found item to resolve: {probe['label']}")

    # Send completionItem/resolve request
    resolve_id = await client.request('completionItem/resolve', probe)

    # Read resolve response
    resolve_response = await client.read_response(resolve_id)
    resolved_item = resolve_response['result']

    log("client", f"Resolved item: {resolved_item['label']}")

    # Check that the resolved item now has documentation
    assert resolved_item.get('documentation'), \
        f"Expected documentation in resolved item, got: {resolved_item}"
    log("client", "Successfully got documentation after resolve")

    # Test '[' trigger character (only basedpyright supports this)
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test2.py',
            'version': 0,
            'languageId': 'python',
            'text': 'x = {"result" = 42}\nx[\n'
        }
    })

    # Request completions with '[' trigger
    bracket_id = await client.request('textDocument/completion', {
        'textDocument': {'uri': 'file:///tmp/test2.py'},
        'position': {'line': 1, 'character': 2},
        'context': {'triggerKind': 2, 'triggerCharacter': '['}
    })

    # Read response
    bracket_response = await client.read_response(bracket_id)
    bracket_items = bracket_response['result'].get('items', [])

    log("client", f"Got {len(bracket_items)} items for '[' trigger")

    # Should only get items from basedpyright (ty doesn't support '[')
    # FIXME: we verify it is indeed so from the logs, but
    # unfortunately, there's not much I can assert here. Also
    # basedpyright in this test answers with a bucketload of
    # irrelevant completions, but in the same environment with a real
    # client it responds with just one completion. Investigate this.

    await client.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
