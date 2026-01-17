#!/bin/bash
set -e
cd $(dirname "$0")

# S1 (primary) responds immediately
# S2 (secondary) delays initialize response by 3000ms (exceeds 2500 default timeout)

../yoyo.sh ./client.py --rass-- --drop-tardy \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --initialize-delay 3000
