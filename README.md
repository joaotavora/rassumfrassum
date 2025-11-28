# dada

An LSP/JSONRPC multiplexer that connects one LSP client to multiple
LSP servers. It spawns one or more stdio-enabled LSP server
subprocesses, communicates with them via pipes, and handles a client
connected to its own stdio.

An LSP client like Emacs's Eglot can invoke it like this:

```bash
dada.py --some-dada-option=42 -- ./s1 --s1option=84 --foo -- ./s2 --s2option=24 --bar
```

To the client, it mostly feels like talking to a single LSP server.

## Features

- Single-threaded asyncio-based event loop
- Message logging to stderr for diagnostics
- Tweakable response / notification merging
- Zero dependencies beyond Python standard library (3.10+)

## Installation

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

## Logging

The stderr of `dada.py` is the main diagnostics tool. It logs all operations:

- Messages from `dada.py` itself, prefixed with `[dada]`

- Messages from each server's stderr, prefixed with the server's
  nickname (discovered dynamically from the `initialize` response)

## Message Routing

JSONRPC has requests, responses, and notifications. Here's how they're routed:

**From client to servers:**

- All notifications go unchanged directly to all servers

- Some requests go only to one server (usually the primary), and that
  server's response is forwarded to the client

- Other requests go to multiple servers, and their responses are
  merged if they arrive in time

**From servers to client:**

- Most notifications go directly through

- Some notifications like `textDocument/publishDiagnostics` wait for
  all servers to send theirs, then the results are merged before
  forwarding to the client

- All server requests go to the client. ID tweaking as necessary
  because server's don't know about each other and they could clash.

## Architecture

The codebase is split into three files:

`jsonrpc.py` handles bare JSONRPC/pipe logistics and is completely
ignorant of LSP. It deals with protocol framing and I/O operations.

`dada.py` is the entry point with command-line processing. It knows
about LSP requests, responses, and notifications, and does the
bookkeeping and tracking for the aggregation, the timeouts etc.
Shouldn't know anything about particular custom handling of specific
message types.  

`lsp_router.py` contains the business logic that uses the `dada.py`
facilities. Special handling for the `initialize` and `shutdown`
requests lives here. The `textDocument/publishDiagnostics` aggregation
logic should be here, but totally agnostic from the synchronization
managed by `dada.py`.

## Testing

There's are tests under `test/`. It uses simple `client.py` and and
`server.py` scripts (multiple copies can be spawned to emulate
multiple servers) and creates a fifo to wire up the stdio
connections. The stderr output from this test is useful for
understanding how the multiplexer operates.  All tests can be run with
`test/run-all.sh`.

## Options

The `--delay-ms N` option delays all JSONRPC messages sent to the
client by N milliseconds. Each message gets its own independent timer,
so if two messages arrive at t=0.5 and t=1.5 with a 3-second delay,
they'll be dispatched at t=3.5 and t=4.5 respectively. Useful for
diagnostics and testing.
