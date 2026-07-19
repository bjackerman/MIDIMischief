"""Action layer.

An :class:`Action` is what the :class:`~midimap.mapping.MappingEngine`
emits. The :class:`ActionExecutor` dispatches to the right backend:
keyboard, media, builtin, script, or plugin. M2 implemented keyboard;
M3 added media + builtin + script. M6 implements plugin via the
:class:`midimap.plugins.PluginRegistry`.

Design points
-------------
- ``dry_run`` flag on the executor logs every action instead of
  performing it. The GUI exposes a global "Test Mode" toggle.
- Every dispatcher path catches and logs exceptions so a single bad
  action cannot kill the engine.
- Template substitution (``$value``, ``$control``, ...) is applied to
  the action ``params`` dict before dispatch, so script argv, builtin
  params, and command arguments all see the triggering event.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events import NormalizedEvent
    from ..profile.schema import Mapping

from .builtin import run_builtin
from .template import substitute

log = logging.getLogger(__name__)


@dataclass
class Action:
    """A concrete thing to do, in response to a triggering event.

    ``kind`` is one of ``"keyboard" | "media" | "builtin" | "script" | "plugin"``.
    ``params`` is the action-specific parameter dict (already validated
    by the profile schema and template-substituted). ``raw`` is the
    original :class:`Mapping`, for debugging/UI display. ``event`` is
    the triggering event.
    """

    kind: str
    params: dict[str, Any]
    raw: Mapping
    event: NormalizedEvent

    @classmethod
    def from_mapping(cls, mapping: Mapping, event: NormalizedEvent) -> Action:
        params = mapping.action.model_dump()
        # Apply template substitution: $value, $control, $device, etc.
        params = substitute(params, event)
        return cls(kind=mapping.action.type, params=params, raw=mapping, event=event)


class ActionExecutor:
    """Dispatch Action → the right backend.

    The executor owns a :class:`ScriptRunner` for script actions
    and looks plugins up in the :class:`PluginRegistry` for plugin
    actions. Builtin and media are stateless module-level calls.
    """

    def __init__(
        self,
        *,
        dry_run: bool = False,
        scripts_enabled: bool = True,
        confirm_risky: bool = True,
        confirm_callback=None,  # type: ignore[no-untyped-def]
    ) -> None:
        from .keyboard import KeyboardSender
        from .media import MediaKeySender
        from .script import ScriptRunner

        self.dry_run = dry_run
        self._keyboard = KeyboardSender(dry_run=dry_run)
        self._media = MediaKeySender(dry_run=dry_run)
        self._scripts = ScriptRunner(
            confirm_callback=confirm_callback,
            enabled=scripts_enabled,
            confirm_risky=confirm_risky,
            dry_run=dry_run,
        )

    @property
    def scripts(self) -> ScriptRunner:  # type: ignore[name-defined]  # noqa: F821
        return self._scripts

    # ---- public ----

    def execute(self, action: Action) -> bool:
        """Run the action. Returns True on success, False on error/unsupported."""
        pfx = "[DRY-RUN] " if self.dry_run else ""
        try:
            if action.kind == "keyboard":
                keys = action.params.get("keys", [])
                self._keyboard.send(keys)
                log.info("%skeyboard send: %s", pfx, keys)
                return True
            if action.kind == "media":
                key = action.params.get("key")
                ok = self._media.send(key)
                log.info("%smedia key: %s -> %s", pfx, key, ok)
                return ok
            if action.kind == "builtin":
                name = action.params.get("name")
                builtin_params = dict(action.params.get("params") or {})
                ok = run_builtin(name, builtin_params, dry_run=self.dry_run)
                log.info("%sbuiltin: %s(%s) -> %s", pfx, name, builtin_params, ok)
                return ok
            if action.kind == "script":
                return self._scripts.run(action.params, event=action.event)
            if action.kind == "plugin":
                return self._dispatch_plugin(action, pfx=pfx)
            log.warning("unknown action kind: %r", action.kind)
            return False
        except Exception:
            log.exception("action execution failed: %s", action.kind)
            return False

    def _dispatch_plugin(self, action: Action, *, pfx: str) -> bool:
        from .plugin import run_plugin

        fn = action.params.get("function") or action.params.get("module")
        args = action.params.get("args") or {}
        if not fn:
            log.warning("%splugin action missing 'function' name: %s", pfx, action.params)
            return False
        log.info("%splugin: %s(%s)", pfx, fn, args)
        return run_plugin(str(fn), args, event=action.event, dry_run=self.dry_run)

    def shutdown(self) -> None:
        """Release any held resources."""
        self._keyboard.close()
        self._media.close()


__all__ = ["Action", "ActionExecutor"]
