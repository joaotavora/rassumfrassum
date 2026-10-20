"""Vuetail preset: the vue preset plus tailwindcss-language-server."""

from rassumfrassum.presets import vue


def servers():
    """Vue's servers, then Tailwind's."""
    return vue.servers() + [['tailwindcss-language-server', '--stdio']]


def logic_class():
    """Same as the vue preset's."""
    return vue.logic_class()
