#!/usr/bin/env python3
"""Server for parallel-server-requests test"""

import asyncio

from rassumfrassum.test2 import run_toy_server, log

async def handle_slow_request(msg_id, params):
    """Handle dummy/slowRequest with a 5-second delay."""
    log('async-server', f"Starting to handle dummy/slowRequest id={msg_id}")
    await asyncio.sleep(5)
    log('async-server', f"Finished handling dummy/slowRequest id={msg_id}")
    return {'result': 'done'}

run_toy_server(
    name='async-server',
    request_handlers={'dummy/slowRequest': handle_slow_request}
)
