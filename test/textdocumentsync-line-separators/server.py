#!/usr/bin/env python
"""Server for textdocumentsync-line-separators test: mirrors the document and reports it on didSave.

Applies didChange content changes to its own copy of the document,
splitting lines at LF, CRLF and CR as the LSP specification defines,
and notes any change
whose shape doesn't match the advertised sync kind.  On didSave, sends
the copy and those notes upstream in a 'rass-test/docText' notification
so the client can check them.  (A server that exits on a failed check
doesn't make run.sh fail.)
"""

import argparse
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

state = {'doc': '', 'errors': []}


def offset(text, pos):
    """Offset of an LSP position (code points = UTF-16 units here)."""
    line_starts = [0] + [m.end() for m in re.finditer(r'\r\n|\r|\n', text)]
    if pos['line'] >= len(line_starts):
        return len(text)
    return line_starts[pos['line']] + pos['character']


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
    changes = params['contentChanges']
    if args.text_document_sync == 1:
        if not (len(changes) == 1 and 'range' not in changes[0]):
            state['errors'].append(f"full-sync server got {changes}")
    elif not all('range' in c for c in changes):
        state['errors'].append(f"incremental server got {changes}")
    state['doc'] = apply_changes(state['doc'], changes)


def did_save(params):
    write_message_sync(
        {
            'jsonrpc': '2.0',
            'method': 'rass-test/docText',
            'params': {
                'server': args.name,
                'text': state['doc'],
                'errors': state['errors'],
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
