#!/bin/bash
set -e
cd $(dirname "$0")

# rass spawns the servers directly (no shell), which can't run the
# .cmd shims npm creates on Windows
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
    echo "Windows, skipping test" >&2
    exit 77
fi

# Needed to npm-install the fixture and by the servers themselves
if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found, skipping test" >&2
    exit 77
fi

# Install fixture dependencies: vue-language-server v3,
# typescript-language-server, tailwindcss-language-server, etc.
(cd fixture && npm install --silent >/dev/null 2>&1) || {
    echo "npm install failed in fixture, skipping test" >&2
    exit 77
}

# Use the fixture-pinned servers regardless of what's in PATH
export PATH="$PWD/fixture/node_modules/.bin:$PATH"

../yoyo.sh ./client.py --rass-- vuetail
