#!/usr/bin/env python3
"""Server for server-crash test"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from dada.tete import run_server, log
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--crash-after-init', action='store_true')
args = parser.parse_args()

run_server(
    name=args.name,
    on_initialized=lambda: (log(args.name, "Crashing as requested"), sys.exit(42)) if args.crash_after_init else None
)
