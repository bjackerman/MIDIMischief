"""Profile schema."""

from __future__ import annotations

from .diff import LayerDiff, MappingChange, ProfileDiff, diff, diff_to_dict
from .schema import (
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
    load_profile_text,
)
from .store import ProfileLoadError, load_profile, save_profile
from .watcher import ProfileWatcher, ReloadResult

__all__ = [
    "BuiltinAction",
    "DeviceMatch",
    "InputSpec",
    "KeyboardAction",
    "Layer",
    "LayerDiff",
    "Mapping",
    "MappingChange",
    "MediaAction",
    "PluginAction",
    "Profile",
    "ProfileDiff",
    "ProfileLoadError",
    "ProfileWatcher",
    "ReloadResult",
    "ScriptAction",
    "diff",
    "diff_to_dict",
    "load_profile",
    "load_profile_text",
    "save_profile",
]
