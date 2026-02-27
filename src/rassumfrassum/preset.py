"""Preset loading and management for rassumfrassum."""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from .util import PresetResult, ExtendedPresetResult


def _get_config_dirs() -> list[Path]:
    """
    Get user config directories for rassumfrassum in XDG fallback order.

    Returns list in priority order:
    1. $XDG_CONFIG_HOME/rassumfrassum (if XDG_CONFIG_HOME is set)
    2. ~/.config/rassumfrassum (default XDG location)
    3. ~/.rassumfrassum (legacy/alternative location)
    """
    dirs: list[Path] = []

    # XDG_CONFIG_HOME/rassumfrassum
    if xdg_config := os.environ.get('XDG_CONFIG_HOME'):
        dirs.append(Path(xdg_config) / 'rassumfrassum')

    # ~/.config/rassumfrassum (default XDG)
    home = Path.home()
    dirs.append(home / '.config' / 'rassumfrassum')

    # ~/.rassumfrassum (legacy)
    dirs.append(home / '.rassumfrassum')

    return dirs


def load_preset(name_or_path: str) -> ExtendedPresetResult:
    """
    Load preset by name or file path.

    Search order for preset names (without '/'):
    1. User config directories (XDG_CONFIG_HOME, ~/.config, ~/.rassumfrassum)
    2. Bundled presets directory

    Args:
        name_or_path: 'python' or './my_preset.py'

    Returns:
        (server_commands, logic_class, relay_server_commands, relay_spec, init_options)
    """
    # Path detection: contains '/' means external file
    if '/' in name_or_path:
        module = _load_preset_from_file(name_or_path)
    else:
        # Try user config directories first
        for config_dir in _get_config_dirs():
            preset_path = config_dir / f'{name_or_path}.py'
            if preset_path.exists():
                module = _load_preset_from_file(str(preset_path))
                break
        else:
            # Fall back to bundled preset
            module = _load_preset_from_bundle(name_or_path)

    servers_fn = getattr(module, 'servers', None)
    lclass_fn = getattr(module, 'logic_class', None)
    relay_servers_fn = getattr(module, 'relay_servers', None)
    relay_spec_fn = getattr(module, 'relay_spec', None)
    init_options_fn = getattr(module, 'init_options', None)

    return (
        servers_fn() if servers_fn else [],
        lclass_fn() if lclass_fn else None,
        relay_servers_fn() if relay_servers_fn else [],
        relay_spec_fn() if relay_spec_fn else None,
        init_options_fn() if init_options_fn else None,
    )


def _load_preset_from_file(filepath: str) -> Any:
    """Load from external Python file using importlib.util."""
    abs_path = os.path.abspath(filepath)

    spec = importlib.util.spec_from_file_location("_preset_module", abs_path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"Cannot load preset from {filepath}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["_preset_module"] = module
    spec.loader.exec_module(module)
    return module


def _load_preset_from_bundle(name: str) -> Any:
    """Load bundled preset from rassumfrassum.presets subpackage."""
    # Find the presets subpackage location
    presets_spec = importlib.util.find_spec('rassumfrassum.presets')
    if presets_spec is None or presets_spec.origin is None:
        raise FileNotFoundError(f"Cannot find rassumfrassum.presets package")

    presets_dir = os.path.dirname(presets_spec.origin)
    preset_path = os.path.join(presets_dir, f'{name}.py')
    return _load_preset_from_file(preset_path)
