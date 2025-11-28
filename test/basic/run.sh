#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

run_test -- python "$SERVER" --name s1 --publish-diagnostics \
         -- python "$SERVER" --name s2 --publish-diagnostics
