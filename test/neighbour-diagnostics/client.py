#!/usr/bin/env python
"""Test streamed diagnostics for a changed document and its neighbour."""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint

A = 'file:///tmp/a.py'
B = 'file:///tmp/b.py'

async def reports(client, n):
    """Read N $/streamDiagnostics as (uri, version, server), then no more."""
    got = set()
    for _ in range(n):
        p = await client.read_notification('$/streamDiagnostics')
        got.add((p['uri'], p['version'], p['token'].split('-')[0]))
    await client.assert_no_message_pending(timeout_sec=0.5)
    return got

async def main():
    client = await LspTestEndpoint.create()
    await client.initialize()
    for uri in (A, B):
        await client.notify('textDocument/didOpen', {
            'textDocument': {
                'uri': uri, 'languageId': 'python', 'version': 0, 'text': '',
            }
        })
    await reports(client, 4)

    await client.notify('textDocument/didChange', {
        'textDocument': {'uri': A, 'version': 1},
        'contentChanges': [{'text': 'boom'}],
    })
    got = await reports(client, 3)
    assert got == {(A, 1, 's1'), (A, 1, 's2'), (B, 0, 's1')}, got

    # "boom!" keeps the diagnostics, so s1's "unchanged" report for
    # the neighbour must be dropped.
    await client.notify('textDocument/didChange', {
        'textDocument': {'uri': A, 'version': 2},
        'contentChanges': [{'text': 'boom!'}],
    })
    got = await reports(client, 2)
    assert got == {(A, 2, 's1'), (A, 2, 's2')}, got

    await client.notify('textDocument/didChange', {
        'textDocument': {'uri': A, 'version': 3},
        'contentChanges': [{'text': 'x'}],
    })
    got = await reports(client, 3)
    assert got == {(A, 3, 's1'), (A, 3, 's2'), (B, 0, 's1')}, got

    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
