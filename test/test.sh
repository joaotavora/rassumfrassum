#!/bin/sh
set -e

# Get script's directory and derive paths relative to it
SCRIPT_DIR=$(dirname "$0")
LSPYLEX="$SCRIPT_DIR/../lspylex.py"
CLIENT="$SCRIPT_DIR/client.py"
SERVER="$SCRIPT_DIR/server.py"

# Create temporary fifo
FIFO=$(mktemp -u)
mkfifo "$FIFO"

# Cleanup on exit
trap "rm -f '$FIFO'" EXIT INT TERM

# Run test
"$CLIENT" < "$FIFO" | "$LSPYLEX" -- python "$SERVER" --name s1 --publish-diagnostics > "$FIFO"
