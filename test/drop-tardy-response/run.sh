#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# S1 (primary) responds immediately
# S2 (secondary) delays initialize response by 2500ms (exceeds 2000ms timeout)
./client.py < "$FIFO" | ./../../dada --drop-tardy \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --initialize-delay 2500 \
> "$FIFO"
