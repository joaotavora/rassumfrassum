#!/bin/bash
set -e
cd $(dirname "$0")

# s1 is incremental, s2 is full: a range-less change from the client is
# diffed into ranged changes for s1 (#57)
../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 --text-document-sync 2 \
    -- python ./server.py --name s2 --text-document-sync 1
