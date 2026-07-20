"""M5 GUI tests: profile editor mutations, watcher integration, edit-existing."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.app import App
from midimap.gui.main_window import MainWindow
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    MediaAction,
    Profile,
)
from midimap.profile.watcher import ProfileWatcher


def _profile() -> Profile:
    return Profile(
        layers={
            0: Layer(
                name="Default",
                mappings=[
                    Mapping(
                        id="pad1",
                        input=InputSpec(control="note:60"),
                        action=KeyboardAction(keys=["ctrl", "1"]),
                    )
                ],
            )
        }
    )


def test_profile_editor_adds_mapping(qapp):  # type: ignore[no-untyped-def]
    win = MainWindow(app=None)
    win._profile_tab.add_mapping(
        Mapping(
            id="pad2",
            input=InputSpec(control="note:62"),
            action=KeyboardAction(keys=["ctrl", "2"]),
        )
    )
    assert win._profile_tab.profile().all_mappings(0)[-1].id == "pad2"
    win.close()
    qapp.processEvents()


def test_profile_editor_replaces_mapping(qapp):  # type: ignore[no-untyped-def]
    win = MainWindow(app=None)
    new = Mapping(
        id="pad1",
        input=InputSpec(control="note:60"),
        action=MediaAction(key="play_pause"),
    )
    win._profile_tab.replace_mapping(new)
    profile = win._profile_tab.profile()
    assert profile.all_mappings(0)[0].action.type == "media"
    win.close()
    qapp.processEvents()


def test_profile_editor_removes_mapping(qapp):  # type: ignore[no-untyped-def]
    win = MainWindow(app=None)
    win._profile_tab.remove_mapping("pad1")
    assert all(m.id != "pad1" for m in win._profile_tab.profile().all_mappings(0))
    win.close()
    qapp.processEvents()


def test_profile_editor_switches_layer(qapp):  # type: ignore[no-untyped-def]
    win = MainWindow(app=None)
    profile = win._profile_tab.profile()
    profile.layers[1] = Layer(
        name="Shift",
        mappings=[
            Mapping(
                id="shift_pad1",
                input=InputSpec(control="note:60"),
                action=MediaAction(key="play_pause"),
            )
        ],
    )
    win._profile_tab.set_profile(profile)
    # The layer combo should now have 2 entries
    assert win._profile_tab._layer_combo.count() == 2
    # Switch to layer 1
    win._profile_tab._layer_combo.setCurrentIndex(1)
    qapp.processEvents()
    # The model should now show only shift_pad1
    model = win._profile_tab._binding_list.model()
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0)) == "shift_pad1"
    win.close()
    qapp.processEvents()


def test_profile_editor_layer_operations_and_runtime_sync(qapp):  # type: ignore[no-untyped-def]
    """Layer mutations update both the visible editor and the live engine."""
    from unittest.mock import MagicMock, patch

    with patch("pynput.keyboard.Controller") as controller:
        controller.return_value = MagicMock()
        runtime = App(_profile(), dry_run=True, auto_connect=False)
        win = MainWindow(app=runtime)
        editor = win._profile_tab

        layer_idx = editor.add_layer("Shift")
        assert layer_idx == 1
        assert editor.selected_layer_idx() == 1
        assert runtime.engine.profile is editor.profile()

        assert editor.rename_layer(layer_idx, "Fn") is True
        assert editor.profile().layers[layer_idx].name == "Fn"

        assert editor.set_default_layer(layer_idx) is True
        assert editor.profile().default_layer == layer_idx

        assert editor.set_hold_to_activate(layer_idx, True) is True
        assert editor.profile().layers[layer_idx].hold_to_activate is True

        editor.add_mapping(
            Mapping(
                id="fn_pad",
                input=InputSpec(control="note:63"),
                action=KeyboardAction(keys=["f"]),
            )
        )
        assert [m.id for m in editor.profile().layers[layer_idx].mappings] == ["fn_pad"]

        runtime.engine._active_layers.add(layer_idx)
        assert editor.delete_layer(layer_idx) is True
        assert layer_idx not in editor.profile().layers
        assert editor.profile().default_layer == 0
        assert layer_idx not in runtime.engine.active_layers
        assert runtime.engine.profile is editor.profile()

        assert editor.delete_layer(0) is False
        assert 0 in editor.profile().layers
        win.close()
        runtime.stop()
        qapp.processEvents()


def test_main_window_loads_profile_and_starts_watcher(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    p.write_text(json.dumps(_profile().model_dump(mode="json")))
    win = MainWindow(app=None)
    ok = win.load_profile_file(p)
    assert ok is True
    assert win._watcher is not None
    assert win._profile_tab.profile().name == "Untitled"
    win.close()
    qapp.processEvents()


def test_main_window_reload_via_watcher(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    p.write_text(json.dumps(_profile().model_dump(mode="json")))
    win = MainWindow(app=None)
    win.load_profile_file(p)
    # Rewrite the file with a different name to trigger a reload
    new = Profile(name="Renamed", layers=_profile().layers)
    time.sleep(0.05)
    p.write_text(json.dumps(new.model_dump(mode="json")))
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.02)
    assert win._profile_tab.profile().name == "Renamed"
    win.close()
    qapp.processEvents()


def test_main_window_save_profile_overwrites_file(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    """A round-trip: write the in-memory profile back to disk."""
    from unittest.mock import MagicMock, patch

    with patch("pynput.keyboard.Controller") as kc:
        kc.return_value = MagicMock()
        # Use a full App so save_profile() can pull .profile from it.
        p = tmp_path / "p.json"
        p.write_text(json.dumps(_profile().model_dump(mode="json")))
        profile = _profile()
        runtime = App(profile, dry_run=True, auto_connect=False)
        win = MainWindow(app=runtime)
        win.load_profile_file(p)
        # Modify the profile via the editor
        win._profile_tab.add_mapping(
            Mapping(
                id="extra",
                input=InputSpec(control="note:64"),
                action=KeyboardAction(keys=["a"]),
            )
        )
        win._on_save_profile()
        # Read the file back
        loaded = json.loads(p.read_text())
        names = [m["id"] for layer in loaded["layers"].values() for m in layer["mappings"]]
        assert "extra" in names
        win.close()
        runtime.stop()
        qapp.processEvents()


def test_watcher_emits_reload_signal_on_external_change(tmp_path: Path, qapp):  # type: ignore[no-untyped-def]
    p = tmp_path / "p.json"
    p.write_text(json.dumps(_profile().model_dump(mode="json")))
    w = ProfileWatcher(p)
    seen: list = []
    w.profile_reloaded.connect(seen.append)
    p.write_text(
        json.dumps(Profile(name="Another", layers=_profile().layers).model_dump(mode="json"))
    )
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.02)
    assert any(r.profile is not None and r.profile.name == "Another" and r.changed for r in seen)
