#!/usr/bin/env python3
"""
Test client for the vuetail preset with vue-language-server v3.

vue-language-server v3 is unusable unless the client (here, rass
itself via the vuetail preset) brokers its 'tsserver/request'
notifications to a typescript-language-server: it blocks right after
'didOpen' waiting for project info and never answers anything.  So
simply getting answers out of it is proof that the brokering works.
"""

import asyncio
import json
import os

from rassumfrassum.test2 import LspTestEndpoint, log, scaled_timeout


async def pump_until_response(client: LspTestEndpoint, req_id: int):
    """Wait for the response to req_id, babysitting the servers meanwhile.

    The real-world servers in this test (tailwind especially) ask for
    'workspace/configuration' and other client services at their own
    leisure, so answer those blandly instead of expecting them at
    fixed points like simpler tests do.
    """
    while True:
        msg = await client.read_message(timeout_sec=scaled_timeout(60))
        if 'id' in msg and 'method' in msg:
            # A server-to-client request: answer blandly
            if msg['method'] == 'workspace/configuration':
                items = msg.get('params', {}).get('items', [])
                result = [None] * len(items)
            else:
                result = None
            await client.respond(msg['id'], result)
            log(client.name, f"Answered server request {msg['method']}")
        elif 'method' in msg:
            log(client.name, f"Skipping notification {msg['method']}")
        elif msg.get('id') == req_id:
            return msg
        else:
            log(client.name, f"Skipping response id={msg.get('id')}")


def symbol_names(symbols) -> set[str]:
    """Collect names from DocumentSymbol[]/SymbolInformation[]."""
    names = set()
    for s in symbols or []:
        names.add(s.get('name'))
        names |= symbol_names(s.get('children'))
    return names


async def main():
    client = await LspTestEndpoint.create()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_project = os.path.join(test_dir, "fixture")
    os.chdir(test_project)

    capabilities = {
        'workspace': {'configuration': True},
        'textDocument': {
            'publishDiagnostics': {'versionSupport': False},
            'hover': {'contentFormat': ['markdown', 'plaintext']},
        },
    }

    init_response = await client.initialize(
        capabilities=capabilities, rootUri=f"file://{test_project}"
    )
    server_caps = init_response.get('result', {}).get('capabilities', {})
    assert server_caps.get('documentSymbolProvider'), \
        "Expected documentSymbolProvider in merged capabilities"
    assert server_caps.get('hoverProvider'), \
        "Expected hoverProvider in merged capabilities"

    # Open the .vue single-file component
    file_path = os.path.join(test_project, "src/App.vue")
    with open(file_path, 'r') as f:
        file_content = f.read()
    file_uri = f"file://{file_path}"

    log(client.name, f"Opening {file_uri}")
    await client.notify(
        'textDocument/didOpen',
        {
            'textDocument': {
                'uri': file_uri, 'languageId': 'vue',
                'version': 1, 'text': file_content,
            }
        },
    )

    # vue-language-server v3 won't answer this (or anything) unless
    # its tsserver/request dance succeeded.
    log(client.name, "Requesting documentSymbol...")
    req_id = await client.request(
        'textDocument/documentSymbol', {'textDocument': {'uri': file_uri}}
    )
    response = await pump_until_response(client, req_id)
    names = symbol_names(response.get('result'))
    log(client.name, f"Got symbols: {names}")
    assert 'greeting' in names and 'shout' in names, \
        f"Expected 'greeting' and 'shout' symbols, got {names}"

    # Hover over 'greeting' in the <script> part.  In the v3
    # architecture this type information can only come out of
    # tsserver with a working '@vue/typescript-plugin'.
    log(client.name, "Requesting hover over 'greeting'...")
    req_id = await client.request(
        'textDocument/hover',
        {
            'textDocument': {'uri': file_uri},
            'position': {'line': 1, 'character': 8},
        },
    )
    response = await pump_until_response(client, req_id)
    contents = json.dumps(response.get('result') or {})
    log(client.name, f"Got hover: {contents}")
    assert 'string' in contents, \
        f"Expected hover mentioning 'string', got {contents}"

    log(client.name, "OK! vue-language-server v3 is alive and typed!")

    await client.byebye()


if __name__ == '__main__':
    asyncio.run(main())
