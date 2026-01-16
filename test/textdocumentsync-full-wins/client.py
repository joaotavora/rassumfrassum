#!/usr/bin/env python
"""
Test that textDocumentSync=1 (Full) wins over textDocumentSync=2 (Incremental).
Even if the primary server reports Incremental, if any secondary server reports
Full, the merged capability should be Full.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Test that textDocumentSync=1 wins."""

    client = await LspTestEndpoint.create()
    init_response = await client.initialize()

    result = init_response['result']
    capabilities = result.get('capabilities', {})
    text_doc_sync = capabilities.get('textDocumentSync')

    log("client", f"Got initialize response with textDocumentSync={text_doc_sync}")

    # The key assertion: textDocumentSync should be 1 (Full)
    # because s1 (secondary) has textDocumentSync=1, even though s2 (primary) has textDocumentSync=2
    assert text_doc_sync == 1, \
        f"Expected textDocumentSync=1 (Full) to win, but got: {text_doc_sync}"

    log("client", "✓ textDocumentSync=1 correctly won over textDocumentSync=2")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
