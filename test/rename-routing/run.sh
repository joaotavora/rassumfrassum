#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# s1 (primary) does NOT have renameProvider
# s2 (secondary) has renameProvider
# s3 (tertiary) has renameProvider
# Expected: rename request goes ONLY to s2 (first with capability), NOT to s3
timeout 3 bash -c "./client.py < '$FIFO' | ./../../dada.py \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --has-rename \
         -- python ./server.py --name s3 --has-rename \
> '$FIFO'"
