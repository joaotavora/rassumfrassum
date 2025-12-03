#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

timeout 3 bash -c "./client.py < '$FIFO' | ./../../dada.py \
         -- python ./server.py --name s1 --send-request-after-init \
         -- python ./server.py --name s2 --send-request-after-init \
> '$FIFO'"
