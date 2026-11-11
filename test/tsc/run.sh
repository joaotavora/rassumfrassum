#!/bin/bash
set -e
cd $(dirname "$0")

# rass can't directly spawn npm's .cmd shims on Windows.
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
    echo "Windows, skipping test" >&2
    exit 77
fi

if ! command -v tsc >/dev/null 2>&1; then
    echo "tsc not found, skipping test" >&2
    exit 77
fi

# Older tsc versions don't implement LSP.
case "$(tsc --version)" in
    "Version "[0-6].*)
        echo "TypeScript 7 or newer required, skipping test" >&2
        exit 77
        ;;
esac

python ../yoyo.py ./client.py --rass-- --stream-diagnostics \
    -- tsc --lsp --stdio
