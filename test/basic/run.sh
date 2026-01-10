#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | python3 -m rassumfrassum  \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 \
> "$FIFO"
