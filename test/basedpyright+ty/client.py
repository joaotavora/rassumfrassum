#!/usr/bin/env python3
"""
Test client for basedpyright + ty servers.
Tests multi-server completion support.
"""

from rassumfrassum.test import do_initialize, do_initialized, do_shutdown, send_and_log, read_response, log

def main():
    """Test multi-server completions with real servers."""

    # Initialize with completion capabilities
    completion_caps = {
        'textDocument': {
            'completion': {
                'dynamicRegistration': False,
                'completionItem': {
                    'snippetSupport': True,
                    'deprecatedSupport': True,
                    'resolveSupport': {
                        'properties': [
                            'documentation',
                            'details',
                            'additionalTextEdits'
                        ]
                    },
                    'tagSupport': {
                        'valueSet': [1]
                    },
                    'insertReplaceSupport': True
                },
                'contextSupport': True
            }
        }
    }

    init_response = do_initialize(capabilities=completion_caps)

    # Verify we got a response with capabilities
    result = init_response.get('result', {})
    capabilities = result.get('capabilities', {})
    assert capabilities, "Expected capabilities in initialize response"

    # Verify completionProvider is present
    assert capabilities.get('completionProvider'), "Expected completionProvider in merged capabilities"
    log("client", f"Got completionProvider: {capabilities.get('completionProvider')}")

    # Send initialized notification
    do_initialized()

    # Open a test document
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didOpen',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test.py',
                'version': 0,
                'languageId': 'python',
                'text': 'import sys\n\nsys.'
            }
        }
    }, "Opening test document")

    # Request completions at position after "sys."
    send_and_log({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'textDocument/completion',
        'params': {
            'textDocument': {'uri': 'file:///tmp/test.py'},
            'position': {'line': 2, 'character': 4},
            'context': {'triggerKind': 2, 'triggerCharacter': '.'}
        }
    }, "Requesting completions")

    # Read completion response
    comp_response = read_response(2)
    result = comp_response['result']
    items = result.get('items', [])

    log("client", f"Got {len(items)} completion items")
    assert len(items) > 0, "Expected at least one completion item"

    # Check if items have data fields (should be stashed)
    items_with_data = [item for item in items if 'data' in item]
    log("client", f"Found {len(items_with_data)} items with data fields")

    # Find an item without documentation to resolve
    probe = next(item for item in items if 'data' in item and 'documentation' not in item)
    log("client", f"Found item to resolve: {probe['label']}")

    # Send completionItem/resolve request
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'completionItem/resolve',
        'params': probe
    }, f"Resolving item: {probe['label']}")

    # Read resolve response
    resolve_response = read_response(3)
    resolved_item = resolve_response['result']

    log("client", f"Resolved item: {resolved_item['label']}")

    # Check that the resolved item now has documentation
    assert resolved_item.get('documentation'), \
        f"Expected documentation in resolved item, got: {resolved_item}"
    log("client", "Successfully got documentation after resolve")

    # Test '[' trigger character (only basedpyright supports this)
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'textDocument/didOpen',
        'params': {
            'textDocument': {
                'uri': 'file:///tmp/test2.py',
                'version': 0,
                'languageId': 'python',
                'text': 'x = {"result" =  42}\nx[\n'
            }
        }
    }, "Opening test document with some '[]'")

    # Request completions with '[' trigger
    send_and_log({
        'jsonrpc': '2.0',
        'id': 4,
        'method': 'textDocument/completion',
        'params': {
            'textDocument': {'uri': 'file:///tmp/test2.py'},
            'position': {'line': 1, 'character': 2},
            'context': {'triggerKind': 2, 'triggerCharacter': '['}
        }
    }, "Requesting completions with '[' trigger")

    # Read response
    bracket_response = read_response(4)
    bracket_items = bracket_response['result'].get('items', [])

    log("client", f"Got {len(bracket_items)} items for '[' trigger")

    # Should only get items from basedpyright (ty doesn't support '[')
    # FIXME: we verify it is indeed so from the logs, but
    # unfortunately, there's not much I can assert here.  Also
    # basedpyright in this test answers with a bucketload of
    # irrelevant completions, but in the same environment with a real
    # client it responds with just one completion.  Investigate this.

    # Shutdown
    do_shutdown()

if __name__ == '__main__':
    main()
