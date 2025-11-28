#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

# Server s2 will crash after initialization
# We expect dada to exit with error code 1
# Disable exit-on-error temporarily to check exit code
set +e
run_test -- python "$SERVER" --name s1 \
         -- python "$SERVER" --name s2 --crash-after-init
EXIT_CODE=$?
set -e

# Check if dada exited with error (expected behavior)
if [ $EXIT_CODE -eq 1 ]; then
    exit 0  # Test passed - dada exited with error as expected
else
    echo "Test failed: Expected exit code 1, got $EXIT_CODE"
    exit 1
fi
