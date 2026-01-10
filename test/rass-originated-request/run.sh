#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

# Add both src and current test directory to PYTHONPATH
# so rass can import both rassumfrassum and profile modules
export PYTHONPATH="$(cd ../.. && pwd)/src:$(pwd):${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | python3 -m rassumfrassum --logic-class custom_logic.CustomLogic \
         -- python ./server.py \
> "$FIFO"
