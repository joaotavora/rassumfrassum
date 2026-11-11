#!/usr/bin/env python
"""Test streamed pull diagnostics from the real tsc --lsp server."""

import asyncio
from pathlib import Path

from rassumfrassum.test2 import LspTestEndpoint, scaled_timeout


async def read_report(client, uri):
    while True:
        message = await client.read_message(timeout_sec=scaled_timeout(10))
        method = message.get('method')
        if method == 'client/registerCapability':
            await client.respond(message['id'], None)
        elif method == '$/streamDiagnostics' and message['params']['uri'] == uri:
            return message['params']
        else:
            assert 'id' not in message, message


async def main():
    client = await LspTestEndpoint.create()
    project = Path(__file__).resolve().parent / 'fixture'
    document = project / 'main.ts'
    uri = document.as_uri()

    req_id = await client.request('initialize', {
        'processId': None,
        'rootUri': project.as_uri(),
        'capabilities': {
            'textDocument': {'$streamingDiagnostics': True},
            'general': {'positionEncodings': ['utf-16']},
        },
    })
    response = await client.read_response(req_id)
    assert 'error' not in response, response
    assert response['result']['capabilities'], response
    await client.notify('initialized', {})

    # The first internal pull has no previousResultId. Sending null
    # instead of omitting it makes tsc reject the request.
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': uri,
            'languageId': 'typescript',
            'version': 1,
            'text': document.read_text(),
        },
    })
    report = await asyncio.wait_for(
        read_report(client, uri), scaled_timeout(10)
    )
    assert report['uri'] == uri, report
    assert report['version'] == 1, report
    assert report['kind'] == 'full', report
    diagnostics = report.get('diagnostics', [])
    assert len(diagnostics) == 1, diagnostics
    assert diagnostics[0]['code'] == 2322, diagnostics
    assert diagnostics[0]['severity'] == 1, diagnostics

    # Fix the error in memory and check that subsequent pulls still work.
    await client.notify('textDocument/didChange', {
        'textDocument': {'uri': uri, 'version': 2},
        'contentChanges': [{'text': 'const value: number = 42;\n'}],
    })
    updated = await asyncio.wait_for(
        read_report(client, uri), scaled_timeout(10)
    )
    assert updated['uri'] == uri, updated
    assert updated['version'] == 2, updated
    assert updated['token'] == report['token'], updated
    assert updated['kind'] == 'full', updated
    assert not updated.get('diagnostics'), updated

    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
