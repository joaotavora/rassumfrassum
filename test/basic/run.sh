#!/bin/bash
set -e
cd $(dirname "$0")

# Use relay.py for cross-platform compatibility
python ../relay.py ./client.py \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2
