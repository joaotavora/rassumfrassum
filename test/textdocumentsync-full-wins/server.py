#!/usr/bin/env python
"""
Server that reports configurable textDocumentSync capability.
"""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--text-document-sync', type=int, default=2,
                   help='textDocumentSync value: 1=Full, 2=Incremental')
args = parser.parse_args()

run_toy_server(
    name=args.name,
    capabilities={
        'textDocumentSync': args.text_document_sync,
        'hoverProvider': True,
    }
)
