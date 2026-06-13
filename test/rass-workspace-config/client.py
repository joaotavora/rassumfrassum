#!/usr/bin/env python
"""Client for rass-workspace-config test.

Verifies that the 'rass' key in workspace/configuration response items is
stripped before forwarding, and that server-specific overlays are merged
in for matching servers only.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    client = await LspTestEndpoint.create()
    await client.initialize()

    # Both servers send workspace/configuration requests after initialized
    req_ids = []
    for _ in range(2):
        req_id, _params = await client.read_request('workspace/configuration')
        req_ids.append(req_id)

    # Respond with a config containing a 'rass' overlay for the second server
    for req_id in req_ids:
        await client.respond(req_id, [
            {
                'commonOption': 'common',
                'rass': {
                    's2': {'extraOption': 'extra'},  # matches server-reported name 's2'
                },
            }
        ])

    # Collect what each server actually received after rass filtering
    reports = {}
    for _ in range(2):
        notif = await client.read_notification('rass-test/configReceived')
        reports[notif['server']] = notif['config']
        log('client', f"Got report from {notif['server']}: {notif['config']}")

    # s1 matched no regex: receives only generic options, no 'rass' key
    assert reports['s1'] == {'commonOption': 'common'}, \
        f"s1 expected common only, got: {reports['s1']}"

    # s2 matched '#1': receives generic options merged with overlay
    assert reports['s2'] == {'commonOption': 'common', 'extraOption': 'extra'}, \
        f"s2 expected merged opts, got: {reports['s2']}"

    log('client', 'All assertions passed')
    await client.byebye()

if __name__ == '__main__':
    asyncio.run(main())
