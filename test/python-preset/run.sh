#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

# Check if required LSP servers are available
if ! command -v ty >/dev/null 2>&1 || \
   ! command -v ruff >/dev/null 2>&1; then
    echo "Required LSP servers not found, skipping test" >&2
    exit 77
fi

../yoyo.sh ./client.py --rass-- python
