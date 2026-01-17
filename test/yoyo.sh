#!/bin/bash
# Cross-platform bidirectional pipe for rassumfrassum tests.
# On Unix: uses mkfifo trick for clean stdio piping
# On Windows: falls back to yoyo.py (Python-based workaround)
#
# Usage: yoyo.sh <client_script> [client_args...] --rass-- [rass_args...]
#
# Example:
#   yoyo.sh ./client.py --rass-- -- python ./server.py --name s1 -- python ./server.py --name s2
#   yoyo.sh ./client.py --rass-- python
#   yoyo.sh ./client.py --some-arg --rass-- --logic-class custom.Logic -- python ./server.py

set -e
set -o pipefail

# Detect Windows (Git Bash, MSYS2, Cygwin, WSL)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
    # Windows: use yoyo.py
    export WINDOWS_KLUDGE=1
    SCRIPT_DIR=$(dirname "$0")
    exec python "$SCRIPT_DIR/yoyo.py" "$@"
else
    # Unix: use mkfifo trick
    if [ $# -lt 3 ]; then
        echo "Usage: $0 <client_script> [client_args...] --rass-- [rass_args...]" >&2
        exit 1
    fi

    CLIENT_SCRIPT="$1"
    shift

    # Collect client args until we hit --rass--
    CLIENT_ARGS=()
    while [ $# -gt 0 ] && [ "$1" != "--rass--" ]; do
        CLIENT_ARGS+=("$1")
        shift
    done

    # Skip the --rass-- separator
    if [ "$1" != "--rass--" ]; then
        echo "Error: Missing --rass-- separator" >&2
        exit 1
    fi
    shift

    # Remaining args are for rassumfrassum
    RASS_ARGS=("$@")

    # Set up PYTHONPATH
    REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
    export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH}"

    # Create FIFO
    FIFO=$(mktemp -u)
    mkfifo "$FIFO"
    trap "rm -f '$FIFO'" EXIT INT TERM

    # Run client < fifo | rassumfrassum <args> > fifo
    "$CLIENT_SCRIPT" "${CLIENT_ARGS[@]}" < "$FIFO" | python -m rassumfrassum "${RASS_ARGS[@]}" > "$FIFO"
fi
