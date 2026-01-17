#!/bin/bash
set -e
cd $(dirname "$0")

# s1 (primary) has textDocumentSync=2 (Incremental)
# s2 (secondary) has textDocumentSync=1 (Full)
# The bug: merged result will be 2, but should be 1

../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 --text-document-sync 2 \
    -- python ./server.py --name s2 --text-document-sync 1
