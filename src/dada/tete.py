#!/usr/bin/env python3
"""
Test utilities for LSP client and server tests.
"""

import sys
import select
import time
from typing import Callable, cast

from dada.jaja import JSON, read_message_sync, write_message_sync

# Client utilities

def log(prefix: str, msg: str):
    print(f'[{prefix}] {msg}', file=sys.stderr)

def send_and_log(message: JSON, description: str):
    """Send a message and log what we're doing."""
    log("client", description)
    write_message_sync(message)

def do_initialize() -> JSON:
    """Send initialize request and return the response."""
    send_and_log({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {}
    }, "Sending initialize")

    msg = read_message_sync()
    assert msg is not None, "Expected initialize response"
    assert 'result' in msg, f"Expected 'result' in initialize response: {msg}"
    assert 'capabilities' in msg['result'], f"Expected 'capabilities' in initialize result: {msg}"
    log("client", "Got initialize response")
    return msg

def do_initialized():
    """Send initialized notification."""
    send_and_log({
        'jsonrpc': '2.0',
        'method': 'initialized',
        'params': {}
    }, "Sending initialized notification")

def do_shutdown():
    """Send shutdown request and exit notification."""
    send_and_log({
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'shutdown',
        'params': {}
    }, "Sending shutdown")

    msg = read_message_sync()
    assert msg is not None, "Expected shutdown response"
    assert 'id' in msg and msg['id'] == 3, f"Expected response with id=3: {msg}"
    assert 'result' in msg, f"Expected 'result' in shutdown response: {msg}"
    log("client", "Got shutdown response")

    send_and_log({
        'jsonrpc': '2.0',
        'method': 'exit'
    }, "Sending exit notification")

    log("client", "done!")

def assert_no_message_pending(timeout_sec: float = 0.1):
    """
    Assert that no message is available on stdin within timeout.
    Raises assertion error if a message is available.
    """
    readable, _, _ = select.select([sys.stdin.buffer], [], [], timeout_sec)
    if readable:
        msg = read_message_sync()
        raise AssertionError(f"Unexpected message received (should have been dropped): {msg}")
    log("client", f"Verified no message pending (waited {timeout_sec}s)")


# Server utilities

# Realistic capability responses based on real LSP servers
CAPABILITIES = {
    'basedpyright': {
        'textDocumentSync': {'willSave': True, 'change': 2, 'openClose': True},
        'definitionProvider': {'workDoneProgress': True},
        'hoverProvider': {'workDoneProgress': True},
        'completionProvider': {
            'triggerCharacters': ['.', '[', '"', "'"],
            'resolveProvider': True,
            'workDoneProgress': True
        },
        'signatureHelpProvider': {'triggerCharacters': ['(', ',', ')']},
        'codeActionProvider': {'codeActionKinds': ['quickfix', 'source.organizeImports']},
    },
    'ruff': {
        'codeActionProvider': {
            'codeActionKinds': [
                'quickfix',
                'source.fixAll.ruff',
                'source.organizeImports.ruff'
            ],
            'resolveProvider': True
        },
        'diagnosticProvider': {'identifier': 'Ruff', 'interFileDependencies': False},
        'documentFormattingProvider': True,
        'documentRangeFormattingProvider': True,
        'hoverProvider': True,
        'textDocumentSync': {'change': 2, 'openClose': True}
    }
}

def make_diagnostic(line: int, char_start: int, char_end: int,
                    severity: int, message: str, source: str | None = None) -> JSON:
    """Create a diagnostic object."""
    diag: JSON = {
        'range': {
            'start': {'line': line, 'character': char_start},
            'end': {'line': line, 'character': char_end}
        },
        'severity': severity,
        'message': message
    }
    if source:
        diag['source'] = source
    return diag


def run_server(
    name: str,
    version: str = '1.0.0',
    capabilities: str = 'basedpyright',
    on_didopen: Callable[[str, JSON], None] | None = None,
    on_didchange: Callable[[str, JSON], None] | None = None,
    on_initialized: Callable[[], None] | None = None
) -> None:
    """
    Run a generic LSP server for testing.

    Args:
        name: Server name for serverInfo
        version: Server version
        capabilities: Which capability set to use ('basedpyright' or 'ruff')
        on_didopen: Callback for textDocument/didOpen notifications (uri, text_doc)
        on_didchange: Callback for textDocument/didChange notifications (uri, text_doc)
        on_initialized: Callback for initialized notification
    """

    log(name, "Started!")

    while True:
        try:
            message = read_message_sync()
            if message is None:
                break

            method = message.get('method')
            msg_id = message.get('id')

            if method == 'initialize':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': {
                        'capabilities': CAPABILITIES[capabilities],
                        'serverInfo': {
                            'name': name,
                            'version': version
                        }
                    }
                }
                write_message_sync(response)

            elif method == 'shutdown':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': None
                }
                write_message_sync(response)
                log(name, "shutting down")
                break

            elif method == 'textDocument/hover':
                response = {
                    'jsonrpc': '2.0',
                    'id': msg_id,
                    'result': {
                        "contents": {
                            "kind": "markdown",
                            "value": "oh yeah "
                        },
                        "range": {
                            "start": {"line": 0, "character": 5 },
                            "end": {"line": 0, "character": 10 }
                        }
                    }
                }
                write_message_sync(response)

            elif method == 'textDocument/didOpen' and on_didopen:
                params = cast(JSON, message.get('params', {}))
                text_doc = cast(JSON, params.get('textDocument', {}))
                uri = cast(str, text_doc.get('uri', 'file:///unknown'))
                log(name, f"got notification {method}")
                on_didopen(uri, text_doc)

            elif method == 'textDocument/didChange' and on_didchange:
                params = cast(JSON, message.get('params', {}))
                text_doc = cast(JSON, params.get('textDocument', {}))
                uri = cast(str, text_doc.get('uri', 'file:///unknown'))
                log(name, f"got notification {method}")
                on_didchange(uri, text_doc)

            elif method == 'initialized':
                log(name, f"got notification {method}")
                if on_initialized:
                    on_initialized()

            elif msg_id == 999 and method is None:
                log(name, f"Got response to workspace/configuration request: {message}")
                # Validate response and send notification if correct
                result = message.get('result')
                if (isinstance(result, list) and len(result) == 1 and
                    isinstance(result[0], dict) and result[0].get('pythonPath') == '/usr/bin/python3'):
                    # Response is correct, send success notification
                    write_message_sync({
                        'jsonrpc': '2.0',
                        'method': 'custom/requestResponseOk',
                        'params': {'server': name}
                    })
                    log(name, "Response validation passed, sent success notification")
                else:
                    log(name, f"Response validation FAILED: {result}")

            else:
                if msg_id is not None:
                    log(name, f"request {method} (id={msg_id})")
                else:
                    log(name, f"notification {method}")

        except Exception as e:
            log(name, f"Error: {e}")
            break

    log(name, "stopped")
