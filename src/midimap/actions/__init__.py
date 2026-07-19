"""Action layer.

An :class:`Action` is what the :class:`~midimap.mapping.MappingEngine`
emits. The :class:`ActionExecutor` dispatches to the right backend:
keyboard, media, builtin, script, or plugin. M2 implements keyboard
fully; media/builtin/script are M3; plugin is M6.

Design points
-------------
- ``dry_run`` flag on the executor logs every action instead of
  performing it. The GUI exposes a global "Test Mode" toggle.
- Every dispatcher path catches and logs exceptions so a single bad
  action cannot kill the engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events import NormalizedEvent
    from ..profile.schema import Mapping

log = logging.getLogger(__name__)


@dataclass
class Action:
    """A concrete thing to do, in response to a triggering event.

    ``kind`` is one of ``"keyboard" | "media" | "builtin" | "script" | "plugin"``.
    ``params`` is the action-specific parameter dict (already validated
    by the profile schema). ``raw`` is the original :class:`Mapping`,
    for debugging/UI display. ``event`` is the triggering event, so
    downstream backends can read ``$value`` / ``$control`` / ``$event``
    from it (M3 will implement the template substitution).
    """

    kind: str
    params: dict[str, Any]
    raw: Mapping
    event: NormalizedEvent

    @classmethod
    def from_mapping(cls, mapping: Mapping, event: NormalizedEvent) -> Action:
        params = mapping.action.model_dump()
        # The triggering event is attached as a private field so backends
        # can do template substitution without re-passing it.
        params["_event"] = event
        return cls(kind=mapping.action.type, params=params, raw=mapping, event=event)


class ActionExecutor:
    """Dispatch Action → the right backend.

    The executor is constructed once at startup and shared across
    threads. The dispatch methods are quick (microseconds) so we don't
    bother with a worker pool for the M2 subset; the script action in
    M3 will be the one that needs a real pool.
    """

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        # Lazy import to avoid pulling pynput at module load time (the
        # monitor CLI doesn't need it).
        from .keyboard import KeyboardSender

        self._keyboard = KeyboardSender(dry_run=dry_run)
        # Stubs for M3/M6 — see actions/builtin.py, actions/script.py, etc.
        # They raise NotImplementedError on execute(); the M3 milestone
        # will replace them.

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
                log.warning("%smedia action not yet implemented (M3): %s", pfx, action.params)
                return False
            if action.kind == "builtin":
                log.warning("%sbuiltin action not yet implemented (M3): %s", pfx, action.params)
                return False
            if action.kind == "script":
                log.warning("%sscript action not yet implemented (M3)", pfx)
                return False
            if action.kind == "plugin":
                log.warning("%splugin action not yet implemented (M6): %s", pfx, action.params)
                return False
            log.warning("unknown action kind: %r", action.kind)
            return False
        except Exception:
            log.exception("action execution failed: %s", action.kind)
            return False

    def shutdown(self) -> None:
        """Release any held resources (M3 will add the script pool here)."""
        self._keyboard.close()


__all__ = ["Action", "ActionExecutor"]
