#!/usr/bin/env python
"""Server for initialize-minimal-capabilities test."""

import argparse

from rassumfrassum.test2 import run_toy_server

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
args = parser.parse_args()

run_toy_server(name=args.name)
