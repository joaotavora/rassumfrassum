#!/bin/bash
set -e
cd $(dirname "$0")

# s1: 1500ms delay (exceeds 1000ms timeout, diagnostics discarded)
# s2: immediate diagnostics

../yoyo.sh ./client.py --rass-- --drop-tardy \
    -- python ./server.py --name s1 --delay-diagnostics 1500 \
    -- python ./server.py --name s2
