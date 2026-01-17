#!/bin/bash
set -e
cd $(dirname "$0")

# s1: immediate diagnostics
# s2: 500ms delay (well within 1000ms timeout)

../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --delay-diagnostics 500
