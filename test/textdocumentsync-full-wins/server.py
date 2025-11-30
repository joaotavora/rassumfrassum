#!/usr/bin/env python3
"""
Server that reports configurable textDocumentSync capability.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from jaja import read_message_sync, write_message_sync
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--text-document-sync', type=int, default=2,
                   help='textDocumentSync value: 1=Full, 2=Incremental')
args = parser.parse_args()

def log(msg):
    print(msg, file=sys.stderr)

log(f"[{args.name}] Started with textDocumentSync={args.text_document_sync}!")

while True:
    try:
        message = read_message_sync()
        if message is None:
            break

        method = message.get('method')
        msg_id = message.get('id')

        if method == 'initialize':
            response = {
                'jsonrpc': '2.0',
                'id': msg_id,
                'result': {
                    'capabilities': {
                        'textDocumentSync': args.text_document_sync,
                        'hoverProvider': True,
                    },
                    'serverInfo': {
                        'name': args.name,
                        'version': '1.0.0'
                    }
                }
            }
            write_message_sync(response)

        elif method == 'shutdown':
            response = {
                'jsonrpc': '2.0',
                'id': msg_id,
                'result': None
            }
            write_message_sync(response)
            log(f"[{args.name}] shutting down")
            break

        elif method in ('initialized', 'textDocument/didOpen', 'textDocument/didChange'):
            log(f"[{args.name}] got notification {method}")

        else:
            if msg_id is not None:
                log(f"[{args.name}] request {method} (id={msg_id})")
            else:
                log(f"[{args.name}] notification {method}")

    except Exception as e:
        log(f"[{args.name}] Error: {e}")
        break

log(f"[{args.name}] stopped")
