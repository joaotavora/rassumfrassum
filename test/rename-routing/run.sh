#!/bin/bash
set -e
cd $(dirname "$0")

# s1 (primary) does NOT have renameProvider
# s2 (secondary) has renameProvider
# s3 (tertiary) has renameProvider
# Expected: rename request goes ONLY to s2 (first with capability), NOT to s3

../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --has-rename \
    -- python ./server.py --name s3 --has-rename
