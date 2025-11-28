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

# Run test with 2 servers
"$CLIENT" < "$FIFO" | "$LSPYLEX" -- python "$SERVER" --name s1 --publish-diagnostics -- python "$SERVER" --name s2 --publish-diagnostics > "$FIFO"
