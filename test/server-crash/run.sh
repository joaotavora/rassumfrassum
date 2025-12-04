#!/bin/bash
set -o pipefail
cd $(dirname "$0")

# Server s2 will crash after initialization
# We expect dada to exit with error code 1

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

set +e
./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --crash-after-init \
> "$FIFO"
EXIT_CODE=$?
set -e

# Check if dada exited with error (expected behavior)
if [ $EXIT_CODE -eq 1 ]; then
    exit 0  # Test passed - dada exited with error as expected
else
    echo "Test failed: Expected exit code 1, got $EXIT_CODE"
    exit 1
fi
