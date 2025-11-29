#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

# s1: immediate diagnostics
# s2: 500ms delay (well within 1000ms timeout)

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --delay-diagnostics 500 \
> "$FIFO"
