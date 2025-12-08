"""Preset loading for rassumfrassum."""

import importlib
import importlib.util
import sys
from typing import Any

def load_preset(name_or_path: str) -> tuple[list[list[str]], type | None]:
    """
    Load preset by name or file path.

    Args:
        name_or_path: 'python' or './my_preset.py'

    Returns:
        (server_commands, logic_class)

    Raises:
        ModuleNotFoundError, FileNotFoundError, AttributeError
    """
    # Path detection: contains '/' means external file
    if '/' in name_or_path:
        module = _load_from_file(name_or_path)
    else:
        module = _load_from_bundle(name_or_path)

    # Extract required exports
    get_servers = getattr(module, 'get_servers')
    get_logic_class = getattr(module, 'get_logic_class')

    return get_servers(), get_logic_class()

def _load_from_file(filepath: str) -> Any:
    """Load from external Python file using importlib.util."""
    import os
    abs_path = os.path.abspath(filepath)

    spec = importlib.util.spec_from_file_location("_preset_module", abs_path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"Cannot load preset from {filepath}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["_preset_module"] = module
    spec.loader.exec_module(module)
    return module

def _load_from_bundle(name: str) -> Any:
    """Load bundled preset by name."""
    return importlib.import_module(f"rassumfrassum.presets.{name}")
