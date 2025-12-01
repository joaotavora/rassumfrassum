# dada

LSP/JSONRPC multiplexer that connects one LSP client to multiple LSP
servers. It spawns one or more stdio-enabled LSP server subprocesses,
communicates with them via pipes, and handles a client connected to
its own stdio.

An LSP client like Emacs's Eglot can invoke it like this:

```bash
dada.py -- basedpyright-langserver --stdio -- ruff server
```

To start managing Python files with a project with two servers instead
of one.  The `--` separate `dada.py`'s options from `basedpyright`'s
from `ruff`'s.

To clients, it mostly feels like talking to a single LSP server.

## Installation

TBD.  I don't know much Python packaging pip stuff, etc.  Just call
`dada.py` for now.

## Features

- Merges and synchronizes diagnostics from multiple servers into a
  single `textDocucment/publishDiagnostics` event.
- Requests `textDocument/codeActions` from all servers supporting it
- Most other requests go to the first server that supports the
  corresponding capability.
- Zero dependencies beyond Python standard library (3.10+)

## Under the hood

### Message Routing

JSONRPC has requests, responses, and notifications. Here's how they're
routed:

**From client to servers:**

- All notifications go unchanged directly to all servers

- Some requests go only to one server, and that server's response is
  forwarded to the client

- Other requests go to multiple servers, and their responses are
  merged if they arrive in time

**From servers to client:**

- Most notifications go directly through, but some like
  `textDocument/publishDiagnostics` wait for all servers to send
  theirs, then the results are merged before forwarding to the client

- All server requests go to the client.  ID tweaking is necessary
  because server's don't know about each other and they could clash.

### Architecture

The codebase is split into three files: `dada.py`, `wowo.py` and
`jaja.py`.

- `jaja.py` handles bare JSON-over-stdio logistics and is completely
  ignorant of LSP. It deals with protocol framing and I/O operations.

- `dada.py` is the entry point with command-line
  processing. `run_multiplexer` starts a bunch of async tasks to read
  from the clients and servers, and waits for all of them.  The local
  lexical state in `run_multiplexer` tracks JSONRPC requests,
  responses, and notifications, and crucialy the progress of ongoing
  aggregation attempts.  In as much as possible, `dada.py` should be
  just a JSONRPC-aggregator and not know anything about particular
  custom handling of LSP message types.  There are a few violations of
  this principle, but whenever it needs to know what to do, it should
  asks/inform the upper layer in `wowo.py` about in-transit
  messages.  

- `wowo.py` contains the business logic used by `dada.py` facilities.
  This one fully knows about LSP.  So it knows, for example, how to
  merge `initialize` and `shutdown` responses, when to reject a stale
  `textDocument/publishDiagnostics` and how to do the actual work for
  aggregation.

### Testing

There are tests under `test/`. Each test is a subdir, usually with a
`client.py`, a `server.py` (of which instances are spawned to emulate
multiple servers) and a `run.sh`, which creates a FIFO special file to
wire up the stdio connections and launches `client.py` connected to
`dada.py`.  `client.py` has the test assertions.  Both `client.py` and
`server.py` use common utils in `test/client_common.py` and
`test/server_common.py`. 

To run all tests, use `test/run-all.sh`.

### Logging

The `stderr` output of dada.py is useful for peeking into the
conversation all entities and understanding how the
multiplexer operates.  


### Options to dada.py

The `--delay-ms N` option delays all JSONRPC messages sent to the
client by N milliseconds. Each message gets its own independent timer,
so if two messages arrive at `t=0.5s` and `t=1.5s` with a 3000ms
delay, they'll be dispatched at `t=3.5s` and `t=4.5s`
respectively. Useful for diagnostics and testing.
