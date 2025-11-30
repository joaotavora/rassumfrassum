#!/usr/bin/env python3
"""
Test client that expects dada to exit when server crashes.
"""

import sys
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(test_dir))

from client_common import do_initialize, do_initialized, log
from jaja import read_message_sync

def main():
    """Send initialize and initialized, then expect connection to die."""

    do_initialize()
    do_initialized()

    # After initialized, one of the servers will crash
    # We expect dada to exit, so we should get EOF
    msg = read_message_sync()
    if msg is not None:
        log("client", f"ERROR: Expected EOF but got message: {msg}")
        sys.exit(1)

    log("client", "Got EOF as expected - dada exited after server crash")

if __name__ == '__main__':
    main()
