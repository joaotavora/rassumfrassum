# lspylex

A simple, single-threaded LSP (Language Server Protocol) multiplexer that forwards JSONRPC messages between an LSP client and server, with logging.

## Features

- **Transparent forwarding**: Acts as a pass-through proxy between LSP client and server
- **Message logging**: All JSONRPC messages logged to stderr with direction indicators
- **Single-threaded**: Uses Python asyncio for efficient event-driven I/O
- **Zero dependencies**: Uses only Python standard library (3.10+)
- **Simple architecture**: Clean, readable code that's easy to understand and modify

## Installation

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

## Usage

```bash
lspylex -- <lsp-server-command> [server-args...]
```

The `--` separator is required to distinguish lspylex arguments from the server command.

### Examples

With pyright:
```bash
lspylex -- pyright-langserver --stdio
```

With pylsp:
```bash
lspylex -- pylsp
```

With clangd:
```bash
lspylex -- clangd
```

## How it works

The multiplexer:
1. Launches the specified LSP server as a subprocess
2. Forwards all client messages to the server (logged with `-->` to stderr)
3. Forwards all server messages to the client (logged with `<--` to stderr)
4. Handles LSP protocol framing (Content-Length headers + JSON body)

## Testing

A simple echo server is included for testing:

```bash
python test_client.py | venv/bin/lspylex -- python test_echo_server.py
```

You should see log messages showing the message flow:
```
--> initialize (id=1)
<-- response (id=1)
```
