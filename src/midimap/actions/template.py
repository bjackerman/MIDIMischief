"""String template substitution for action parameters.

Supported placeholders (case-insensitive):

- ``$value``      — the triggering event's value (0..127 for MIDI, 0/1 for buttons, etc.)
- ``$velocity``   — the triggering event's velocity (MIDI Note On)
- ``$control``    — the normalised control id, e.g. ``"note:60"``
- ``$device``     — the device id, e.g. ``"midi:Maschine Mikro MK3 0"``
- ``$event``      — the event type as a string (``"press"``, ``"release"``, ``"change"``)
- ``$channel``    — MIDI channel (1-16) or empty
- ``$timestamp``  — the event's monotonic timestamp in ms

The placeholder syntax is intentionally shell-free: ``$name`` only. No
``${...}`` nesting, no escapes (yet). If you need a literal ``$`` in a
value, write ``$$`` (we expand ``$$`` → ``$``). This is enough for the
common "fire a script with the knob's value" case.

Substitution walks strings, list elements, and dict values. Non-string
values are left alone (int, bool, None, lists-of-lists, etc.).
"""

from __future__ import annotations

import re
from typing import Any

from ..events import NormalizedEvent

# Placeholder grammar: a name starts with $, followed by a letter or _,
# then letters/digits/_. The "$$" escape is handled separately.
_TOKEN_RE = re.compile(r"\$\$|\$([A-Za-z_][A-Za-z0-9_]*)")

# Names we know how to fill in. Anything else is left untouched (so a
# user who really wants a literal ``$foo`` in a script arg can write
# ``$$foo`` once we add escape support, or just avoid it).
_KNOWN = {
    "value",
    "velocity",
    "control",
    "device",
    "event",
    "channel",
    "timestamp",
}


def _event_value(name: str, event: NormalizedEvent) -> str | None:
    if name == "value":
        return str(int(event.value))
    if name == "velocity":
        return "" if event.velocity is None else str(int(event.velocity))
    if name == "control":
        return str(event.control_id)
    if name == "device":
        return str(event.device_id)
    if name == "event":
        return str(event.event_type.value)
    if name == "channel":
        return "" if event.channel is None else str(int(event.channel))
    if name == "timestamp":
        return str(int(event.timestamp_ms))
    return None  # unknown placeholder, leave as-is


def _substitute_string(s: str, event: NormalizedEvent) -> str:
    def _replace(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok == "$$":
            return "$"
        name = m.group(1)
        if name is None:
            return tok
        if name not in _KNOWN:
            return tok
        val = _event_value(name, event)
        return val if val is not None else ""

    return _TOKEN_RE.sub(_replace, s)


def substitute(obj: Any, event: NormalizedEvent) -> Any:
    """Recursively substitute placeholders in ``obj``.

    - str: each ``$name`` replaced; ``$$`` becomes ``$``.
    - list/tuple: substitute each element.
    - dict: substitute each value (keys are left alone — they're not
      parameters, they're parameter names).
    - anything else: returned unchanged.
    """
    if isinstance(obj, str):
        return _substitute_string(obj, event)
    if isinstance(obj, list):
        return [substitute(x, event) for x in obj]
    if isinstance(obj, tuple):
        return tuple(substitute(x, event) for x in obj)
    if isinstance(obj, dict):
        return {k: substitute(v, event) for k, v in obj.items()}
    return obj
