#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# s1 (primary) does NOT have codeActionProvider
# s2 (secondary) has codeActionProvider
# s3 (tertiary) has codeActionProvider
# Expected: codeAction request goes to s2 and s3, responses aggregated
./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --has-code-actions \
         -- python ./server.py --name s3 --has-code-actions \
> "$FIFO"
