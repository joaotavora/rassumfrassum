#!/usr/bin/env python3
"""
Test client that expects rass to exit when server crashes.
"""


from rassumfrassum.tete import do_initialize, do_initialized, log
from rassumfrassum.jaja import read_message_sync

def main():
    """Send initialize and initialized, then expect connection to die."""

    do_initialize()
    do_initialized()

    # After initialized, one of the servers will crash
    # We expect rass to exit, so we should get EOF
    msg = read_message_sync()
    if msg is not None:
        log("client", f"ERROR: Expected EOF but got message: {msg}")
        sys.exit(1)

    log("client", "Got EOF as expected - rass exited after server crash")

if __name__ == '__main__':
    main()
