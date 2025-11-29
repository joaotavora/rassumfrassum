#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 --version 1.0.0 \
         -- python ./server.py --name s2 --version 2.0.0 \
> "$FIFO"
