"""
Utils for lspylex
"""

import sys
from typing import Any

JSON = dict[str, Any]  # pyright: ignore[reportExplicitAny]

def log(prefix : str, s : str):
    print(f"[{prefix}] {s}", file=sys.stderr)
