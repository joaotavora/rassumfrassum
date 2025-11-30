#!/usr/bin/env python3
"""
Server that provides renameProvider capability.
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
parser.add_argument('--has-rename', action='store_true',
                   help='Whether this server provides rename')
args = parser.parse_args()

def log(msg):
    print(msg, file=sys.stderr)

log(f"[{args.name}] Started with renameProvider={args.has_rename}!")

while True:
    try:
        message = read_message_sync()
        if message is None:
            break

        method = message.get('method')
        msg_id = message.get('id')

        if method == 'initialize':
            capabilities = {'hoverProvider': True}
            if args.has_rename:
                capabilities['renameProvider'] = True

            response = {
                'jsonrpc': '2.0',
                'id': msg_id,
                'result': {
                    'capabilities': capabilities,
                    'serverInfo': {
                        'name': args.name,
                        'version': '1.0.0'
                    }
                }
            }
            write_message_sync(response)
            log(f"[{args.name}] Sent initialize response")

        elif method == 'textDocument/rename':
            # Return a workspace edit from this server
            response = {
                'jsonrpc': '2.0',
                'id': msg_id,
                'result': {
                    'changes': {
                        'file:///test.py': [
                            {
                                'range': {
                                    'start': {'line': 0, 'character': 0},
                                    'end': {'line': 0, 'character': 10}
                                },
                                'newText': f'renamed_by_{args.name}'
                            }
                        ]
                    }
                }
            }
            write_message_sync(response)
            log(f"[{args.name}] Sent rename response")

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
