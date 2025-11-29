#!/bin/bash
source "$(dirname "$0")/../run-test.sh"

run_test -- python "$SERVER" --name s1 --version 1.0.0 \
         -- python "$SERVER" --name s2 --version 2.0.0
