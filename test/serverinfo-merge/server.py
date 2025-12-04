#!/usr/bin/env python3
"""Server for serverinfo-merge test"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from dada.tete import run_server
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--version', default='1.0.0')
args = parser.parse_args()

run_server(name=args.name, version=args.version)
