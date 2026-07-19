"""Tests for template substitution."""

from __future__ import annotations

from midimap.actions.template import substitute
from midimap.events import EventType, NormalizedEvent, Value


def _ev(
    control: str = "cc:1",
    value: int = 100,
    velocity: int | None = 90,
    channel: int | None = 1,
    device: str = "midi:test",
    et: EventType = EventType.CHANGE,
    ts: int = 0,
) -> NormalizedEvent:
    return NormalizedEvent(
        device_id=device,
        control_id=control,
        event_type=et,
        value=Value(value),
        velocity=velocity,
        channel=channel,
        timestamp_ms=ts,
    )


def test_substitute_known_placeholders():
    ev = _ev(value=42, velocity=77, control="cc:7", device="midi:X", ts=0)
    out = substitute(
        "v=$value vel=$velocity c=$control d=$device e=$event ch=$channel t=$timestamp",
        ev,
    )
    assert out == "v=42 vel=77 c=cc:7 d=midi:X e=change ch=1 t=0"


def test_dollar_dollar_escape():
    ev = _ev(value=5)
    assert substitute("price: $$$value", ev) == "price: $5"
    assert substitute("literal $$ sign", ev) == "literal $ sign"


def test_unknown_placeholder_left_as_is():
    ev = _ev(value=5)
    assert substitute("$foo $bar $notaplaceholder", ev) == "$foo $bar $notaplaceholder"


def test_empty_value_for_missing_velocity_and_channel():
    ev = NormalizedEvent(
        device_id="midi:t",
        control_id="note:60",
        event_type=EventType.PRESS,
        value=Value(100),
        velocity=None,
        channel=None,
    )
    out = substitute("v=$velocity ch=$channel", ev)
    assert out == "v= ch="


def test_substitute_walks_list():
    ev = _ev(value=42, control="cc:7")
    out = substitute(["echo", "$value", "$control"], ev)
    assert out == ["echo", "42", "cc:7"]


def test_substitute_walks_dict_values_but_not_keys():
    ev = _ev(value=42, control="cc:7")
    out = substitute(
        {"_key$value": "value=$value", "literal": "$control"},
        ev,
    )
    # Keys are not substituted (they're parameter names, not values)
    assert out == {"_key$value": "value=42", "literal": "cc:7"}


def test_substitute_nested_structures():
    ev = _ev(value=10)
    out = substitute({"args": ["$value", "fixed"], "env": {"X": "$value"}}, ev)
    assert out == {"args": ["10", "fixed"], "env": {"X": "10"}}


def test_non_string_passes_through():
    ev = _ev(value=42)
    assert substitute(42, ev) == 42
    assert substitute(3.14, ev) == 3.14
    assert substitute(True, ev) is True
    assert substitute(None, ev) is None


def test_substitute_tuple_returns_tuple():
    ev = _ev(value=7)
    out = substitute(("a", "$value", "b"), ev)
    assert out == ("a", "7", "b")
    assert isinstance(out, tuple)
