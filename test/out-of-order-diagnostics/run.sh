#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 --send-stale-v1 \
         -- python ./server.py --name s2 \
> "$FIFO"
