#!/bin/bash
set -e
cd $(dirname "$0")

# s1 is incremental, s2 is full: both depend on rass applying every
# change in a didChange batch to its copy of the document (#59)
../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 --text-document-sync 2 \
    -- python ./server.py --name s2 --text-document-sync 1
