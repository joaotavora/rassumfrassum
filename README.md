[![Tests](https://github.com/joaotavora/rassumfrassum/actions/workflows/test.yml/badge.svg)][build-status]
[![PyPI version](https://img.shields.io/pypi/v/rassumfrassum)](https://pypi.org/project/rassumfrassum/)

# rassumfrassum

Connect an LSP client to multiple LSP servers. 

The `rass` program, the main entry point, behaves like an LSP stdio
server, so clients think they are talking to single LSP server, even
though they are secretly talking to many.  Behind the scenes more
stdio [LSP][lsp] server subprocesses are spawned.

![demo](./doc/demo.gif)

## Setup

Install the `rass` tool:

```bash
pip install rassumfrassum
```

Now install some language servers, say Python's [basedpyright][basedpyright] and [ruff][ruff]:

```bash
npm install -g basedpyright
pip install ruff
```

Tell your LSP client to call `rass python`:

* In Emacs's [Eglot][eglot], find a Python file in a project and `C-u
M-x eglot RET rass python RET`.

* In vanilla [Neovim][neovim], use this snippet (briefly tested with `nvim --clean -u snippet.lua`)

```lua
vim.lsp.config('rass-python', {
   cmd = {'rass','python'},
   filetypes = { 'python' },
   root_markers = { '.git', },
})
vim.lsp.enable('rass-python')
```

## Presets

Presets give you a uniform way to start typical sets of language
servers for a given language, while being flexible enough for
tweaking.  Most presets would be Python files with a `servers()`
function that returns a list of server commands.  

Advanced presets can hook into LSP messages to hide the typical
initialization/configuration pains from clients, see
[vue.py][vue-preset].

### Using Presets

The bundled `python` preset runs [basedpyright][basedpyright] and [ruff][ruff]:

```bash
rass python
```

You can add more servers on top of a preset using `--` separators.
For example, to add [codebook][codebook] for spell checking:

```bash
rass python -- codebook-lsp server
```

### User Presets

You can create your own presets or override bundled ones. Rass searches
these locations in order:

1. `$XDG_CONFIG_HOME/rassumfrassum/` (if XDG_CONFIG_HOME is set)
2. `~/.config/rassumfrassum/` (default)
3. `~/.rassumfrassum/` (legacy)
4. Bundled presets directory (last resort)

To use [ty][ty] instead of `basedpyright`, create `~/.config/rassumfrassum/python.py`:

```python
"""Python preset using ty instead of basedpyright."""

def servers():
    return [
        ['ty', 'server'],
        ['ruff', 'server']
    ]
```

## Issues?

[Read this first](#bugs_and_issues), please.

## Features

- Zero dependencies beyond Python standard library (3.10+)

## Under the hood

- Tries its best to merge server capabilities announcements into a
  consistent aggregate capability set.  
- Track which inferior server supports which capability.
- Merges and synchronizes diagnostics from multiple servers into a
  single `textDocument/publishDiagnostics` event.
- Client requests for `textDocument/codeActions` and
  `textDocument/completions` go to all servers supporting it, other
  requests go to the first server that supports the corresponding
  capability.
- All server requests go to the client.  ID tweaking is necessary
  because servers don't know about each other and they could clash.

### Architecture

The codebase lives in `src/rassumfrassum/` and is split into several modules:

- `main.py` is the main entry point with command-line processing and
  argument parsing. It calls `run_multiplexer` from `rassum.py` to
  start the multiplexer.

- `presets.py` handles preset discovery and loading, searching user
  config directories (XDG-compliant) and bundled presets.

- `rassum.py` contains `run_multiplexer` which starts a bunch of async
  tasks to read from the clients and servers, and waits for all of
  them.  The local lexical state in `run_multiplexer` tracks JSONRPC
  requests, responses, and notifications, and crucially the progress
  of ongoing aggregation attempts.  In as much as possible,
  `rassum.py` should be just a JSONRPC-aggregator and not know
  anything about particular custom handling of LSP message types.
  There are a few violations of this principle, but whenever it needs
  to know what to do, it asks/informs the upper layer in `frassum.py`
  about in-transit messages.

- `frassum.py` contains the business logic used by `rassum.py` facilities.
  This one fully knows about LSP.  So it knows, for example, how to
  merge `initialize` and `shutdown` responses, when to reject a stale
  `textDocument/publishDiagnostics` and how to do the actual work for
  aggregation.

- `util.py` provides logging utilities and general-purpose helpers
  like dict merging for debugging and monitoring the multiplexer's
  operation.

- `test.py` contains test utilities used by both client and server
  test scripts.

- `json.py` handles bare JSON-over-stdio logistics and is completely
  ignorant of LSP. It deals with protocol framing and I/O operations.

### Testing

There are tests under `test/`. Each test is a subdir, usually with a
`client.py`, a `server.py` (of which instances are spawned to emulate
multiple servers) and a `run.sh`, which creates a FIFO special file to
wire up the stdio connections and launches `client.py` connected to
`rass`.  `client.py` has the test assertions.  Both `client.py` and
`server.py` use common utils from `src/rassumfrassum/test.py`.

To run all tests, use `test/run-all.sh`.

### Logging

The `stderr` output of rass is useful for peeking into the
conversation between all entities and understanding how the
multiplexer operates.

### FAQ 

_(...not really, noone's really asked anything yet...)_

#### Related projects?

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
  
#### Issue reports?

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

#### Did I vibe code this junk?

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

The `--logic-class CLASS` option specifies which routing logic class
to use.  The default is `LspLogic`.  You can specify a simple class
name (which will be looked up in the `rassumfrassum.frassum` module)
or a fully qualified class name like `mymodule.MyCustomLogic`.  This
is useful for extending rass with custom routing behavior by
subclassing `LspLogic`.

The `--stream-diagnostics` and `--no-stream-diagnostics` options
control whether diagnostics are streamed incrementally or aggregated
before sending. When streaming is enabled (the default), clients
receive `$/streamDiagnostics` notifications as each server responds.
When disabled, diagnostics are aggregated and sent as standard
`textDocument/publishDiagnostics` notifications. See the [Streaming
Diagnostics Protocol Extension](#streaming-diagnostics-protocol-extension)
section for details.

<a name=streaming-diagnostics-protocol-extension></a>
### Streaming diagnostics

Rassumfrassum implements an optional experimental non-standard
protocol extension for streaming diagnostics from multiple
sources. Rather than having clients and users wait for aggregations,
this allows receiving diagnostics incrementally as different sources
of diagnostics potentially respond out-of-phase.  Although the
protocol is designed to serve Rass's use case (where sources ==
multiplexed servers) it could theoretically be reused by any server
that wants to provide different types of diagnostics (warnings, errors,
linter results) separately.

#### Protocol flow

Negotiation happens when the client advertises support by sending
`$streamingDiagnostics` capability in the `initialize`
request. Rassumfrassum responds with `$streamingDiagnosticsProvider`
set to `true` in its capabilities.

Now, consider a simple example with two servers and one file. When the
client sends `textDocument/didOpen` for `file.py` at version 0,
rassumfrassum forwards the notification to both servers.

Let's assume the first server quickly sends a
`textDocument/publishDiagnostics` notification which rassumfrassum
converts to `$/streamDiagnostics` and forwards to the client. This
notification includes the `uri` of the file, the `diagnostics` array,
the document `version` (0), and a bonus `token` identifying the source
server. The client stores these diagnostics indexed by the triplet
`(version, uri, token)`.  Let's also assume the second server doesn't
support `textDocument/publishDiagnostics` but rather
`textDocument/diagnostic` "pull" requests.  Rassumfrassum sends an
internal pull to it and the response is also converted to a
`$/streamDiagnostics` notification, with a different token but the
same `uri` and `version`.  The client stores this second batch
separately and updates its display by combining diagnostics from both
tokens.

Now the user edits the file. The client sends `textDocument/didChange`
with version 1. Both servers analyze the new content and the process
repeats. When each `$/streamDiagnostics` notification arrives, the
client replaces the old diagnostics for that specific `(version, uri,
token)` triplet. The diagnostics from the first server's version 0 are
replaced by its version 1 diagnostics. Same for the second server.

The `kind` field may be present with value `"unchanged"` to indicate
the diagnostics for this token haven't changed. In this case the
client reuses any previous diagnostics for that uri and token. 

A complete reference implementation can be found in
[eglot.el](https://git.savannah.gnu.org/cgit/emacs.git/tree/lisp/progmodes/eglot.el)
in the `eglot-handle-notification` method for
`$/streamDiagnostics`.

[eglot]: https://github.com/joaotavora/eglot
[lsp]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/
[build-status]: https://github.com/joaotavora/rassumfrassum/actions/workflows/test.yml
[lspx]: https://github.com/thefrontside/lspx
[lsplex]: https://github.com/joaotavora/lsplex
[basedpyright]: https://github.com/detachhead/basedpyright
[ty]: https://github.com/astral-sh/ty
[ruff]: https://github.com/astral-sh/ruff
[neovim]: https://neovim.io/
[codebook]: https://github.com/blopker/codebook
[typos]: https://github.com/tekumara/typos-lsp
[vue-preset]: https://github.com/joaotavora/rassumfrassum/blob/master/src/rassumfrassum/presets/vue.py
