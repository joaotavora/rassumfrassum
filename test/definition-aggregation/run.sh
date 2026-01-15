#!/bin/bash
set -e
set -o pipefail
cd $(dirname "$0")

export PYTHONPATH="$(cd ../.. && pwd)/src:${PYTHONPATH}"

FIFO=$(mktemp -u)
mkfifo "$FIFO"
trap "rm -f '$FIFO'" EXIT INT TERM

# s1 does NOT have definitionProvider
# s2 has definitionProvider, returns random locations as LocationLink (list of)
# s3 has definitionProvider, returns random locations as Location (single, dict)
# s4 has definitionProvider, returns const locations as LocationLink (list of)
# s4 has definitionProvider, returns const locations as Location (single, dict)
# Expected: definition request goes to s2 and s3, responses aggregated
./client.py < "$FIFO" | python3 -m rassumfrassum \
         -- python ./server.py --name s1 \
         -- python ./server.py --name s2 --has-definition --as-link \
         -- python ./server.py --name s3 --has-definition --in-dict \
         -- python ./server.py --name s4 --has-definition --as-link --const \
         -- python ./server.py --name s5 --has-definition --in-dict --const \
> "$FIFO"
