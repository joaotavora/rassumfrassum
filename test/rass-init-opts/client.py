#!/usr/bin/env python
"""Client for rass-init-opts test.

Verifies that the 'rass' sub-object in initializationOptions is stripped
before forwarding, and that server-specific overlays (keyed by regex
matching the executable name) are merged in for matching servers only.
"""

import asyncio
import os
from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    client = await LspTestEndpoint.create()

    req_id = await client.request('initialize', {
        'rootUri': f'file://{os.getcwd()}',
        'capabilities': {
            'textDocument': {},
            'general': {'positionEncodings': ['utf-16']},
        },
        'initializationOptions': {
            'commonSetting': 'common',
            'rass': {
                '#1': {'extraSetting': 'extra'},  # matches executable name 'python#1'
            },
        },
    })
    await client.read_response(req_id)
    await client.notify('initialized', {})

    # Collect both reports (order may vary)
    reports = {}
    for _ in range(2):
        notif = await client.read_notification('rass-test/initOptions')
        reports[notif['server']] = notif['initializationOptions']
        log('client', f"Got report from {notif['server']}: {notif['initializationOptions']}")

    # s1 matched no regex: receives only generic options, no 'rass' key
    assert reports['s1'] == {'commonSetting': 'common'}, \
        f"s1 expected {{'commonSetting': 'common'}}, got: {reports['s1']}"

    # s2 matched the 's2' pattern: receives generic options merged with overlay
    assert reports['s2'] == {'commonSetting': 'common', 'extraSetting': 'extra'}, \
        f"s2 expected merged opts, got: {reports['s2']}"

    log('client', 'All assertions passed')
    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
