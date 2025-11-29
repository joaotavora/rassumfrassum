#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

# Both servers send diagnostics with version numbers
# s1: immediate on didOpen and didChange
# s2: immediate on didOpen and didChange

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 \
> "$FIFO"
