"""Svelte preset: svelteserver + tailwindcss-language-server with custom logic."""


def servers():
    """Return svelteserver and tailwindcss-language-server."""
    return [
        ["svelteserver", "--stdio"],
        ["tailwindcss-language-server", "--stdio"],
    ]
