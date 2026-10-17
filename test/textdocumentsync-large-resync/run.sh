#!/bin/bash
set -e
cd $(dirname "$0")

# s1 is incremental, so a range-less change from the client is diffed
# into ranged changes for it (#58)
../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 --text-document-sync 2
