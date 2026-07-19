"""Convert :class:`mido.Message` → :class:`NormalizedEvent`.

Returns ``None`` for messages we don't care about (clock, active sensing,
sysex, program change). Velocity-bearing messages carry the velocity both in
``value`` (so a single field flows through the pipeline) and in the
``velocity`` metadata field (so consumers can distinguish velocity from CC).
"""

from __future__ import annotations

import mido

from ..events import EventType, NormalizedEvent, Value


def midi_to_normalized(
    msg: mido.Message, device_id: str = "midi:unknown"
) -> NormalizedEvent | None:
    # Note On with vel=0 is the canonical "Note Off" on most controllers.
    if msg.type == "note_on" and msg.velocity > 0:
        return NormalizedEvent(
            device_id=device_id,
            control_id=f"note:{msg.note}",  # type: ignore[arg-type]
            event_type=EventType.PRESS,
            value=Value(msg.velocity),
            channel=msg.channel + 1,  # MIDI channels are 1-indexed for humans
            velocity=msg.velocity,
            raw=msg.bytes(),
        )
    if msg.type in ("note_off", "note_on"):
        return NormalizedEvent(
            device_id=device_id,
            control_id=f"note:{msg.note}",  # type: ignore[arg-type]
            event_type=EventType.RELEASE,
            value=Value(msg.velocity),
            channel=msg.channel + 1,
            velocity=msg.velocity,
            raw=msg.bytes(),
        )
    if msg.type == "control_change":
        return NormalizedEvent(
            device_id=device_id,
            control_id=f"cc:{msg.control}",  # type: ignore[arg-type]
            event_type=EventType.CHANGE,
            value=Value(msg.value),
            channel=msg.channel + 1,
            raw=msg.bytes(),
        )
    if msg.type == "polytouch":
        return NormalizedEvent(
            device_id=device_id,
            control_id=f"polyat:{msg.note}",  # type: ignore[arg-type]
            event_type=EventType.CHANGE,
            value=Value(msg.value),
            channel=msg.channel + 1,
            raw=msg.bytes(),
        )
    if msg.type == "aftertouch":
        return NormalizedEvent(
            device_id=device_id,
            control_id="channel_at",
            event_type=EventType.CHANGE,
            value=Value(msg.value),
            channel=msg.channel + 1,
            raw=msg.bytes(),
        )
    if msg.type == "pitchwheel":
        # 14-bit; show high byte (0..127) for the value field.
        v14 = msg.pitch + 8192
        return NormalizedEvent(
            device_id=device_id,
            control_id="pitch",
            event_type=EventType.CHANGE,
            value=Value(v14 >> 7),
            channel=msg.channel + 1,
            raw=msg.bytes(),
        )
    # Ignore program_change, clock, active_sensing, sysex, etc.
    return None
