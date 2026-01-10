#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# S1 (primary) responds immediately
# S2 (secondary) delays initialize response by 3000ms (exceeds 2500 default timeout)
./client.py < "$FIFO" | python3 -m rassumfrassum --drop-tardy \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --initialize-delay 3000 \
> "$FIFO"
