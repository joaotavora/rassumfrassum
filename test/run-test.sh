#!/bin/bash
# Common test runner script
# Usage from a test's run.sh:
#   source ../run-test.sh
#   run_test -- <server1 args> -- <server2 args>

set -e
set -o pipefail

# Set up paths when sourced
_TEST_DIR=$(dirname "${BASH_SOURCE[1]}")
LSPYLEX="$_TEST_DIR/../../lspylex.py"
CLIENT="$_TEST_DIR/client.py"
SERVER="$_TEST_DIR/../server.py"

run_test() {
    # Create temporary fifo
    local FIFO=$(mktemp -u)
    mkfifo "$FIFO"

    # Cleanup on exit
    trap "rm -f '$FIFO'" EXIT INT TERM

    # Run test with provided server arguments
    "$CLIENT" < "$FIFO" | "$LSPYLEX" "$@" > "$FIFO"
}
