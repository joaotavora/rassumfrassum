#!/bin/bash
cd $(dirname "$0")

# Server s2 will crash after initialization
# We expect rass to exit with error code 1

set +e
../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --crash-after-init
EXIT_CODE=$?
set -e

# Check if rass exited with error (expected behavior)
if [ $EXIT_CODE -eq 1 ]; then
    exit 0  # Test passed - rass exited with error as expected
else
    echo "Test failed: Expected exit code 1, got $EXIT_CODE"
    exit 1
fi
