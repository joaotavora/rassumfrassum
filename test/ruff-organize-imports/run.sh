#!/bin/bash
set -e
cd $(dirname "$0")

if ! command -v ruff >/dev/null 2>&1; then
    echo "ruff not found, skipping test" >&2
    exit 77
fi

../yoyo.sh ./client.py --rass-- -- ruff server
