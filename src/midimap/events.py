"""Normalized event schema — the lingua franca between backends and the engine.

Every backend (MIDI in M1, HID in M6) produces :class:`NormalizedEvent`. The
:mod:`midimap.mapping.engine` consumes them without caring which backend
generated them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import NewType

DeviceId = NewType("DeviceId", str)
ControlId = NewType("ControlId", str)
# MIDI: 0..127 | HID button: 0/1 | HID axis: 0..32767 | pitch: 0..127 (we show high byte)
Value = NewType("Value", int)


class EventType(str, Enum):
    PRESS = "press"      # button/pad down
    RELEASE = "release"  # button/pad up
    CHANGE = "change"    # knob/slider/axis moved
    TAP = "tap"          # short press+release; fired on release if dur < threshold


@dataclass(frozen=True)
class NormalizedEvent:
    device_id: DeviceId
    control_id: ControlId
    event_type: EventType
    value: Value
    timestamp_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))
    # Optional metadata for routing/learning/debugging:
    channel: int | None = None
    velocity: int | None = None
    raw: bytes | None = None

    def __repr__(self) -> str:  # pragma: no cover — purely cosmetic
        return (
            f"NormalizedEvent({self.device_id} {self.control_id} {self.event_type.value} "
            f"value={self.value} ts={self.timestamp_ms})"
        )
