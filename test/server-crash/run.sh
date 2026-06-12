#!/bin/bash
cd $(dirname "$0")

# Server s2 will crash after initialization
# We expect rass to exit with error code 1

# On Windows rass can't make its fatal exit while the stdin-reading
# executor thread is blocked (see WINDOWS_KLUDGE in test2.py), so this
# scenario isn't testable there
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
    echo "Windows, skipping test" >&2
    exit 77
fi

# The client waits for EOF from rass, which macOS's kqueue never
# reports on FIFOs, so cap its wait.  rass's exit code decides the
# test and yoyo.sh's pipefail propagates the pipeline's rightmost
# (i.e. rass's) non-zero exit status.
TO=$(command -v timeout || command -v gtimeout || true)

set +e
../yoyo.sh ${TO:+"$TO" 5} ./client.py --rass-- \
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
