#!/bin/bash
# Run all tests and report results

# Find all test directories (those containing run.sh)
TEST_DIRS=$(find test -mindepth 2 -maxdepth 2 -name "run.sh" -type f -executable | sed 's|/run.sh$||' | sort)

if [ -z "$TEST_DIRS" ]; then
    echo "No tests found"
    exit 1
fi

PASSED=0
FAILED=0
TIMEDOUT=0
SKIPPED=0
FAILED_TESTS=()
TIMEDOUT_TESTS=()
SKIPPED_TESTS=()

for d in $TEST_DIRS; do
    n=$(basename "$d")
    printf "%-35s " "$n"

    output=$(timeout 10 "$d/run.sh" 2>&1)
    rc=$?

    case $rc in
        0)
            echo "PASSED"
            PASSED=$((PASSED + 1))
            ;;
        77)
            echo "SKIPPED"
            SKIPPED=$((SKIPPED + 1))
            SKIPPED_TESTS+=("$n")
            ;;
        124)
            echo "TIMED OUT"
            TIMEDOUT=$((TIMEDOUT + 1))
            TIMEDOUT_TESTS+=("$n")
            ;;
        *)
            echo "FAILED"
            FAILED=$((FAILED + 1))
            FAILED_TESTS+=("$n")
            ;;
    esac

    if [ "$rc" -ne 0 ]; then
        echo "--- Output from $n ---"
        echo "$output"
        echo "--- End of $n ---"
        echo
    fi
done

echo
echo "$PASSED passed, $FAILED failed, $SKIPPED skipped, $TIMEDOUT timed out"

rc=0
if [ $FAILED -gt 0 ]; then
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    rc=1
fi
if [ $TIMEDOUT -gt 0 ]; then
    echo "Timed-out tests:"
    for test in "${TIMEDOUT_TESTS[@]}"; do
        echo "  - $test"
    done
    rc=1
fi
if [ $SKIPPED -gt 0 ]; then
    echo "Skipped tests:"
    for test in "${SKIPPED_TESTS[@]}"; do
        echo "  - $test"
    done
fi
exit $rc
