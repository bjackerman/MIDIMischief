"""KeyboardSender — wraps pynput.keyboard.Controller with dry-run support.

Behaviour
---------
- A combo like ``["ctrl", "shift", "k"]`` is sent as a chord:
  ctrl.down(), shift.down(), k.down(), k.up(), shift.up(), ctrl.up().
  Order is normalised so modifiers always go down first.
- ``dry_run=True`` logs the would-be send without touching the OS.
- On platforms where pynput isn't usable (macOS Accessibility not
  granted, Wayland, headless server) ``send`` raises ``RuntimeError``
  with a clear message. M2 surfaces this as a normal log line; the GUI
  will show a status-bar warning in M4.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterable

log = logging.getLogger(__name__)


# Modifier keys we want to press/release first in a combo.
_MODIFIERS = {
    "ctrl", "control", "shift", "alt", "option", "meta", "cmd", "command", "win", "super"
}


class KeyboardSender:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._controller = None
        self._Key = None
        self._init_error: Exception | None = None
        try:
            from pynput.keyboard import Controller, Key

            self._controller = Controller()
            self._Key = Key
        except Exception as e:  # pragma: no cover — environment-specific
            self._init_error = e
            log.warning("pynput not available, keyboard sends will no-op: %s", e)

    def send(self, keys: Iterable[str]) -> None:
        keys = [k.lower().strip() for k in keys if k and k.strip()]
        if not keys:
            return
        if self._init_error is not None or self._controller is None:
            raise RuntimeError(
                f"pynput keyboard unavailable: {self._init_error}"
            ) from self._init_error
        if self.dry_run:
            log.info("[DRY-RUN] keyboard chord: %s", keys)
            return

        # Sort so modifiers go first (purely cosmetic; chord works either way)
        mods = [k for k in keys if k in _MODIFIERS]
        non_mods = [k for k in keys if k not in _MODIFIERS]
        ordered = mods + non_mods

        Key = self._Key
        key_objs_down: list = []
        try:
            for name in ordered:
                ko = _resolve_key(name, Key)
                self._controller.press(ko)
                key_objs_down.append(ko)
            # Release in reverse order
            for ko in reversed(key_objs_down):
                self._controller.release(ko)
        except Exception:
            # Try to release anything we did press before bubbling
            for ko in reversed(key_objs_down):
                with contextlib.suppress(Exception):  # pragma: no cover
                    self._controller.release(ko)
            raise

    def close(self) -> None:
        # pynput's Controller has no explicit close, but keep the method
        # for symmetry with M3 script pool and future cleanup needs.
        self._controller = None


def _resolve_key(name: str, Key) -> object:
    """Turn a string key name into a pynput Key or KeyCode.

    - ``"ctrl"`` → ``Key.ctrl``
    - ``"f5"``   → ``Key.f5``
    - ``"a"``    → ``KeyCode.from_char('a')``
    """
    if hasattr(Key, name):
        return getattr(Key, name)
    # Common aliases
    aliases = {
        "control": "ctrl",
        "cmd": "cmd",
        "command": "cmd",
        "meta": "cmd",
        "super": "cmd",
        "win": "cmd",
        "option": "alt",
        "escape": "esc",
        "return": "enter",
        "space": "space",
    }
    if name in aliases and hasattr(Key, aliases[name]):
        return getattr(Key, aliases[name])
    if len(name) == 1:
        from pynput.keyboard import KeyCode

        return KeyCode.from_char(name)
    raise ValueError(f"unrecognised key name: {name!r}")
