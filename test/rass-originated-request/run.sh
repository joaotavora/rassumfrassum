#!/bin/bash
set -e
cd $(dirname "$0")

# Add current test directory to PYTHONPATH
# so rass can import the custom_logic module
export PYTHONPATH="$(pwd):${PYTHONPATH}"

../yoyo.sh ./client.py --rass-- --logic-class custom_logic.CustomLogic \
    -- python ./server.py
