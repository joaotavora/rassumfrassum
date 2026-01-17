#!/usr/bin/env python
"""
rassumfrassum - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import argparse
import asyncio
import sys

from . import __version__
from .preset import load_preset
from .rassum import run_multiplexer
from .util import (
    log,
    set_log_level,
    set_max_log_length,
    LOG_SILENT,
    LOG_WARN,
    LOG_INFO,
    LOG_DEBUG,
    LOG_EVENT,
    LOG_TRACE,
)


def parse_server_commands(argv: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Split argv on '--' separators.
    Returns (rass_args, [server_command1, server_command2, ...])
    """
    if "--" not in argv:
        return argv, []

    # Find all '--' separator indices
    separator_indices = [i for i, arg in enumerate(argv) if arg == "--"]

    # Everything before first '--' is rass options
    rass_args = argv[: separator_indices[0]]

    # Split server commands
    server_commands: list[list[str]] = []
    for i, sep_idx in enumerate(separator_indices):
        # Find start and end of this server command
        start = sep_idx + 1
        end = (
            separator_indices[i + 1]
            if i + 1 < len(separator_indices)
            else len(argv)
        )

        server_cmd: list[str] = argv[start:end]
        if server_cmd:  # Only add non-empty commands
            server_commands.append(server_cmd)

    return rass_args, server_commands


def main(argv=None) -> None:
    """
    Parse arguments and start the multiplexer.
    """
    if argv is None:
        import sys
        argv = sys.argv[1:]

    # Parse multiple '--' separators for multiple servers
    rass_args, server_commands = parse_server_commands(argv)

    # Parse rass options with argparse
    parser = argparse.ArgumentParser(
        prog='rass',
        usage="%(prog)s [-h] [%(prog)s options] [preset] [-- server1 [args...] [-- server2 ...]]",
        add_help=True,
    )

    parser.add_argument(
        '--version', action='version', version=f'%(prog)s {__version__}'
    )
    parser.add_argument(
        'preset', nargs='?', help='Preset name or path to preset file'
    )
    parser.add_argument(
        '--quiet-server', action='store_true', help='Suppress server\'s stderr.'
    )
    parser.add_argument(
        '--delay-ms',
        type=int,
        default=0,
        metavar='N',
        help='Delay all messages from rass by N ms.',
    )
    parser.add_argument(
        '--drop-tardy',
        action='store_true',
        help='Drop tardy messages instead of re-sending aggregations.',
    )
    parser.add_argument(
        '--stream-diagnostics',
        action=argparse.BooleanOptionalAction,
        default=False,
        help='Stream diagnostics as they arrive (default: enabled).',
    )
    parser.add_argument(
        '--logic-class',
        type=str,
        default='LspLogic',
        metavar='CLASS',
        help='Logic class to use for routing (default: LspLogic).',
    )
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['silent', 'warn', 'info', 'event', 'debug', 'trace'],
        default='event',
        help='Set logging verbosity (default: event).',
    )
    parser.add_argument(
        '--max-log-length',
        type=int,
        default=4000,
        metavar='N',
        help='Maximum log message length in bytes; 0 for unlimited (default: 4000).',
    )
    opts = parser.parse_args(rass_args)

    # Set log level based on argument
    log_level_map = {
        'silent': LOG_SILENT,
        'warn': LOG_WARN,
        'info': LOG_INFO,
        'event': LOG_EVENT,
        'debug': LOG_DEBUG,
        'trace': LOG_TRACE,
    }
    set_log_level(log_level_map[opts.log_level])
    set_max_log_length(opts.max_log_length)

    # Load preset if specified
    preset_logic_class = None
    if opts.preset:
        preset_servers, preset_logic_class = load_preset(opts.preset)
        server_commands = preset_servers + server_commands

        # Use preset logic class if --logic-class wasn't explicitly set
        if preset_logic_class and '--logic-class' not in rass_args:
            opts.logic_class = (
                f"{preset_logic_class.__module__}.{preset_logic_class.__name__}"
            )

    if not server_commands:
        log(
            "Usage: rass [OPTIONS] -- <primary-server> [args] [-- <secondary-server> [args]]..."
        )
        sys.exit(1)

    # Validate
    assert opts.delay_ms >= 0, "--delay-ms must be non-negative"

    try:
        asyncio.run(run_multiplexer(server_commands, opts))
    except KeyboardInterrupt:
        log("\nShutting down...")
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
