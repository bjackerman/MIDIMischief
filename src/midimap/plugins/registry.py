"""Plugin registry — discover and invoke user-supplied Python callables.

A "plugin" is any Python callable exposed via the ``midimap.plugins``
entry-point group. The registry collects them at startup, validates
their signature, and lets a :class:`PluginAction` invoke them with
the action's args.

Example project layout for a plugin (publishable as a wheel)::

    # pyproject.toml of the plugin package
    [project.entry-points."midimap.plugins"]
    say_hello = "my_pkg:hello"

    # my_pkg/__init__.py
    def hello(text: str = "world", *, event=None) -> bool:
        print(f"hello {text} (event: {event})")
        return True

The mapping schema for a plugin action looks like::

    action:
      type: plugin
      function: say_hello
      args:
        text: "world"

The registry falls back to scanning the importable ``midimap_plugins``
module if no entry points are installed (useful for dev / quick
hacks).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "midimap.plugins"


@dataclass
class PluginSpec:
    name: str
    function: Callable[..., Any]
    signature: inspect.Signature

    def call(self, *, args: dict[str, Any] | None = None, event: Any = None) -> Any:
        """Invoke the plugin with ``args`` and a special ``event`` kwarg.

        The plugin's signature is inspected; the ``event`` kwarg is
        only passed if the plugin accepts it.
        """
        kw: dict[str, Any] = dict(args or {})
        if "event" in self.signature.parameters:
            kw["event"] = event
        return self.function(**kw)


class PluginRegistry:
    """Discover + cache plugin callables by name."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginSpec] = {}
        self._loaded = False

    def load(self) -> None:
        """Discover plugins via entry points and importable module."""
        if self._loaded:
            return
        self._loaded = True
        self._load_entry_points()
        self._load_legacy_module()

    def _load_entry_points(self) -> None:
        try:
            eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception as e:  # pragma: no cover
            log.debug("entry-point discovery failed: %s", e)
            return
        for ep in eps:
            try:
                fn = ep.load()
            except Exception as e:
                log.warning("failed to load plugin %s: %s", ep.name, e)
                continue
            self._register(ep.name, fn)

    def _load_legacy_module(self) -> None:
        """If a ``midimap_plugins`` module is importable, harvest its attrs."""
        try:
            mod = importlib.import_module("midimap_plugins")
        except ImportError:
            return
        for name in dir(mod):
            if name.startswith("_"):
                continue
            fn = getattr(mod, name)
            if callable(fn):
                self._register(name, fn)

    def _register(self, name: str, fn: Callable[..., Any]) -> None:
        if not callable(fn):
            log.warning("plugin %r is not callable", name)
            return
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = inspect.Signature()  # pragma: no cover
        self._plugins[name] = PluginSpec(name=name, function=fn, signature=sig)
        log.info("registered plugin %r", name)

    def get(self, name: str) -> PluginSpec | None:
        self.load()
        return self._plugins.get(name)

    def names(self) -> list[str]:
        self.load()
        return sorted(self._plugins)

    def all(self) -> list[PluginSpec]:
        self.load()
        return list(self._plugins.values())


# A process-wide singleton so the executor doesn't need to plumb
# the registry through every constructor.
_REGISTRY: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry()
    return _REGISTRY


def reset_registry() -> None:
    """Drop the singleton so tests can start fresh."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "ENTRY_POINT_GROUP",
    "PluginRegistry",
    "PluginSpec",
    "get_registry",
    "reset_registry",
]
