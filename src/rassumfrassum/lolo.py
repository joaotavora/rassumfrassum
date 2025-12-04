from datetime import datetime
import sys

def log(s: str):
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]  # truncate microseconds to milliseconds
    print(f"i[{timestamp}] {s}", file=sys.stderr)

def warn(s: str):
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]  # truncate microseconds to milliseconds
    print(f"W[{timestamp}] WARN: {s}", file=sys.stderr)

def event(s: str):
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]  # truncate microseconds to milliseconds
    print(f"e[{timestamp}] {s}", file=sys.stderr)


