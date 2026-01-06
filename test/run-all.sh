#!/bin/bash
# Run all tests in parallel and report results

# Colorize helper (set to false to disable colors)
USE_COLOR=true
colorize() {
    if [ "$USE_COLOR" = true ]; then
        case "$2" in
            green) echo -e "\033[32m$1\033[0m" ;;
            yellow) echo -e "\033[33m$1\033[0m" ;;
            red) echo -e "\033[31m$1\033[0m" ;;
            *) echo "$1" ;;
        esac
    else
        echo "$1"
    fi
}
export -f colorize
export USE_COLOR

# Find all test directories (those containing run.sh)
TEST_DIRS=$(find test -mindepth 2 -maxdepth 2 -name "run.sh" -type f -executable | sed 's|/run.sh$||' | sort)

if [ -z "$TEST_DIRS" ]; then
    echo "No tests found"
    exit 1
fi

# Create temp dir for outputs
TMPDIR=$(mktemp -d)
trap "rm -rf '$TMPDIR'" EXIT

# Launch all tests in parallel
PIDS=()
for d in $TEST_DIRS; do
    n=$(basename "$d")
    echo "Start: $n"

    # Run in background, capturing output and timing
    (
        start=$(date +%s%N)
        output=$(timeout 10 "$d/run.sh" 2>&1)
        rc=$?
        end=$(date +%s%N)
        elapsed_ns=$((end - start))
        elapsed=$(awk "BEGIN {printf \"%.3f\", $elapsed_ns / 1000000000}")

        # Determine status with colors
        case $rc in
            0) status=$(colorize "PASSED" green) ;;
            77) status=$(colorize "SKIPPED" yellow) ;;
            124) status=$(colorize "TIMED OUT" red) ;;
            *) status=$(colorize "FAILED" red) ;;
        esac

        # Save results
        echo "$rc" > "$TMPDIR/$n.rc"
        echo "$elapsed" > "$TMPDIR/$n.time"
        echo "$output" > "$TMPDIR/$n.output"

        # Print completion message
        printf "%s: %s (%ss)\n" "$status" "$n" "$elapsed"
    ) &
    PIDS+=($!)
done

# Wait for all to finish
for pid in "${PIDS[@]}"; do
    wait $pid
done

echo

# Collect results
PASSED=0
FAILED=0
TIMEDOUT=0
SKIPPED=0
FAILED_TESTS=()
TIMEDOUT_TESTS=()
SKIPPED_TESTS=()

for d in $TEST_DIRS; do
    n=$(basename "$d")
    rc=$(cat "$TMPDIR/$n.rc")

    case $rc in
        0)
            PASSED=$((PASSED + 1))
            ;;
        77)
            SKIPPED=$((SKIPPED + 1))
            SKIPPED_TESTS+=("$n")
            ;;
        124)
            TIMEDOUT=$((TIMEDOUT + 1))
            TIMEDOUT_TESTS+=("$n")
            ;;
        *)
            FAILED=$((FAILED + 1))
            FAILED_TESTS+=("$n")
            ;;
    esac
done

# Print outputs for non-passing tests
if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    for test in "${FAILED_TESTS[@]}"; do
        echo "--- Output from $test ---"
        cat "$TMPDIR/$test.output"
        echo "--- End of $test ---"
        echo
    done
fi

if [ ${#TIMEDOUT_TESTS[@]} -gt 0 ]; then
    for test in "${TIMEDOUT_TESTS[@]}"; do
        echo "--- Output from $test ---"
        cat "$TMPDIR/$test.output"
        echo "--- End of $test ---"
        echo
    done
fi

if [ ${#SKIPPED_TESTS[@]} -gt 0 ]; then
    for test in "${SKIPPED_TESTS[@]}"; do
        echo "--- Output from $test ---"
        cat "$TMPDIR/$test.output"
        echo "--- End of $test ---"
        echo
    done
fi

echo "$PASSED passed, $FAILED failed, $SKIPPED skipped, $TIMEDOUT timed out"

if [ $FAILED -gt 0 ]; then
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
fi

if [ $TIMEDOUT -gt 0 ]; then
    echo "Timed-out tests:"
    for test in "${TIMEDOUT_TESTS[@]}"; do
        echo "  - $test"
    done
fi

if [ $SKIPPED -gt 0 ]; then
    echo "Skipped tests:"
    for test in "${SKIPPED_TESTS[@]}"; do
        echo "  - $test"
    done
fi

rc=0
if [ $FAILED -gt 0 ] || [ $TIMEDOUT -gt 0 ]; then
    rc=1
fi
exit $rc
