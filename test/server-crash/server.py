#!/usr/bin/env python
"""Server for server-crash test"""

import argparse
import sys

from rassumfrassum.test2 import run_toy_server, log

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--crash-after-init', action='store_true')
args = parser.parse_args()

def handle_initialized(params):
    if args.crash_after_init:
        log(args.name, "Crashing as requested")
        sys.exit(42)

run_toy_server(
    name=args.name,
    notification_handlers={'initialized': handle_initialized}
)
