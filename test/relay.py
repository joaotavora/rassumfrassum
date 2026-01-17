#!/usr/bin/env python
"""
Cross-platform relay for rassumfrassum tests.
Connects a client script to rassumfrassum, relaying stdio between them.

Usage: relay.py <client_script> <rass_args...>

Example:
  relay.py ./client.py -- python ./server.py --name s1 -- python ./server.py --name s2
"""
import asyncio
import sys
import os
import platform
from pathlib import Path


async def relay_stream(reader, writer, name):
    """Relay data from reader to writer."""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        print(f"[{name}] Relay error: {e}", file=sys.stderr, flush=True)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_relay():
    """Run the relay with proper cleanup."""
    if len(sys.argv) < 2:
        print("Usage: relay.py <client_script> <rass_args...>", file=sys.stderr)
        sys.exit(1)

    client_script = Path(sys.argv[1]).resolve()
    rass_args = sys.argv[2:]  # Arguments to pass to rassumfrassum

    # Set up PYTHONPATH to include src directory
    repo_root = Path(__file__).parent.parent
    src_dir = repo_root / "src"

    env = os.environ.copy()
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{src_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = str(src_dir)

    # Start client
    client = await asyncio.create_subprocess_exec(
        sys.executable,
        str(client_script),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # Let client stderr pass through
        env=env
    )

    # Start rassumfrassum with provided arguments
    rass = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "rassumfrassum",
        *rass_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # Let rassumfrassum stderr pass through
        env=env
    )

    # Create relay tasks for bidirectional communication
    client_exit_code = None
    try:
        await asyncio.gather(
            relay_stream(client.stdout, rass.stdin, "client→rass"),
            relay_stream(rass.stdout, client.stdin, "rass→client")
        )
        # Both streams finished - wait for client to exit
        try:
            await asyncio.wait_for(client.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        client_exit_code = client.returncode
        print(f"[RELAY] Client exited with code: {client_exit_code}", file=sys.stderr)
    except Exception as e:
        print(f"Relay error: {e}", file=sys.stderr)
        client_exit_code = 1
    finally:
        # Ensure both processes are terminated
        if client.returncode is None:
            client.terminate()
            try:
                await asyncio.wait_for(client.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                client.kill()
                await client.wait()

        if rass.returncode is None:
            rass.terminate()
            try:
                await asyncio.wait_for(rass.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                rass.kill()
                await rass.wait()

        # Use saved exit code if available, otherwise use current returncode
        if client_exit_code is None:
            client_exit_code = client.returncode if client.returncode is not None else 1

        return client_exit_code


async def main():
    """Main entry point with timeout."""
    try:
        # Run relay with a reasonable timeout (tests should complete quickly)
        exit_code = await asyncio.wait_for(run_relay(), timeout=10.0)
        sys.exit(exit_code)
    except asyncio.TimeoutError:
        print("Timeout: relay did not complete within 10 seconds", file=sys.stderr)
        sys.exit(124)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
