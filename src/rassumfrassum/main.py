#!/usr/bin/env python
"""
rassumfrassum - A simple LSP multiplexer that forwards JSONRPC messages.
"""

import argparse
import asyncio
import json
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


def parse_server_commands(
    argv: list[str],
) -> tuple[list[str], list[list[str]], list[list[str]]]:
    """
    Split argv on '--' and '---' separators.
    Returns (rass_args, server_commands, relay_server_commands)

    '--' separates regular server commands.
    '---' separates relay server commands.
    """
    if "--" not in argv and "---" not in argv:
        return argv, [], []

    # Find first separator (either -- or ---)
    first_sep = None
    for i, arg in enumerate(argv):
        if arg in ("--", "---"):
            first_sep = i
            break

    if first_sep is None:
        return argv, [], []

    # Everything before first separator is rass options
    rass_args = argv[:first_sep]

    # Walk through remaining args, splitting on separators
    server_commands: list[list[str]] = []
    relay_server_commands: list[list[str]] = []
    current: list[str] = []
    is_relay = False

    for arg in argv[first_sep:]:
        if arg in ("--", "---"):
            if current:
                (relay_server_commands if is_relay else server_commands).append(current)
                current = []
            is_relay = (arg == "---")
        else:
            current.append(arg)

    if current:
        (relay_server_commands if is_relay else server_commands).append(current)

    return rass_args, server_commands, relay_server_commands


def main(argv=None) -> None:
    """
    Parse arguments and start the multiplexer.
    """
    if argv is None:
        import sys
        argv = sys.argv[1:]

    # Parse multiple '--' / '---' separators for servers and relay servers
    rass_args, server_commands, relay_server_commands = parse_server_commands(argv)

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
    parser.add_argument(
        '--relay-match',
        type=str,
        metavar='METHOD',
        help='Notification method to intercept from source servers for relay.',
    )
    parser.add_argument(
        '--relay-send',
        type=str,
        metavar='METHOD',
        help='Request method to send to relay server.',
    )
    parser.add_argument(
        '--relay-respond',
        type=str,
        metavar='METHOD',
        help='Notification method to send back to source server.',
    )
    parser.add_argument(
        '--relay-command',
        type=str,
        metavar='CMD',
        help='Command name for workspace/executeCommand relay.',
    )
    parser.add_argument(
        '--relay-forward',
        type=str,
        metavar='METHODS',
        help='Comma-separated notification methods to forward to relay servers (e.g. textDocument/didOpen,textDocument/didChange,textDocument/didClose).',
    )
    parser.add_argument(
        '--relay-forward-requests',
        type=str,
        metavar='METHODS',
        help='Comma-separated request methods to also route to relay servers (e.g. textDocument/definition).',
    )
    parser.add_argument(
        '--init-options',
        type=str,
        metavar='JSON',
        help='JSON object to merge into primary server initializationOptions.',
    )
    parser.add_argument(
        '--relay-init-options',
        type=str,
        metavar='JSON',
        help='JSON object to merge into relay server initializationOptions.',
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

    # Parse JSON CLI options
    cli_init_options = json.loads(opts.init_options) if opts.init_options else None
    cli_relay_init_options = json.loads(opts.relay_init_options) if opts.relay_init_options else None

    # Load preset if specified
    preset_logic_class = None
    relay_spec = None
    preset_init_options = None
    if opts.preset:
        preset_servers, preset_logic_class, preset_relay_servers, preset_relay_spec, preset_init_options = load_preset(opts.preset)
        server_commands = preset_servers + server_commands
        relay_server_commands = preset_relay_servers + relay_server_commands
        relay_spec = preset_relay_spec

        # Use preset logic class if --logic-class wasn't explicitly set
        if preset_logic_class and '--logic-class' not in rass_args:
            opts.logic_class = (
                f"{preset_logic_class.__module__}.{preset_logic_class.__name__}"
            )

    # Merge init_options: preset as base, CLI overrides on top
    if preset_init_options or cli_init_options:
        opts.init_options = {**(preset_init_options or {}), **(cli_init_options or {})}
    else:
        opts.init_options = None

    # CLI relay args override anything from the preset
    forward = opts.relay_forward.split(',') if opts.relay_forward else None
    forward_reqs = opts.relay_forward_requests.split(',') if opts.relay_forward_requests else None
    if opts.relay_match:
        from .relay import RelaySpec
        relay_spec = RelaySpec(
            match_method=opts.relay_match,
            send_method=opts.relay_send or 'workspace/executeCommand',
            respond_method=opts.relay_respond or opts.relay_match.replace('/request', '/response'),
            command=opts.relay_command,
            forward_notifications=forward,
            forward_requests=forward_reqs,
            init_options=cli_relay_init_options,
        )
    else:
        if forward and relay_spec:
            relay_spec.forward_notifications = forward
        if forward_reqs and relay_spec:
            relay_spec.forward_requests = forward_reqs
        # CLI --relay-init-options overrides preset relay_spec init_options
        if cli_relay_init_options and relay_spec:
            relay_spec.init_options = {**(relay_spec.init_options or {}), **cli_relay_init_options}

    if not server_commands:
        log(
            "Usage: rass [OPTIONS] -- <primary-server> [args] [-- <secondary-server> [args]]..."
        )
        sys.exit(1)

    # Validate
    assert opts.delay_ms >= 0, "--delay-ms must be non-negative"

    try:
        asyncio.run(run_multiplexer(
            server_commands, opts,
            relay_server_commands=relay_server_commands,
            relay_spec=relay_spec,
        ))
    except KeyboardInterrupt:
        log("\nShutting down...")
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
