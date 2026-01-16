#!/usr/bin/env python
"""Server for serverinfo-merge test"""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--version', default='1.0.0')
args = parser.parse_args()

run_toy_server(name=args.name, version=args.version)
