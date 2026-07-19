"""Tests for the validate / diff / export / import CLI subcommands.

We invoke them in-process via the entry function, not via subprocess,
to keep the test fast and avoid platform-specific quoting.
"""

from __future__ import annotations

import json
from pathlib import Path

from midimap.cli import diff as diff_cmd
from midimap.cli import export_import
from midimap.cli import validate as validate_cmd
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    MediaAction,
    Profile,
)


def _make_profile(path: Path, name: str = "demo", action=None) -> None:
    p = Profile(
        name=name,
        layers={
            0: Layer(
                name="Default",
                mappings=[
                    Mapping(
                        id="m1",
                        input=InputSpec(control="note:60"),
                        action=action or KeyboardAction(keys=["a"]),
                    )
                ],
            )
        },
    )
    path.write_text(json.dumps(p.model_dump(mode="json")))


def test_validate_prints_summary(tmp_path: Path, capsys):
    p = tmp_path / "p.json"
    _make_profile(p, "demo")
    rc = validate_cmd.run(
        type(
            "A",  # type: ignore[no-untyped-def]
            (),
            {"profile": str(p), "json": False, "log_level": "WARNING"},
        )()
    )
    out = capsys.readouterr().out
    assert "profile: demo" in out
    assert "Default" in out
    assert rc == 0


def test_validate_reports_invalid_profile(tmp_path: Path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("not json")
    ns = type("A", (), {"profile": str(p), "json": False, "log_level": "WARNING"})()  # type: ignore[no-untyped-def]
    rc = validate_cmd.run(ns)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


def test_diff_identical_exits_1_by_default(tmp_path: Path, capsys):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    _make_profile(p1, "demo")
    _make_profile(p2, "demo")
    ns = type("A", (), {"profile_a": str(p1), "profile_b": str(p2), "json": False, "no_changes_ok": False, "log_level": "WARNING"})()  # type: ignore[no-untyped-def]
    rc = diff_cmd.run(ns)
    out = capsys.readouterr().out
    assert "no changes" in out
    assert rc == 1


def test_diff_detects_added_mapping(tmp_path: Path, capsys):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _make_profile(a, "demo")
    _make_profile(b, "demo", action=MediaAction(key="play_pause"))
    ns = type("A", (), {"profile_a": str(a), "profile_b": str(b), "json": False, "no_changes_ok": True, "log_level": "WARNING"})()  # type: ignore[no-untyped-def]
    rc = diff_cmd.run(ns)
    out = capsys.readouterr().out
    assert "action.type: keyboard -> media" in out
    assert rc == 0


def test_export_changes_format(tmp_path: Path):
    src = tmp_path / "in.json"
    dst = tmp_path / "out.yaml"
    _make_profile(src)
    ns = type("A", (), {"source": str(src), "destination": str(dst), "log_level": "WARNING"})()  # type: ignore[no-untyped-def]
    rc = export_import.run_export(ns)
    assert rc == 0
    assert dst.exists()
    text = dst.read_text()
    assert "name: demo" in text
    assert "note:60" in text


def test_import_writes_destination(tmp_path: Path):
    src = tmp_path / "in.yaml"
    dst = tmp_path / "out.json"
    src.write_text(
        "version: 1\n"
        "name: demo\n"
        "layers:\n"
        "  '0':\n"
        "    name: Default\n"
        "    mappings:\n"
        "      - id: m1\n"
        "        input:\n"
        "          control: 'note:60'\n"
        "        action:\n"
        "          type: keyboard\n"
        "          keys: [a]\n"
    )
    ns = type("A", (), {"source": str(src), "destination": str(dst), "log_level": "WARNING"})()  # type: ignore[no-untyped-def]
    rc = export_import.run_import(ns)
    assert rc == 0
    assert dst.exists()
    loaded = json.loads(dst.read_text())
    assert loaded["name"] == "demo"
