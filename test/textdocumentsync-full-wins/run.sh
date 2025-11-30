#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# s1 (primary) has textDocumentSync=2 (Incremental)
# s2 (secondary) has textDocumentSync=1 (Full)
# The bug: merged result will be 2, but should be 1
./client.py < "$FIFO" | ./../../dada.py \
         -- python ./server.py --name s1 --text-document-sync 2 \
         -- python ./server.py --name s2 --text-document-sync 1 \
> "$FIFO"
