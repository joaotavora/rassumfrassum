#!/bin/bash
set -e
cd $(dirname "$0")

# s1 (primary) does NOT have codeActionProvider
# s2 (secondary) has codeActionProvider
# s3 (tertiary) has codeActionProvider
# Expected: codeAction request goes to s2 and s3, responses aggregated

../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --has-code-actions \
    -- python ./server.py --name s3 --has-code-actions
