"""Tests for the pydantic profile schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from midimap.profile.schema import (
    BuiltinAction,
    DeviceMatch,
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    MediaAction,
    PluginAction,
    Profile,
    ScriptAction,
)


def test_minimal_profile_defaults_to_layer_0():
    p = Profile()
    assert p.version == 1
    assert 0 in p.layers
    assert p.layers[0].name == "Default"
    assert p.layers[0].mappings == []


def test_profile_must_include_layer_0():
    with pytest.raises(ValidationError, match="layers must include key 0"):
        Profile(layers={1: Layer(name="Shift")})


def test_layer_keys_must_be_nonneg_int():
    with pytest.raises(ValidationError, match="non-negative int"):
        Profile(
            layers={
                0: Layer(name="Default"),
                -1: Layer(name="bad"),
            }
        )


def test_keyboard_action_normalises_keys():
    a = KeyboardAction(keys=["  Ctrl ", "SHIFT", "K"])
    assert a.keys == ["ctrl", "shift", "k"]


def test_keyboard_action_rejects_empty():
    with pytest.raises(ValidationError):
        KeyboardAction(keys=["", "  "])


def test_value_range_validated():
    with pytest.raises(ValidationError, match="value_min"):
        InputSpec(control="cc:1", value_min=50, value_max=10)


def test_press_duration_validated():
    with pytest.raises(ValidationError, match="min_press_ms"):
        InputSpec(control="note:60", min_press_ms=500, max_press_ms=200)


def test_action_discriminated_union_keyboard():
    a = Mapping(
        id="x",
        input=InputSpec(control="note:60"),
        action={"type": "keyboard", "keys": ["a"]},
    )
    assert isinstance(a.action, KeyboardAction)


def test_action_discriminated_union_media():
    a = Mapping(
        id="x",
        input=InputSpec(control="cc:1"),
        action={"type": "media", "key": "play_pause"},
    )
    assert isinstance(a.action, MediaAction)
    assert a.action.key == "play_pause"


def test_action_discriminated_union_builtin():
    a = Mapping(
        id="x",
        input=InputSpec(control="cc:1"),
        action={"type": "builtin", "name": "volume_set", "params": {"value": "$value"}},
    )
    assert isinstance(a.action, BuiltinAction)
    assert a.action.params == {"value": "$value"}


def test_builtin_action_rejects_unimplemented_quit_app():
    with pytest.raises(ValidationError, match="quit_app"):
        Mapping(
            id="x",
            input=InputSpec(control="cc:1"),
            action={"type": "builtin", "name": "quit_app", "params": {"name": "explorer"}},
        )


def test_action_discriminated_union_script():
    a = Mapping(
        id="x",
        input=InputSpec(control="note:60"),
        action={"type": "script", "command": ["python", "-V"], "timeout_s": 5.0},
    )
    assert isinstance(a.action, ScriptAction)
    assert a.action.timeout_s == 5.0
    assert a.action.risky is False


def test_action_discriminated_union_plugin():
    a = Mapping(
        id="x",
        input=InputSpec(control="note:60"),
        action={"type": "plugin", "name": "switch_workspace", "params": {"n": 1}},
    )
    assert isinstance(a.action, PluginAction)


def test_unknown_action_type_rejected():
    with pytest.raises(ValidationError):
        Mapping(
            id="x",
            input=InputSpec(control="note:60"),
            action={"type": "explode", "boom": True},
        )


def test_device_match_substring_case_insensitive():
    m = DeviceMatch(name_contains="Maschine")
    assert m.matches({"kind": "midi", "name": "Maschine Mikro MK3"})
    assert m.matches({"kind": "midi", "name": "MASCHINE MIKRO"})
    assert not m.matches({"kind": "midi", "name": "MPK Mini"})


def test_device_match_vid_pid():
    m = DeviceMatch(vid_pid="17cc:1700")
    assert m.matches({"kind": "midi", "name": "Anything", "vid_pid": "17cc:1700"})
    assert not m.matches({"kind": "midi", "name": "Anything", "vid_pid": "1234:5678"})


def test_device_match_kind_filters():
    m = DeviceMatch(kind="midi")
    assert m.matches({"kind": "midi", "name": "x"})
    assert not m.matches({"kind": "hid", "name": "x"})


def test_profile_all_mappings_returns_list():
    p = Profile(
        layers={
            0: Layer(
                mappings=[
                    Mapping(id="a", input=InputSpec(control="note:60"), action=KeyboardAction(keys=["a"])),
                    Mapping(id="b", input=InputSpec(control="note:61"), action=KeyboardAction(keys=["b"])),
                ]
            )
        }
    )
    assert len(p.all_mappings(0)) == 2
    assert p.all_mappings(99) == []


def test_profile_matches_device():
    p = Profile(device_match=DeviceMatch(name_contains="Mikro"))
    assert p.matches_device({"kind": "midi", "name": "Maschine Mikro MK3"})
    assert not p.matches_device({"kind": "midi", "name": "MPK Mini"})


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Profile(name="x", unexpected=True)
