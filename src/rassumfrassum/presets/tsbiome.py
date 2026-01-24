"""TypeScript preset: typescript-language-server + biome."""


def servers():
    """Return typescript-language-server and biome lsp-proxy."""
    return [
        ['typescript-language-server', '--stdio'],
        ['biome', 'lsp-proxy'],
    ]
