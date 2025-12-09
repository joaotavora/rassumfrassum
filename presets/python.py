"""Python preset: basedpyright + ruff."""

def get_servers():
    """Return basedpyright and ruff server commands."""
    return [
        ['basedpyright-langserver', '--stdio'],
        ['ruff', 'server']
    ]




