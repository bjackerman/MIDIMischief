"""Tests for ProfileWatcher."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.profile.watcher import ProfileWatcher, ReloadResult


def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _write_profile(path: Path, name: str = "demo", extra_mapping: bool = False) -> None:
    profile = {
        "name": name,
        "layers": {
            "0": {
                "name": "Default",
                "mappings": [
                    {
                        "id": "m1",
                        "input": {"control": "note:60"},
                        "action": {"type": "keyboard", "keys": ["a"]},
                    }
                ]
                + (
                    [
                        {
                            "id": "m2",
                            "input": {"control": "note:62"},
                            "action": {"type": "keyboard", "keys": ["b"]},
                        }
                    ]
                    if extra_mapping
                    else []
                ),
            }
        },
    }
    path.write_text(json.dumps(profile))


def test_watcher_loads_on_construct(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p, "demo")
    w = ProfileWatcher(p)
    assert w.current is not None
    assert w.current.name == "demo"


def test_watcher_emits_signal_on_initial_load(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p)
    w = ProfileWatcher(p)
    seen: list[ReloadResult] = []
    w.profile_reloaded.connect(seen.append)
    # initial=True in __init__ already fired before we connected; force one
    r = w.force_reload()
    assert isinstance(r, ReloadResult)
    assert r.error is None
    assert r.changed is False  # same content as before


def test_watcher_detects_external_change(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p, "v1")
    w = ProfileWatcher(p)
    seen: list[ReloadResult] = []
    w.profile_reloaded.connect(seen.append)

    # Modify the file. We touch then rewrite to mimic an editor save.
    time.sleep(0.05)
    p.write_text(json.dumps({
        "name": "v2",
        "layers": {"0": {"name": "Default", "mappings": []}},
    }))
    # Pump the event loop so QFileSystemWatcher fires + debounce elapses
    for _ in range(50):
        qapp.processEvents()
        time.sleep(0.02)
    assert any(r.profile is not None and r.profile.name == "v2" for r in seen)


def test_watcher_keeps_old_profile_on_load_error(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p, "v1")
    w = ProfileWatcher(p)
    # Corrupt the file
    p.write_text("{ this is not json")
    seen: list[ReloadResult] = []
    w.profile_reloaded.connect(seen.append)
    r = w.force_reload()
    assert r.error is not None
    assert r.profile is not None  # the old one is preserved
    assert r.profile.name == "v1"


def test_watcher_handles_missing_file_on_reload(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p)
    w = ProfileWatcher(p)
    p.unlink()
    r = w.force_reload()
    assert r.error is not None
    assert "no longer exists" in r.error
    assert r.profile is not None  # old one still cached


def test_watcher_changed_flag_set_when_content_differs(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    _write_profile(p, "v1")
    w = ProfileWatcher(p)
    _write_profile(p, "v1", extra_mapping=True)
    r = w.force_reload()
    assert r.changed is True
    assert r.profile is not None
    assert len(r.profile.all_mappings(0)) == 2
