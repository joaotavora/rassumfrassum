#!/bin/bash
set -e
cd $(dirname "$0")

# Check if required LSP servers are available
if ! command -v biome >/dev/null 2>&1; then
    echo "biome not found, skipping test" >&2
    exit 77
fi

if ! command -v typescript-language-server >/dev/null 2>&1; then
    echo "typescript-language-server not found, skipping test" >&2
    exit 77
fi

../yoyo.sh ./client.py --rass-- tsbiome
