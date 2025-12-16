#!/bin/bash
set -e
cd $(dirname "$0")

# s1 does NOT have definitionProvider, won't receive definition requests
# s2 has definitionProvider, returns random locations as LocationLink (list)
# s3 has definitionProvider, returns random locations as Location (dict)
# s4 has definitionProvider, returns const locations as LocationLink (list)
# s5 has definitionProvider, returns const locations as Location (dict)
# s4 and s5 return identical locations, so one gets deduplicated
# Expected: request goes to s2, s3, s4, s5; result has 3 unique definitions
../yoyo.sh ./client.py --rass-- \
    -- python ./server.py --name s1 \
    -- python ./server.py --name s2 --has-definition --as-link \
    -- python ./server.py --name s3 --has-definition --in-dict \
    -- python ./server.py --name s4 --has-definition --as-link --const \
    -- python ./server.py --name s5 --has-definition --in-dict --const
