"""Python preset: basedpyright + ruff."""

def get_servers():
    """Return basedpyright and ruff server commands."""
    return [
        ['basedpyright-langserver', '--stdio'],
        ['ruff', 'server']
    ]

def get_logic_class():
    """Use standard LspLogic."""
    from rassumfrassum.frassum import LspLogic
    return LspLogic
