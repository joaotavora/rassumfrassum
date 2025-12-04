#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

# s1: 1500ms delay (exceeds 1000ms timeout, diagnostics discarded)
# s2: immediate diagnostics

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | ./../../dada.py --drop-tardy \
         -- python ./server.py --name s1 --delay-diagnostics 1500 \
         -- python ./server.py --name s2 \
> "$FIFO"
