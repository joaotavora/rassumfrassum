#!/usr/bin/env python3
"""
Client that sends three back-to-back textDocument/diagnostic requests.
Tests that server handles them in parallel (should take ~5 seconds)
vs sequentially (would take ~15 seconds).
"""

import asyncio
import time

from rassumfrassum.test2 import LspTestEndpoint, log

async def main():
    """Send three textDocument/diagnostic requests back-to-back."""

    client = await LspTestEndpoint.create()

    # Initialize
    await client.initialize()

    # Open a document
    await client.notify('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///tmp/test.py',
            'languageId': 'python',
            'version': 1,
            'text': 'print("hello")\n'
        }
    })

    # Send three slow requests back-to-back
    log("client", "Sending 3 dummy/slowRequest requests")
    start_time = time.time()

    req_id1 = await client.request('dummy/slowRequest', {})
    req_id2 = await client.request('dummy/slowRequest', {})
    req_id3 = await client.request('dummy/slowRequest', {})

    log("client", f"Sent all 3 requests at t={time.time() - start_time:.2f}s")

    # Wait for all three responses
    resp1 = await client.read_response(req_id1)
    log("client", f"Got response 1 at t={time.time() - start_time:.2f}s")

    resp2 = await client.read_response(req_id2)
    log("client", f"Got response 2 at t={time.time() - start_time:.2f}s")

    resp3 = await client.read_response(req_id3)
    elapsed = time.time() - start_time
    log("client", f"Got response 3 at t={elapsed:.2f}s")

    # Check that all responses are valid
    assert 'result' in resp1, f"Expected result in response 1: {resp1}"
    assert 'result' in resp2, f"Expected result in response 2: {resp2}"
    assert 'result' in resp3, f"Expected result in response 3: {resp3}"

    # The key assertion: Since the server handles requests with async handlers,
    # they execute in parallel. All three 5-second requests complete in ~5 seconds total.
    log("client", f"Total elapsed time: {elapsed:.2f}s")

    # Allow some tolerance for timing
    if elapsed < 4:
        log("client", f"ERROR: Took {elapsed:.2f}s - too fast, something's wrong!")
        raise AssertionError(f"Expected ~5s (parallel), but took {elapsed:.2f}s")
    elif elapsed > 7:
        log("client", f"ERROR: Took {elapsed:.2f}s - too slow, not parallel enough!")
        raise AssertionError(f"Expected ~5s (parallel), but took {elapsed:.2f}s")
    else:
        log("client", f"SUCCESS: Took {elapsed:.2f}s - responses handled in parallel as expected")

    await client.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
