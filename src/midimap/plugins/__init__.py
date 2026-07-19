"""Plugin system.

Public surface:
- :class:`PluginRegistry` — discover + invoke plugins
- :func:`get_registry` — process-wide singleton

A plugin is a Python callable registered via the
``midimap.plugins`` entry-point group. See ``registry.py`` for
details.
"""

from __future__ import annotations

from .registry import (
    ENTRY_POINT_GROUP,
    PluginRegistry,
    PluginSpec,
    get_registry,
    reset_registry,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "PluginRegistry",
    "PluginSpec",
    "get_registry",
    "reset_registry",
]
