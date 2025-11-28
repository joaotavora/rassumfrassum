#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

# s1: 1500ms delay (exceeds 1000ms timeout, diagnostics discarded)
# s2: immediate diagnostics
run_test -- python "$SERVER" --name s1 --publish-diagnostics --delay-diagnostics 1500 \
         -- python "$SERVER" --name s2 --publish-diagnostics
