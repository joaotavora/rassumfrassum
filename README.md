[![Tests](https://github.com/joaotavora/rassumfrassum/actions/workflows/test.yml/badge.svg)][build-status]
[![PyPI version](https://img.shields.io/pypi/v/rassumfrassum)](https://pypi.org/project/rassumfrassum/)

# rassumfrassum

Connects one LSP client to multiple LSP servers. 

It spawns one or more stdio-enabled [LSP][lsp] server subprocesses,
communicates with them via pipes, and handles a client connected to
its own stdio.  `rass` behaves like an LSP server, so clients think
they are talking to single LSP server, even though they are secretly
talking to many.

An LSP client like Emacs's [Eglot][eglot] can find a python file in
some project and invoke it like so (`C-u M-x eglot` probably helps):

```bash
rass -- basedpyright-langserver --stdio -- ruff server
```

This should start managing Python files within a project with two
servers instead of one.  The `--` separate `rass`'s options from
`basedpyright`'s from `ruff`'s.

To set up other clients, check their documentation.  

## Issues?

[Read this first](#bugs_and_issues), please.

## Installation

I hope to have made `pip install rassumfrassum` do the right thing by
now.  If I haven't, you can probably clone this repo and call the
top-level `rass` wrapper script directly, since this doesn't have any
dependencies.

## Features

- Merges and synchronizes diagnostics from multiple servers into a
  single `textDocument/publishDiagnostics` event.
- Requests `textDocument/codeActions` from all servers supporting it;
  other requests go to the first server that supports the
  corresponding capability.
- Tries its best to merge server capabilities announcements and to
  track which inferior server supports which capability.
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
  because servers don't know about each other and they could clash.

### Architecture

The codebase lives in `src/rassumfrassum/` and is split into several modules:

- `rassum.py` is the main entry point with command-line
  processing. `run_multiplexer` starts a bunch of async tasks to read
  from the clients and servers, and waits for all of them.  The local
  lexical state in `run_multiplexer` tracks JSONRPC requests,
  responses, and notifications, and crucially the progress of ongoing
  aggregation attempts.  In as much as possible, `rassum.py` should be
  just a JSONRPC-aggregator and not know anything about particular
  custom handling of LSP message types.  There are a few violations of
  this principle, but whenever it needs to know what to do, it
  asks/informs the upper layer in `frassum.py` about in-transit
  messages.

- `frassum.py` contains the business logic used by `rassum.py` facilities.
  This one fully knows about LSP.  So it knows, for example, how to
  merge `initialize` and `shutdown` responses, when to reject a stale
  `textDocument/publishDiagnostics` and how to do the actual work for
  aggregation.

- `lolo.py` provides logging utilities for debugging and monitoring
  the multiplexer's operation.

- `tete.py` contains test utilities used by both client and server
  test scripts.
  
- `jaja.py` handles bare JSON-over-stdio logistics and is completely
  ignorant of LSP. It deals with protocol framing and I/O operations.

### Testing

There are tests under `test/`. Each test is a subdir, usually with a
`client.py`, a `server.py` (of which instances are spawned to emulate
multiple servers) and a `run.sh`, which creates a FIFO special file to
wire up the stdio connections and launches `client.py` connected to
`rass`.  `client.py` has the test assertions.  Both `client.py` and
`server.py` use common utils from `src/rassumfrassum/tete.py`.

To run all tests, use `test/run-all.sh`.

### Logging

The `stderr` output of rass is useful for peeking into the
conversation between all entities and understanding how the
multiplexer operates.

### FAQ 

_(...not really, noone's really asked anything yet...)_

#### Related projects

There's [lspx][lspx]!  Never tried it, but some people are using it.
Development started in this Eglot discussion thread:
https://github.com/joaotavora/eglot/discussions/1429

There's also this defunct [lsplex][lsplex] thing by myself in C++ that
went nowhere.

#### Project name?  

I'm tired of fretting about names.  Kudos if you can guess where I
stole this one from.  Used to be called dada, btw.

<a name=bugs_and_issues></a>
#### Bugs?

Probably a million.  The LSP flora is hard enough to navigate, and
maintaining the [Eglot][eglot] client is hard enough because of that.
So this is fun and potentially useful but adds another failure point.
A pretty big one at that, since of the hundreds (thousands?)  of LSP
servers out there, there are uncountable combinations of them, and
some will definitely trip you up.
  
#### Issue reports

Read the preceding section.  If you use this and want to report
something, you can start discussions or create issues at will.  If you
create an issue, I might just close it with a `cantmakesenseofthis`
label which just means I can't make sense of it just yet.  Also I have
very little time for OSS these days, so this is a totally NO WARRANTY,
YMMV thing.  If I close your issue just like that, doesn't mean you're
a bad person, so don't fret.  If you can provide an easy, simple, 100%
idiot-proof recipe demonstrating the bug the chances that I'll address
it are slightly higher.  Else, just fork this repo, this is just
Python and you're probably a programmer right?

#### Did you vibe code this junk?

Yeah, a bit, with some heavy coaching, then I took over.  The boring
bits are definitely an LLM's.

#### Future/roadmap?

I might rewrite this in Rust or C++ if it makes sense.  Having an LSP
middleware opens up some possibilities for making JSON communication
more efficient.
  
### Options to `rass`

Use `--help` to see all options.

The `--delay-ms N` option delays all JSONRPC messages sent to the
client by N milliseconds. Each message gets its own independent timer,
so if two messages arrive at `t=0.5s` and `t=1.5s` with a 3000ms
delay, they'll be dispatched at `t=3.5s` and `t=4.5s`
respectively. Useful for diagnostics and testing.

The `--drop-tardy` option controls an aspect of the "aggregation".  If
it's true and a server takes too long to respond to a request, or send
a mergeworthy notification, any messages that arrive too late are
simply dropped and the client sees whatever it got when the timeout
expired.  If it's false, the most up-to-date state of the aggregation
is simply retransmitted to the client.  The default is false.

[eglot]: https://github.com/joaotavora/eglot
[lsp]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/
[build-status]: https://github.com/joaotavora/rassumfrassum/actions/workflows/test.yml
