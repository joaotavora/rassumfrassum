"""
Async test helpers for LSP testing.
"""

import asyncio
import inspect
import os
import sys
from typing import Callable, cast

from .json import JSON, read_message, write_message, read_message_sync, write_message_sync
from .stdio import create_stdin_reader, create_stdout_writer

def log(who: str, msg: str) -> None:
    """Log to stderr."""
    print(f"[{who}] {msg}", file=sys.stderr, flush=True)

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


class LspTestEndpoint:
    """Async LSP test helper."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, name: str):
        self.reader = reader
        self.writer = writer
        self.name = name
        self._next_id = 1

    @staticmethod
    async def create(name : str = "client") -> 'LspTestEndpoint':
        """Create an LSP test endpoint connected to stdin/stdout."""
        reader = await create_stdin_reader()
        writer = await create_stdout_writer()
        return LspTestEndpoint(reader=reader, writer=writer, name=name)

    async def notify(self, method: str, params: JSON) -> None:
        """Send a notification (no response expected)."""
        await write_message(
            self.writer,
            {'jsonrpc': '2.0', 'method': method, 'params': params},
        )

    async def request(self, method: str, params: JSON | None = None) -> int:
        """Send a request and return the request id."""
        req_id = self._next_id
        self._next_id += 1
        msg = {'jsonrpc': '2.0', 'id': req_id, 'method': method}
        if params is not None:
            msg['params'] = params
        await write_message(self.writer, msg)
        return req_id

    async def respond(self, req_id: int, result: JSON | None) -> None:
        """Send a response to a server request."""
        msg = {'jsonrpc': '2.0', 'id': req_id, 'result': result}
        await write_message(self.writer, msg)

    async def read_message(self, timeout_sec: float = 5.0) -> JSON:
        """
        Read a single JSONRPC message with timeout.

        Use sparingly - prefer the specific read_notification(), read_response(),
        or read_request() methods when you know what you're expecting.
        This is useful when you need to verify what message arrives (or doesn't)
        without filtering.

        Raises asyncio.TimeoutError if no message arrives within timeout.
        """
        msg = await asyncio.wait_for(
            read_message(self.reader),
            timeout=timeout_sec
        )
        if not msg:
            raise EOFError("EOF while waiting for message")
        return msg

    async def read_notification(self, method: str) -> JSON:
        """Read messages until we get a notification with the given method."""
        while True:
            msg = await read_message(self.reader)
            if not msg:
                raise EOFError(f"EOF while waiting for notification {method}")

            # Skip responses (have 'id' field)
            if 'id' in msg:
                log(self.name, f"Skipping non-notification: {msg}")
                continue

            # Check if it's the notification we want
            if msg.get('method') == method:
                return msg['params']

            log(self.name, f"Skipping uninteresting notification: {msg}")

    async def read_request(self, method) -> tuple[int, JSON]:
        """Read messages until we get a request for the given method"""
        while True:
            msg = await read_message(self.reader)
            if not msg:
                raise EOFError(f"EOF while waiting for request {method}")

            if 'id' not in msg:
                log(self.name, f"Skipping notification: {msg}")
                continue

            if 'method' not in msg:
                log(self.name, f"Skipping server response: {msg}")
                continue

            if  msg["method"] == method:
                return (msg["id"], cast(JSON, msg.get('params')))
            log(self.name, f"Skipping uninteresting request: {msg}")

    async def read_response(self, req_id: int) -> JSON:
        """Read messages until we get a response with the given id."""
        while True:
            msg = await read_message(self.reader)
            if not msg:
                raise EOFError(f"EOF while waiting for response to id={req_id}")

            # Skip notifications (no 'id' field)
            if 'id' not in msg:
                log(self.name, f"Skipping notification: {msg.get('method')}")
                continue

            # Skip server requests (have both 'id' and 'method')
            if 'method' in msg:
                log(self.name, f"Skipping server request: {msg.get('method')} id={msg['id']}")
                continue

            # Check if it's the response we want
            if msg['id'] == req_id:
                return msg

            log(self.name, f"Skipping response: id={msg['id']}")

    async def initialize(
        self, capabilities: JSON | None = None, rootUri: str | None = None
    ) -> JSON:
        """
        Send initialize request and initialized notification.
        Returns the initialize response.
        """
        import os

        # Default capabilities that most servers expect
        default_caps = {
            'textDocument': {
                'synchronization': {
                    'dynamicRegistration': False,
                    'willSave': True,
                    'willSaveWaitUntil': True,
                    'didSave': True,
                }
            },
            'general': {'positionEncodings': ['utf-16']},
        }

        # Merge with provided capabilities
        if capabilities:
            from .util import dmerge

            merged_caps = dmerge(default_caps.copy(), capabilities)
        else:
            merged_caps = default_caps

        # Default rootUri to current directory
        if rootUri is None:
            rootUri = f"file://{os.getcwd()}"

        # Send initialize request
        log(self.name, "Sending initialize")
        req_id = await self.request(
            'initialize', {'rootUri': rootUri, 'capabilities': merged_caps}
        )

        # Read initialize response
        msg = await self.read_response(req_id)
        log(self.name, "Got initialize response")
        server_info = msg.get('result', {}).get('serverInfo', {})
        if server_info:
            log(
                self.name,
                f"Server: {server_info.get('name')} v{server_info.get('version')}",
            )

        # Send initialized notification
        log(self.name, "Sending initialized")
        await self.notify('initialized', {})

        return msg

    async def byebye(self) -> None:
        """Send shutdown request and exit notification, then exit the program."""
        log(self.name, "Sending shutdown")
        req_id = await self.request('shutdown')
        await self.read_response(req_id)
        log(self.name, "Got shutdown response")

        await self.notify('exit', {})
        log(self.name, "done!")

        # FIXME: The Windows-specific stdio machinery in stdio.py is
        # fragile and deadlocks during normal asyncio cleanup. Don't
        # have time to debug it.  Force exit on Windows, clean exit
        # elsewhere.
        if os.getenv('WINDOWS_KLUDGE'):
            os._exit(0)
        else:
            sys.exit(0)

    async def assert_no_message_pending(self, timeout_sec: float) -> None:
        """Assert that no message arrives within the given timeout."""
        try:
            msg = await asyncio.wait_for(
                read_message(self.reader),
                timeout=timeout_sec
            )
            raise AssertionError(f"Expected no message, but got: {msg}")
        except asyncio.TimeoutError:
            # This is what we expect - no message arrived
            pass


async def _run_toy_server_async(
    name: str,
    version: str,
    capabilities: JSON,
    request_handlers: 'dict[str, Callable[[int, JSON | None], JSON | None]]',
    notification_handlers: 'dict[str, Callable[[JSON | None], None]]',
    raw_request_handlers: 'dict[str, Callable[[int, JSON | None, Callable[[JSON], None]], None]]'
) -> None:
    """Internal async implementation of toy LSP server."""
    loop = asyncio.get_event_loop()

    # Setup async stdin/stdout using cross-platform functions
    reader = await create_stdin_reader()
    writer = await create_stdout_writer()

    log(name, "Started!")

    tasks = []
    should_stop = False

    async def handle_async_request(msg_id: int, method: str, params: JSON | None, handler):
        """Handle a single async request."""
        try:
            result = await handler(msg_id, params)
            response = {
                'jsonrpc': '2.0',
                'id': msg_id,
                'result': result
            }
            await write_message(writer, response)
        except Exception as e:
            log(name, f"Error in async handler for {method}: {e}")

    while not should_stop:
        try:
            message = await read_message(reader)
            if message is None:
                break

            method = message.get('method')
            msg_id = message.get('id')
            params = message.get('params')

            # Handle requests (messages with id)
            if msg_id is not None and method:
                if method in raw_request_handlers:
                    # Raw handler - it will send messages itself
                    handler = raw_request_handlers[method]
                    def send_msg(msg: JSON):
                        write_message_sync(msg)
                    handler(msg_id, params, send_msg)
                elif method in request_handlers:
                    handler = request_handlers[method]

                    # Check if handler is async
                    if inspect.iscoroutinefunction(handler):
                        # Spawn async handler as a task
                        task = asyncio.create_task(handle_async_request(msg_id, method, params, handler))
                        tasks.append(task)
                    else:
                        # Call sync handler directly
                        result = handler(msg_id, params)
                        response = {
                            'jsonrpc': '2.0',
                            'id': msg_id,
                            'result': result
                        }
                        await write_message(writer, response)

                    # Special handling for shutdown
                    if method == 'shutdown':
                        log(name, "shutting down")
                        should_stop = True
                else:
                    log(name, f"Unhandled request {method} (id={msg_id})")

            # Handle notifications (messages without id)
            elif method and msg_id is None:
                if method in notification_handlers:
                    notification_handlers[method](params)
                else:
                    log(name, f"got notification {method}")

            # Handle responses from client (e.g., workspace/configuration response)
            elif msg_id == 999 and method is None:
                log(name, f"Got response to workspace/configuration request: {message}")
                # Validate response and send notification if correct
                result = message.get('result')
                if (isinstance(result, list) and len(result) == 1 and
                    isinstance(result[0], dict) and result[0].get('pythonPath') == '/usr/bin/python3'):
                    # Response is correct, send success notification
                    await write_message(writer, {
                        'jsonrpc': '2.0',
                        'method': 'custom/requestResponseOk',
                        'params': {'server': name}
                    })
                    log(name, "Response validation passed, sent success notification")
                else:
                    log(name, f"Response validation FAILED: {result}")

        except Exception as e:
            log(name, f"Error: {e}")
            break

    # Wait for all pending async tasks
    if tasks:
        log(name, f"Waiting for {len(tasks)} pending tasks")
        await asyncio.gather(*tasks)

    log(name, "stopped")


def run_toy_server(
    name: str,
    version: str = '1.0.0',
    capabilities: JSON | None = None,
    request_handlers: 'dict[str, Callable[[int, JSON | None], JSON | None]] | None' = None,
    notification_handlers: 'dict[str, Callable[[JSON | None], None]] | None' = None,
    raw_request_handlers: 'dict[str, Callable[[int, JSON | None, Callable[[JSON], None]], None]] | None' = None
) -> None:
    """
    Run a toy LSP server for testing.

    Args:
        name: Server name for serverInfo
        version: Server version
        capabilities: Server capabilities (defaults to empty dict)
        request_handlers: Dict mapping method names to (msg_id, params) -> result handlers.
                         Handlers can be sync or async functions. Async handlers are spawned as tasks.
        notification_handlers: Dict mapping method names to (params) -> None handlers
        raw_request_handlers: Dict mapping method names to (msg_id, params, send_message) handlers.
                              Use sparingly. These handlers get a send_message(msg: JSON) callback
                              for sending arbitrary JSONRPC messages (e.g., duplicate responses).
                              The handler must send the response(s) manually.
    """
    # Default minimal capabilities
    if capabilities is None:
        capabilities = {}

    # Default handlers
    default_request_handlers: dict[str, 'Callable[[int, JSON | None], JSON | None]'] = {
        'initialize': lambda msg_id, params: {
            'capabilities': capabilities,
            'serverInfo': {'name': name, 'version': version}
        },
        'shutdown': lambda msg_id, params: None,
        'textDocument/hover': lambda msg_id, params: {
            "contents": {"kind": "markdown", "value": "oh yeah "},
            "range": {
                "start": {"line": 0, "character": 5},
                "end": {"line": 0, "character": 10}
            }
        }
    }

    # Merge user handlers (user handlers override defaults)
    if request_handlers:
        default_request_handlers.update(request_handlers)
    request_handlers = default_request_handlers

    if notification_handlers is None:
        notification_handlers = {}

    if raw_request_handlers is None:
        raw_request_handlers = {}

    # Run the async implementation
    asyncio.run(_run_toy_server_async(name, version, capabilities, request_handlers, notification_handlers, raw_request_handlers))

def scaled_timeout(timeout: int | float) -> int | float:
    """Scale timeout by TIMEOUT_SCALE environment variable (default 1.0)."""
    scale = float(os.environ.get('TIMEOUT_SCALE', '1.0'))
    return timeout * scale
