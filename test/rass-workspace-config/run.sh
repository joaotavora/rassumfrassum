#!/bin/bash
set -e
cd $(dirname "$0")

../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2
