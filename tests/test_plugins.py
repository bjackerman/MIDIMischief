"""Tests for the plugin registry and the PluginAction executor."""

from __future__ import annotations

from typing import Any

from midimap.actions.plugin import run_plugin
from midimap.plugins import PluginRegistry, get_registry, reset_registry


def test_registry_starts_empty():
    reset_registry()
    r = PluginRegistry()
    r.load()
    # No entry points installed in the test env
    assert r.names() == []


def test_registry_register_then_get():
    r = PluginRegistry()

    def hello(text: str = "world", *, event: Any = None) -> str:
        return f"hello {text} event={event}"

    r._register("hello", hello)
    spec = r.get("hello")
    assert spec is not None
    assert spec.name == "hello"
    assert spec.signature.parameters.keys() == {"text", "event"}


def test_plugin_spec_call_passes_event_when_accepted():
    r = PluginRegistry()

    def plugin(text: str = "x", *, event=None) -> dict:
        return {"text": text, "event": event}

    r._register("p", plugin)
    spec = r.get("p")
    result = spec.call(args={"text": "y"}, event={"foo": 1})
    assert result == {"text": "y", "event": {"foo": 1}}


def test_plugin_spec_call_omits_event_when_not_accepted():
    r = PluginRegistry()

    def plugin(value: int) -> int:
        return value * 2

    r._register("p2", plugin)
    spec = r.get("p2")
    assert spec.call(args={"value": 21}) == 42


def test_registry_skips_uncallable():
    r = PluginRegistry()
    r._register("not_callable", 42)
    r._register("also_bad", "string")
    assert r.names() == []


def test_get_registry_returns_singleton():
    reset_registry()
    a = get_registry()
    b = get_registry()
    assert a is b


def test_run_plugin_dry_run(monkeypatch):
    reset_registry()
    r = get_registry()

    def plugin(value: int = 0) -> int:
        return value

    r._register("dry", plugin)
    # Even without dry-run, plugin returns 0 which is falsy.
    # dry_run should log + return True without calling.
    assert run_plugin("dry", {"value": 5}, dry_run=True) is True


def test_run_plugin_missing_returns_false():
    reset_registry()
    assert run_plugin("does_not_exist", {}) is False


def test_run_plugin_exception_returns_false():
    reset_registry()
    r = get_registry()

    def boom() -> bool:
        raise RuntimeError("nope")

    r._register("boom", boom)
    assert run_plugin("boom", {}) is False


def test_run_plugin_calls_with_event_kwarg():
    reset_registry()
    r = get_registry()
    seen: dict = {}

    def cap(*, event: Any) -> bool:
        seen["event"] = event
        return True

    r._register("cap", cap)
    assert run_plugin("cap", {}, event={"control": "note:60"}) is True
    assert seen["event"] == {"control": "note:60"}


def test_registry_load_is_idempotent():
    reset_registry()
    r = get_registry()
    r.load()
    r.load()  # second call is a no-op
    # No error
