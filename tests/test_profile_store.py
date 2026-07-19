"""Tests for the profile store (load/save JSON+YAML, error reporting)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from midimap.profile import ProfileLoadError, load_profile, save_profile
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    Profile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_json_sample():
    p = load_profile(FIXTURES / "sample_profile.json")
    assert p.name == "Maschine Mikro — Default"
    assert 0 in p.layers
    assert 1 in p.layers
    assert len(p.layers[0].mappings) == 8
    assert p.layers[0].mappings[0].action.keys == ["ctrl", "1"]
    assert p.layers[1].hold_to_activate is True


def test_load_yaml_sample():
    p = load_profile(FIXTURES / "sample_profile.yaml")
    assert p.name == "YAML smoke test"
    assert p.layers[0].mappings[0].action.keys == ["ctrl", "1"]


def test_load_json_with_line_comments():
    text = """
    // a friendly comment
    {
      "version": 1,
      "name": "with comments",
      "layers": { "0": { "name": "D" } }
    }
    """
    p = Profile.model_validate(json.loads(text.replace("//", "").split("{", 1)[1].rsplit("}", 1)[0].join(["{", "}"])) if False else {})
    # Easier: use load_profile_text directly.
    from midimap.profile.schema import load_profile_text

    p = load_profile_text(text, format="json")
    assert p.name == "with comments"


def test_load_bad_profile_raises_profile_load_error():
    with pytest.raises(ProfileLoadError):
        load_profile(FIXTURES / "bad_profile.json")


def test_load_missing_file_raises():
    with pytest.raises(ProfileLoadError, match="not found"):
        load_profile(FIXTURES / "does_not_exist.json")


def test_load_garbage_raises():
    p = FIXTURES / "_garbage.json"
    p.write_text("this is not { valid json or yaml: [", encoding="utf-8")
    try:
        with pytest.raises(ProfileLoadError):
            load_profile(p)
    finally:
        p.unlink()


def test_save_then_reload_json(tmp_path: Path):
    original = Profile(
        name="roundtrip-json",
        layers={
            0: Layer(
                mappings=[
                    Mapping(
                        id="pad1",
                        input=InputSpec(control="note:60"),
                        action=KeyboardAction(keys=["ctrl", "shift", "1"]),
                    )
                ]
            )
        },
    )
    p = tmp_path / "p.json"
    save_profile(original, p)
    reloaded = load_profile(p)
    assert reloaded.name == "roundtrip-json"
    assert reloaded.layers[0].mappings[0].action.keys == ["ctrl", "shift", "1"]


def test_save_then_reload_yaml(tmp_path: Path):
    original = Profile(
        name="roundtrip-yaml",
        layers={
            0: Layer(
                mappings=[
                    Mapping(
                        id="pad1",
                        input=InputSpec(control="note:60"),
                        action=KeyboardAction(keys=["a"]),
                    )
                ]
            )
        },
    )
    p = tmp_path / "p.yaml"
    save_profile(original, p)
    reloaded = load_profile(p)
    assert reloaded.name == "roundtrip-yaml"
    assert reloaded.layers[0].mappings[0].action.keys == ["a"]


def test_format_explicit_overrides_extension(tmp_path: Path):
    """A .yaml file with explicit format='json' should write JSON."""
    p = tmp_path / "weird.yaml"
    prof = Profile(name="x")
    save_profile(prof, p, format="json")
    # File should be valid JSON.
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["name"] == "x"
    # And it should not contain YAML-only constructs we didn't add.
    # (The simplest positive check: it's also parseable as JSON, which it is.)


def test_default_format_is_json(tmp_path: Path):
    p = tmp_path / "noext"
    save_profile(Profile(name="x"), p)
    json.loads(p.read_text(encoding="utf-8"))
