"""Tests for ``midi_to_normalized``."""

from __future__ import annotations

import mido

from midimap.devices.midi_normalizer import midi_to_normalized
from midimap.events import EventType


def _msg(type_, **kwargs):
    """Build a mido.Message in a forward-compatible way.

    mido's Message() rejects unknown kwargs in some versions; the safe path
    is to construct from a dict of channel=0 + type-specific fields.
    """
    return mido.Message(type_, **kwargs)


def test_note_on_with_velocity_is_press():
    msg = _msg("note_on", channel=0, note=60, velocity=100)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.event_type == EventType.PRESS
    assert ev.control_id == "note:60"
    assert ev.value == 100
    assert ev.velocity == 100
    assert ev.channel == 1  # 1-indexed for humans


def test_note_on_with_zero_velocity_is_release():
    """Some controllers send note_on vel=0 instead of note_off."""
    msg = _msg("note_on", channel=0, note=60, velocity=0)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.event_type == EventType.RELEASE
    assert ev.control_id == "note:60"


def test_note_off_is_release():
    msg = _msg("note_off", channel=0, note=60, velocity=64)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.event_type == EventType.RELEASE
    assert ev.velocity == 64


def test_control_change_is_change_event():
    msg = _msg("control_change", channel=0, control=7, value=64)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.event_type == EventType.CHANGE
    assert ev.control_id == "cc:7"
    assert ev.value == 64
    assert ev.channel == 1


def test_poly_aftertouch():
    msg = _msg("polytouch", channel=0, note=60, value=80)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.control_id == "polyat:60"
    assert ev.value == 80


def test_channel_aftertouch():
    msg = _msg("aftertouch", channel=0, value=42)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.control_id == "channel_at"
    assert ev.value == 42


def test_pitch_bend_high_byte():
    msg = _msg("pitchwheel", channel=0, pitch=0)  # center → 14-bit 8192
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.control_id == "pitch"
    assert ev.value == 64  # 8192 >> 7 == 64


def test_pitch_bend_max_up():
    msg = _msg("pitchwheel", channel=0, pitch=8191)  # full up
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.value == 127  # (8191+8192) >> 7 == 127


def test_clock_is_ignored():
    msg = _msg("clock")
    assert midi_to_normalized(msg, device_id="midi:test") is None


def test_active_sensing_is_ignored():
    msg = _msg("active_sensing")
    assert midi_to_normalized(msg, device_id="midi:test") is None


def test_program_change_is_ignored():
    msg = _msg("program_change", channel=0, program=5)
    assert midi_to_normalized(msg, device_id="midi:test") is None


def test_raw_bytes_captured():
    msg = _msg("control_change", channel=0, control=1, value=2)
    ev = midi_to_normalized(msg, device_id="midi:test")
    assert ev is not None
    assert ev.raw is not None
    # 0xB0 (CC) | channel 0, cc 1, value 2
    assert ev.raw[0] == 0xB0
    assert ev.raw[1] == 1
    assert ev.raw[2] == 2
