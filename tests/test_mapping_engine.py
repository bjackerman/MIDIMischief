"""Tests for MappingEngine."""

from __future__ import annotations

from midimap.events import EventType, NormalizedEvent, Value
from midimap.mapping import MappingEngine
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    Profile,
)


def _ev(
    control: str = "note:60",
    event_type: EventType = EventType.PRESS,
    value: int = 100,
    channel: int | None = 1,
    ts: int = 1000,
    device: str = "midi:test",
) -> NormalizedEvent:
    return NormalizedEvent(
        device_id=device,
        control_id=control,
        event_type=event_type,
        value=Value(value),
        channel=channel,
        timestamp_ms=ts,
    )


def _profile_with(layer0: Layer, layer1: Layer | None = None) -> Profile:
    layers: dict[int, Layer] = {0: layer0}
    if layer1 is not None:
        layers[1] = layer1
    return Profile(layers=layers)


# --- basic matching ---


def test_no_match_returns_none():
    eng = MappingEngine(
        _profile_with(Layer(mappings=[Mapping(id="x", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["a"]))]))
    )
    assert eng.process(_ev(control="note:99")) is None


def test_simple_press_match():
    mapping = Mapping(id="x", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["a"]))
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    action = eng.process(_ev())
    assert action is not None
    assert action.kind == "keyboard"
    assert action.params["keys"] == ["a"]


def test_event_type_filter_must_match():
    """``event: press`` should not match a release event."""
    mapping = Mapping(
        id="x",
        input=InputSpec(control="note:60", event="press"),
        action=KeyboardAction(keys=["a"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    assert eng.process(_ev(event_type=EventType.RELEASE)) is None
    assert eng.process(_ev(event_type=EventType.PRESS)) is not None


# --- value range ---


def test_value_range_min_only():
    """value_min=86 means "value >= 86"."""
    mapping = Mapping(
        id="x",
        input=InputSpec(control="cc:1", event="change", value_min=86),
        action=KeyboardAction(keys=["F1"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    assert eng.process(_ev(control="cc:1", event_type=EventType.CHANGE, value=85)) is None
    assert eng.process(_ev(control="cc:1", event_type=EventType.CHANGE, value=86)) is not None
    assert eng.process(_ev(control="cc:1", event_type=EventType.CHANGE, value=127)) is not None


def test_value_range_max_only():
    """value_max=42 means "value <= 42"."""
    mapping = Mapping(
        id="x",
        input=InputSpec(control="cc:1", event="change", value_max=42),
        action=KeyboardAction(keys=["F1"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    assert eng.process(_ev(control="cc:1", event_type=EventType.CHANGE, value=42)) is not None
    assert eng.process(_ev(control="cc:1", event_type=EventType.CHANGE, value=43)) is None


def test_value_range_band():
    """A knob in three bands: 0-42, 43-85, 86+ → three different mappings."""
    layers = {
        0: Layer(
            mappings=[
                Mapping(id="low", input=InputSpec(control="cc:1", value_max=42), action=KeyboardAction(keys=["F1"])),
                Mapping(id="mid", input=InputSpec(control="cc:1", value_min=43, value_max=85), action=KeyboardAction(keys=["F2"])),
                Mapping(id="high", input=InputSpec(control="cc:1", value_min=86), action=KeyboardAction(keys=["F3"])),
            ]
        )
    }
    eng = MappingEngine(Profile(layers=layers))
    assert eng.process(_ev(control="cc:1", value=10)).raw.id == "low"
    assert eng.process(_ev(control="cc:1", value=60)).raw.id == "mid"
    assert eng.process(_ev(control="cc:1", value=100)).raw.id == "high"


# --- press duration ---


def test_release_press_duration_within_window_matches():
    mapping = Mapping(
        id="tap",
        input=InputSpec(control="note:60", event="release", min_press_ms=50, max_press_ms=400),
        action=KeyboardAction(keys=["enter"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    eng.process(_ev(event_type=EventType.PRESS, ts=0))  # press starts
    action = eng.process(_ev(event_type=EventType.RELEASE, ts=200))
    assert action is not None
    assert action.raw.id == "tap"


def test_release_press_duration_too_short_does_not_match():
    mapping = Mapping(
        id="tap",
        input=InputSpec(control="note:60", event="release", min_press_ms=50, max_press_ms=400),
        action=KeyboardAction(keys=["enter"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    eng.process(_ev(event_type=EventType.PRESS, ts=0))
    assert eng.process(_ev(event_type=EventType.RELEASE, ts=10)) is None  # 10ms < 50ms


def test_release_press_duration_too_long_does_not_match():
    mapping = Mapping(
        id="hold",
        input=InputSpec(control="note:60", event="release", min_press_ms=50, max_press_ms=400),
        action=KeyboardAction(keys=["enter"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    eng.process(_ev(event_type=EventType.PRESS, ts=0))
    assert eng.process(_ev(event_type=EventType.RELEASE, ts=1000)) is None  # 1000ms > 400ms


# --- channel filter ---


def test_channel_filter():
    mapping = Mapping(
        id="x",
        input=InputSpec(control="note:60", channel=10),
        action=KeyboardAction(keys=["a"]),
    )
    eng = MappingEngine(_profile_with(Layer(mappings=[mapping])))
    assert eng.process(_ev(channel=9)) is None
    assert eng.process(_ev(channel=10)) is not None


# --- layer / hold-to-activate ---


def test_hold_to_activate_layer_activates_on_press_and_releases():
    profile = Profile(
        layers={
            0: Layer(
                mappings=[
                    Mapping(id="base", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["a"])),
                ]
            ),
            1: Layer(
                name="Shift (hold pad 17)",
                hold_to_activate=True,
                mappings=[
                    Mapping(id="shift_key", input=InputSpec(control="note:52"), action=KeyboardAction(keys=["shift"])),
                    Mapping(id="shifted_pad", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["F5"])),
                ],
            ),
        }
    )
    eng = MappingEngine(profile)
    assert 0 in eng.active_layers
    assert 1 not in eng.active_layers

    # Press the shift key (note:52) → layer 1 activates
    eng.process(_ev(control="note:52", event_type=EventType.PRESS, ts=0))
    assert 1 in eng.active_layers

    # While shift is held, pad 1 (note:60) fires the shifted mapping
    action = eng.process(_ev(control="note:60", event_type=EventType.PRESS, ts=10))
    assert action is not None
    assert action.raw.id == "shifted_pad"
    assert action.params["keys"] == ["f5"]  # KeyboardAction lowercases keys

    # Release shift → layer 1 deactivates
    eng.process(_ev(control="note:52", event_type=EventType.RELEASE, ts=20))
    assert 1 not in eng.active_layers

    # Now pad 1 fires the base mapping again
    action = eng.process(_ev(control="note:60", event_type=EventType.PRESS, ts=30))
    assert action is not None
    assert action.raw.id == "base"


# --- last-mapping-wins ---


def test_last_mapping_wins_in_layer():
    layers = {
        0: Layer(
            mappings=[
                Mapping(id="first", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["a"])),
                Mapping(id="second", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["b"])),
            ]
        )
    }
    eng = MappingEngine(Profile(layers=layers))
    action = eng.process(_ev())
    assert action is not None
    assert action.raw.id == "second"
    assert action.params["keys"] == ["b"]
