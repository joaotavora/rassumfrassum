#!/usr/bin/env python3
"""Server for serverinfo-merge test"""


from rassumfrassum.tete import run_server
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--version', default='1.0.0')
args = parser.parse_args()

run_server(name=args.name, version=args.version)
