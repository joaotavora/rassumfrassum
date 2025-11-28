#!/bin/bash
set -e
set -o pipefail

# Get script's directory and derive paths relative to it
SCRIPT_DIR=$(dirname "$0")
LSPYLEX="$SCRIPT_DIR/../../lspylex.py"
CLIENT="$SCRIPT_DIR/client.py"
SERVER="$SCRIPT_DIR/../server.py"

# Create temporary fifo
FIFO=$(mktemp -u)
mkfifo "$FIFO"

# Cleanup on exit
trap "rm -f '$FIFO'" EXIT INT TERM

# Run test with 2 servers
# s1: immediate diagnostics
# s2: 500ms delay (well within 1000ms timeout)
"$CLIENT" < "$FIFO" | "$LSPYLEX" -- python "$SERVER" --name s1 --publish-diagnostics -- python "$SERVER" --name s2 --publish-diagnostics --delay-diagnostics 500 > "$FIFO"
