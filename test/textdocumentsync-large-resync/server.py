#!/usr/bin/env python
"""Server for the textdocumentsync-large-resync test.

Applies didChange content changes to its own copy of the document,
splitting lines at LF, CRLF and CR as the LSP specification defines.
On didSave, sends a SHA-256 of that copy upstream in a
'rass-test/docHash' notification, so the client can check it without
a huge message.
"""

import argparse
import hashlib
import re

from rassumfrassum.json import write_message_sync
from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument(
    '--text-document-sync',
    type=int,
    required=True,
    help='1 = full, 2 = incremental',
)
args = parser.parse_args()

state = {'doc': ''}


def offset(text, pos):
    """Offset of an LSP position (code points = UTF-16 units here).

    Like the LSP specification, clamps a line past the end to the end
    of the document and a character past the end of a line to the end
    of that line's content, so a position inside a CRLF pair lands
    before the CR."""
    line_starts = [0] + [m.end() for m in re.finditer(r'\r\n|\r|\n', text)]
    if pos['line'] >= len(line_starts):
        return len(text)
    start = line_starts[pos['line']]
    end = re.compile(r'\r\n|\r|\n').search(text, start)
    content_end = end.start() if end else len(text)
    return min(start + pos['character'], content_end)


def apply_changes(text, changes):
    """Apply didChange content changes in order (see LSP spec)."""
    for change in changes:
        new = change.get('text', '')
        if (r := change.get('range')) is None:
            text = new
        else:
            start = offset(text, r['start'])
            end = offset(text, r['end'])
            text = text[:start] + new + text[end:]
    return text


def did_open(params):
    state['doc'] = params['textDocument']['text']


def did_change(params):
    state['doc'] = apply_changes(state['doc'], params['contentChanges'])


def did_save(params):
    write_message_sync(
        {
            'jsonrpc': '2.0',
            'method': 'rass-test/docHash',
            'params': {
                'server': args.name,
                'sha256': hashlib.sha256(state['doc'].encode()).hexdigest(),
            },
        }
    )


run_toy_server(
    name=args.name,
    capabilities={
        'textDocumentSync': {
            'change': args.text_document_sync,
            'openClose': True,
            'save': True,
        },
    },
    notification_handlers={
        'textDocument/didOpen': did_open,
        'textDocument/didChange': did_change,
        'textDocument/didSave': did_save,
    },
)
