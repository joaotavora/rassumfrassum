#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH:-}"

# Check if required servers are available
if ! command -v basedpyright-langserver &> /dev/null || \
   ! command -v ruff &> /dev/null || \
   ! command -v codebook-lsp &> /dev/null; then
    echo "Required LSP servers not found, skipping test" >&2
    exit 77
fi

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

chmod +x client.py
./client.py < "$FIFO" | ./../../rass \
    -- basedpyright-langserver --stdio \
    -- ruff server \
    -- codebook-lsp serve \
> "$FIFO"
