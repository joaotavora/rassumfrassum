#!/usr/bin/env python3
"""Server for server-request test"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from server_common import run_server, log, write_message_sync
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--send-request-after-init', action='store_true')
args = parser.parse_args()

run_server(
    name=args.name,
    on_initialized=lambda: (
        log(args.name, "Sending request to client: workspace/configuration"),
        write_message_sync({
            'jsonrpc': '2.0',
            'id': 999,
            'method': 'workspace/configuration',
            'params': {'items': [{'section': 'python'}]}
        })
    ) if args.send_request_after_init else None
)
