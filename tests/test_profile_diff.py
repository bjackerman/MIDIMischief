"""Tests for the profile structural diff."""

from __future__ import annotations

from midimap.profile.diff import diff, diff_to_dict
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    MediaAction,
    Profile,
    ScriptAction,
)


def _mapping(mid: str, control: str, action=None) -> Mapping:
    return Mapping(
        id=mid,
        input=InputSpec(control=control),
        action=action or KeyboardAction(keys=["a"]),
    )


def test_diff_identical_profiles_is_empty():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60")])})
    b = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60")])})
    assert diff(a, b).is_empty()


def test_diff_added_mapping():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60")])})
    b = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60"), _mapping("p2", "note:62")])})
    d = diff(a, b)
    assert not d.is_empty()
    assert "p2" in d.layer_diffs[0].added_mappings
    assert d.summary().startswith("layer 0: +1")


def test_diff_removed_mapping():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60"), _mapping("p2", "note:62")])})
    b = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60")])})
    d = diff(a, b)
    assert "p2" in d.layer_diffs[0].removed_mappings


def test_diff_changed_action_type():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60", KeyboardAction(keys=["a"]))])})
    b = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60", MediaAction(key="play_pause"))])})
    d = diff(a, b)
    chg = d.layer_diffs[0].changed_mappings["p1"]
    assert any("action.type" in c for c in chg.field_changes)


def test_diff_changed_action_value():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60", ScriptAction(command=["echo", "a"]))])})
    b = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60", ScriptAction(command=["echo", "b"]))])})
    d = diff(a, b)
    chg = d.layer_diffs[0].changed_mappings["p1"]
    assert any("action:" in c for c in chg.field_changes)


def test_diff_added_layer():
    a = Profile(layers={0: Layer()})
    b = Profile(layers={0: Layer(), 1: Layer(name="Shift")})
    d = diff(a, b)
    assert 1 in d.added_layers
    assert d.added_layers[1].name == "Shift"


def test_diff_removed_layer():
    a = Profile(layers={0: Layer(), 1: Layer(name="Shift")})
    b = Profile(layers={0: Layer()})
    d = diff(a, b)
    assert 1 in d.removed_layers


def test_diff_global_settings_changed():
    a = Profile()
    b = Profile(global_settings={"disable_scripts": True})
    d = diff(a, b)
    assert d.global_settings_changed


def test_diff_to_dict_round_trip_shape():
    a = Profile(layers={0: Layer(mappings=[_mapping("p1", "note:60")])})
    b = Profile(
        layers={0: Layer(mappings=[_mapping("p1", "note:60"), _mapping("p2", "note:62")])},
        global_settings={"disable_scripts": True},
    )
    d = diff(a, b)
    as_dict = diff_to_dict(d)
    assert as_dict["global_settings_changed"] is True
    assert "0" in as_dict["layer_diffs"]
    assert "p2" in as_dict["layer_diffs"]["0"]["added_mappings"]
