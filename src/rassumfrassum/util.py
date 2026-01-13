from datetime import datetime
import sys

# Type aliases for presets
ServerCommand = list[str]
ServerCommands = list[ServerCommand]
PresetResult = tuple[ServerCommands, type | None]

# Log levels (lower number = higher priority)
LOG_SILENT = 0
LOG_WARN = 1
LOG_INFO = 2
LOG_EVENT = 3
LOG_DEBUG = 4
LOG_TRACE = 5

# Global settings
_current_log_level = LOG_EVENT
_max_log_length = 4000

def set_log_level(level: int) -> None:
    """Set the global log level."""
    global _current_log_level
    _current_log_level = level

def get_log_level() -> int:
    """Get the current log level."""
    return _current_log_level

def set_max_log_length(max_len: int) -> None:
    """Set the maximum log message length (0 = unlimited)."""
    global _max_log_length
    _max_log_length = max_len

def _truncate(s: str) -> str:
    """Internal: truncate string if needed."""
    if _max_log_length <= 0 or len(s) <= _max_log_length:
        return s
    return f"{s[:_max_log_length]}... (truncated, {len(s)} bytes total)"

def _log(prefix: str, s: str, min_level: int) -> None:
    """Internal: common logging implementation."""
    if _current_log_level < min_level:
        return
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]
    print(f"{prefix}[{timestamp}] {_truncate(s)}", file=sys.stderr)

def info(s: str):
    """Log info-level message (high-level events, lifecycle)."""
    _log("i", s, LOG_INFO)

def debug(s: str):
    """Log debug-level message (method names, routing decisions)."""
    _log("d", s, LOG_DEBUG)

def trace(s: str):
    """Log trace-level message (full protocol details)."""
    _log("t", s, LOG_TRACE)

def warn(s: str):
    """Log warning message."""
    _log("W", "WARN: " + s, LOG_WARN)

def event(s: str):
    """Log JSONRPC protocol event."""
    _log("e", s, LOG_EVENT)

# Alias for backward compatibility
log = info

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


def expand_braces(pattern: str) -> list[str]:
    """Expand {a,b,c} brace groups in glob pattern.

    Examples:
        "**/*.{ts,js}" -> ["**/*.ts", "**/*.js"]
        "*.{a,b}.{x,y}" -> ["*.a.x", "*.a.y", "*.b.x", "*.b.y"]
        "no-braces" -> ["no-braces"]
    """
    import re

    # Find first brace group
    match = re.search(r'\{([^}]+)\}', pattern)
    if not match:
        return [pattern]

    # Split alternatives by comma
    alternatives = match.group(1).split(',')
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]

    # Recursively expand remaining braces
    results = []
    for alt in alternatives:
        for expanded in expand_braces(prefix + alt + suffix):
            results.append(expanded)
    return results
