#!/usr/bin/env python
"""
Test that resync diffs split lines only at LSP line endings (#57).

The LSP specification ends lines at LF, CRLF and CR.  str.splitlines
also breaks at form feeds, U+2028 and others, which shifted the ranges
rass computed for incremental servers.  Each document has those
characters, or a lone CR, before the edited line.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

URI = 'file:///tmp/test.py'
CASES = [
    ('page\x0c\nline sep\nlast\n', 'page\x0c\nline sep\nLAST\n'),
    ('one\rtwo\nthree\n', 'one\rtwo\nTHREE\n'),
    ('crlf\r\nnel\x85vt\x0bx\nend', 'crlf\r\nnel\x85vt\x0bx\nEND'),
    # Edits next to a CRLF pair, which a change must neither split nor
    # form at its edges
    ('a\r\nb\n', 'a\nb\n'),
    ('a\r\nb\n', 'a\rb\n'),
    ('x\r\ny\n', 'x\r\r\ny\n'),
    ('a\r', 'a\r\nb'),
    ('cr\rx\nlf', 'cr\r\nlf'),
]


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
                'text': '',
            }
        },
    )
    version = 1
    for old, new in CASES:
        for text in (old, new):
            version += 1
            await client.notify(
                'textDocument/didChange',
                {
                    'textDocument': {'uri': URI, 'version': version},
                    'contentChanges': [{'text': text}],
                },
            )
        await client.notify(
            'textDocument/didSave', {'textDocument': {'uri': URI}}
        )

        for _ in range(2):
            report = await asyncio.wait_for(
                client.read_notification('rass-test/docText'), timeout=5
            )
            log('client', f"{report['server']} has {report['text']!r}")
            assert not report['errors'], report['errors']
            assert report['text'] == new, (
                f"{report['server']} expected {new!r}, got {report['text']!r}"
            )

    log('client', 'All assertions passed')
    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
