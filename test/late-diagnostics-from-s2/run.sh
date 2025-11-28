#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

# s1: immediate diagnostics
# s2: 500ms delay (well within 1000ms timeout)
run_test -- python "$SERVER" --name s1 --publish-diagnostics \
         -- python "$SERVER" --name s2 --publish-diagnostics --delay-diagnostics 500
