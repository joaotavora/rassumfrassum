#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# s1 (primary) does NOT have definitionProvider
# s2 (secondary) has definitionProvider
# s3 (tertiary) has definitionProvider
# Expected: definition request goes to s2 and s3, responses aggregated
./client.py < "$FIFO" | ./../../rass \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --has-definition \
         -- python ./server.py --name s3 --has-definition --as-dict \
> "$FIFO"
