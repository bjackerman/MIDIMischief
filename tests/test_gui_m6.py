"""Tests for the M6 GUI additions: settings tab (autostart + plugins)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from midimap.gui.tabs.settings import SettingsTab
from midimap.plugins import get_registry, reset_registry
from midimap.profile.schema import Profile


def test_settings_tab_shows_autostart_checkbox(qapp):  # type: ignore[no-untyped-def]
    tab = SettingsTab(Profile())
    assert tab._auto_start.text().startswith("Start with the operating system")
    # The checkbox state must reflect the current autostart state
    # (we don't assume on/off; just that the construction didn't crash)
    assert isinstance(tab._auto_start.isChecked(), bool)
    tab.deleteLater()
    qapp.processEvents()


def test_settings_tab_plugin_list_empty(qapp):  # type: ignore[no-untyped-def]
    reset_registry()
    tab = SettingsTab(Profile())
    tab._refresh_plugins()
    assert tab._plugin_list.count() == 1  # placeholder item
    assert "no plugins" in tab._plugin_list.item(0).text()
    tab.deleteLater()
    qapp.processEvents()


def test_settings_tab_plugin_list_after_register(qapp):  # type: ignore[no-untyped-def]
    reset_registry()
    r = get_registry()

    def my_plugin(text: str = "x") -> str:
        return text

    r._register("my_plugin", my_plugin)
    tab = SettingsTab(Profile())
    tab._refresh_plugins()
    # One entry per registered plugin
    items = [
        tab._plugin_list.item(i).text()
        for i in range(tab._plugin_list.count())
    ]
    assert any("my_plugin" in t for t in items)
    tab.deleteLater()
    qapp.processEvents()


def test_autostart_enable_then_disable_roundtrip(qapp, monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """On Linux, enable creates a .desktop file; disable removes it."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    import midimap.autostart as autostart_mod

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(autostart_mod.platform, "system", lambda: "linux")
        assert autostart_mod.is_enabled() is False
        assert autostart_mod.enable() is True
        assert autostart_mod.is_enabled() is True
        assert autostart_mod.disable() is True
        assert autostart_mod.is_enabled() is False
