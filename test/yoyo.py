#!/usr/bin/env python
"""
Cross-platform relay for rassumfrassum tests.
Connects a client script to rassumfrassum, relaying stdio between them.

Usage: yoyo.py <client_script> [client_args...] --rass-- [rass_args...]

Example:
  yoyo.py ./client.py --rass-- -- python ./server.py --name s1 -- python ./server.py --name s2
  yoyo.py ./client.py --rass-- python
"""

import asyncio
import sys
import os
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
        print(
            f"[yoyo.py][{name}] Relay error: {e}", file=sys.stderr, flush=True
        )
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_relay(client_args, rass_args, env):
    """Run the relay with proper cleanup."""
    # Start client
    client = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        *client_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # Let client stderr pass through
        env=env,
    )

    # Start rassumfrassum with provided arguments
    rass = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "rassumfrassum",
        *rass_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # Let rassumfrassum stderr pass through
        env=env,
    )

    # Create relay tasks for bidirectional communication
    await asyncio.gather(
        relay_stream(client.stdout, rass.stdin, "client→rass"),
        relay_stream(rass.stdout, client.stdin, "rass→client"),
    )
    await client.wait()
    await rass.wait()

    crc = client.returncode
    rrc = rass.returncode

    print(f"[yoyo.py] client rc=${crc} rass rc={rrc}", file=sys.stderr)
    return 0 if (crc == 0 and rrc == 0) else 1


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: yoyo.py <client_script> [client_args...] --rass-- [rass_args...]",
            file=sys.stderr,
        )
        sys.exit(1)

    script = Path(sys.argv[1]).resolve()

    # Find --rass-- separator
    try:
        rass_idx = sys.argv.index('--rass--')
    except ValueError:
        print("Error: Missing --rass-- separator", file=sys.stderr)
        sys.exit(1)

    client_args = sys.argv[
        2:rass_idx
    ]  # Args between client_script and --rass--
    rass_args = sys.argv[rass_idx + 1 :]  # Args after --rass--

    # Set up PYTHONPATH to include src directory
    repo_root = Path(__file__).parent.parent
    src_dir = repo_root / "src"

    env = os.environ.copy()
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{src_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = str(src_dir)

    exit_code = asyncio.run(run_relay(client_args, rass_args, env))
    sys.exit(exit_code)
