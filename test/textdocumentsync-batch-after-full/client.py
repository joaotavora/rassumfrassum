#!/usr/bin/env python
"""
Test a didChange batch with a full-text change followed by a ranged one
(#59).

Changes in a batch apply in order, so the ranged change edits the text
set by the full-text change.  rass used to stop at the full-text change
and drop the rest.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

URI = 'file:///tmp/test.py'
OPEN = 'old\n'
EXPECTED = 'Xabc\n'


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
            'contentChanges': [
                {'text': 'abc\n'},
                {
                    'range': {
                        'start': {'line': 0, 'character': 0},
                        'end': {'line': 0, 'character': 0},
                    },
                    'text': 'X',
                },
            ],
        },
    )
    await client.notify('textDocument/didSave', {'textDocument': {'uri': URI}})

    for _ in range(2):
        report = await asyncio.wait_for(
            client.read_notification('rass-test/docText'), timeout=5
        )
        log('client', f"{report['server']} has {report['text']!r}")
        assert not report['errors'], report['errors']
        assert report['text'] == EXPECTED, (
            f"{report['server']} expected {EXPECTED!r}, got {report['text']!r}"
        )

    log('client', 'All assertions passed')
    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
