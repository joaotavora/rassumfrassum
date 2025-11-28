#!/bin/bash
# Run all tests and report results

set -e
set -o pipefail

# Find all test directories (those containing run.sh)
TEST_DIRS=$(find test -mindepth 2 -maxdepth 2 -name "run.sh" -type f -executable | sed 's|/run.sh$||' | sort)

if [ -z "$TEST_DIRS" ]; then
    echo "No tests found"
    exit 1
fi

PASSED=0
FAILED=0
FAILED_TESTS=()

for test_dir in $TEST_DIRS; do
    test_name=$(basename "$test_dir")
    printf "%-35s " "$test_name"

    # Run test and capture output
    if output=$(timeout 15 "$test_dir/run.sh" 2>&1); then
        echo "PASSED"
        PASSED=$((PASSED + 1))
    else
        echo "FAILED"
        FAILED=$((FAILED + 1))
        FAILED_TESTS+=("$test_name")
        # Show the output for failed tests
        echo "--- Output from $test_name ---"
        echo "$output"
        echo "--- End of $test_name ---"
        echo
    fi
done

echo
echo "========================================="
echo "Results: $PASSED passed, $FAILED failed"
echo "========================================="

if [ $FAILED -gt 0 ]; then
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    exit 1
fi
