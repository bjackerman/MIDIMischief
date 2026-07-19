"""PluginAction executor — invoke a registered plugin.

Replaces the M4 stub that always returned ``False``. The action
schema (PluginAction) is unchanged: ``module`` (legacy), ``function``,
``args`` (dict). M6 deprecates ``module`` and uses the
:class:`PluginRegistry` to look up by name.
"""

from __future__ import annotations

import logging
from typing import Any

from ..plugins import get_registry
from ..plugins.registry import PluginSpec

log = logging.getLogger(__name__)


def run_plugin(
    function_name: str,
    args: dict[str, Any] | None = None,
    *,
    event: Any = None,
    dry_run: bool = False,
) -> bool:
    """Invoke a plugin by registered name.

    Returns True on success, False on missing plugin or exception.
    Dry-run logs the would-be call without invoking.
    """
    registry = get_registry()
    spec: PluginSpec | None = registry.get(function_name)
    if spec is None:
        log.warning("plugin %r not found; registered: %s", function_name, registry.names())
        return False
    if dry_run:
        log.info("[DRY-RUN] plugin: %s(%s) [event=%s]", function_name, args, event)
        return True
    try:
        result = spec.call(args=args, event=event)
    except Exception:
        log.exception("plugin %r raised", function_name)
        return False
    return _truthy(result)


def _truthy(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return True


__all__ = ["run_plugin"]
