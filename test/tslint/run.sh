#!/bin/bash
set -e
cd $(dirname "$0")

# Check if required LSP servers are available
if ! command -v eslint-language-server >/dev/null 2>&1; then
    echo "eslint-language-server not found, skipping test" >&2
    exit 77
fi

if ! command -v typescript-language-server >/dev/null 2>&1; then
    echo "typescript-language-server not found, skipping test" >&2
    exit 77
fi

# Install npm dependencies in fixture
(cd fixture && npm install --silent >/dev/null 2>&1) || {
    echo "npm install failed in fixture, skipping test" >&2
    exit 77
}

../yoyo.sh ./client.py --rass-- tslint
