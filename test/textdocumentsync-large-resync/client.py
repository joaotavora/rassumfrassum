#!/usr/bin/env python
"""
Test that a resync of a large, repetitive document is diffed quickly
(#58).

difflib's SequenceMatcher takes tens of seconds on 30,000 alternating
lines, blocking rass's event loop.  The server's report must arrive
within a few seconds and match the new text.
"""

import asyncio
import hashlib

from rassumfrassum.test2 import LspTestEndpoint, log

URI = 'file:///tmp/test.py'
OPEN = ''.join(f'x = {i % 2}\n' for i in range(30000))
RESYNC = OPEN.replace('x = 1\n', 'y = 1\n', 1)


async def main():
    client = await LspTestEndpoint.create()
    await client.initialize()

    await client.notify(
        'textDocument/didOpen',
        {
            'textDocument': {
                'uri': URI,
                'languageId': 'python',
                'version': 1,
                'text': OPEN,
            }
        },
    )
    await client.notify(
        'textDocument/didChange',
        {
            'textDocument': {'uri': URI, 'version': 2},
            'contentChanges': [{'text': RESYNC}],
        },
    )
    await client.notify('textDocument/didSave', {'textDocument': {'uri': URI}})

    report = await asyncio.wait_for(
        client.read_notification('rass-test/docHash'), timeout=5
    )
    expected = hashlib.sha256(RESYNC.encode()).hexdigest()
    assert report['sha256'] == expected, (
        f"{report['server']} has the wrong text"
    )

    log('client', 'All assertions passed')
    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
