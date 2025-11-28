#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

run_test -- python "$SERVER" --name s1 --send-request-after-init \
         -- python "$SERVER" --name s2 --send-request-after-init
