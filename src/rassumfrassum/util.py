from datetime import datetime
import sys

def info(s: str):
    """Log info-level message (high-level events, lifecycle)."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]  # truncate microseconds to milliseconds
    print(f"i[{timestamp}] {s}", file=sys.stderr)

# Alias for backward compatibility
log = info

def debug(s: str):
    """Log debug-level message (method names, routing decisions)."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]
    print(f"d[{timestamp}] {s}", file=sys.stderr)

def trace(s: str):
    """Log trace-level message (full protocol details with truncation)."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]
    print(f"t[{timestamp}] {s}", file=sys.stderr)

def warn(s: str):
    """Log warning message."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]
    print(f"W[{timestamp}] WARN: {s}", file=sys.stderr)

def event(s: str):
    """Log JSONRPC protocol event."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]
    print(f"e[{timestamp}] {s}", file=sys.stderr)

def truncate_for_log(s: str, max_len: int = 2000) -> str:
    """Truncate a string for logging, showing original length if truncated."""
    if len(s) <= max_len:
        return s
    return f"{s[:max_len]}... (truncated, {len(s)} bytes total)"

def is_scalar(v):
    return not isinstance(v, (dict, list, set, tuple))

def dmerge(d1: dict, d2: dict):
    """Merge d2 into d1 destructively.
    Non-scalars win over scalars; d1 wins on scalar conflicts."""

    result = d1.copy()
    for key, value in d2.items():
        if key in result:
            v1, v2 = result[key], value
            # Both dicts: recursive merge
            if isinstance(v1, dict) and isinstance(v2, dict):
                result[key] = dmerge(v1, v2)
            # Both lists: concatenate
            elif isinstance(v1, list) and isinstance(v2, list):
                result[key] = v1 + v2
            # One scalar, one non-scalar: non-scalar wins
            elif is_scalar(v1) and not is_scalar(v2):
                result[key] = v2  # d2's non-scalar wins
            elif not is_scalar(v1) and is_scalar(v2):
                result[key] = v1  # d1's non-scalar wins
            # Both scalars: d1 wins (keep result[key])
        else:
            result[key] = value
    return result


