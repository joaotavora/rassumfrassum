#!/bin/bash
set -e
cd $(dirname "$0")

# Check if required LSP servers are available
if ! command -v basedpyright-langserver >/dev/null 2>&1 || \
   ! command -v ruff >/dev/null 2>&1 || \
   ! command -v codebook-lsp >/dev/null 2>&1; then
    echo "Required LSP servers not found, skipping test" >&2
    exit 77
fi

../yoyo.sh ./client.py --rass-- \
    -- basedpyright-langserver --stdio \
    -- ruff server \
    -- codebook-lsp serve
