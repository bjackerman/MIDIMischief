"""Pydantic v2 schema for midimap profiles.

A ``Profile`` is the user-authored mapping document. JSON and YAML are
both supported. The schema is the contract; the store and engine code
treat it as canonical.

The M2 subset is intentionally narrow:

- ``device_match`` (broad: name substring, vid:pid, kind)
- ``layers`` (0..N, with a default layer 0)
- ``mappings`` (one per (input, action) rule; last rule wins per event)
- Actions: keyboard, media, builtin, script, plugin (stubs for the
  non-keyboard types in M2; they become real in M3).

M3/M5 will extend this with: ``hold_to_activate`` layers, per-script
``risky`` flag, per-mapping ``min_press_ms``/``max_press_ms``, and
``$value`` template substitution.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Input side
# ---------------------------------------------------------------------------


class DeviceMatch(BaseModel):
    """Substring/identifier match used to pick a profile for a device.

    All fields are AND-ed. Omit all fields to mean "match any device"
    (useful for global scripts and the default profile).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["midi", "hid"] | None = None
    name_contains: str | None = None
    vid_pid: str | None = None  # e.g. "17cc:1700"

    def matches(self, device: dict[str, Any]) -> bool:
        if self.kind is not None and device.get("kind") != self.kind:
            return False
        if self.name_contains is not None and self.name_contains.lower() not in str(
            device.get("name", "")
        ).lower():
            return False
        return not (
            self.vid_pid is not None
            and str(device.get("vid_pid", "")).lower() != self.vid_pid.lower()
        )


class InputSpec(BaseModel):
    """What a Mapping listens for.

    ``control`` is a normalised id like ``"note:60"`` or ``"cc:7"``. See
    :mod:`midimap.devices.midi_normalizer` for the format.
    """

    model_config = ConfigDict(extra="forbid")

    control: str
    event: Literal["press", "release", "change", "tap"] | None = None
    channel: int | None = Field(default=None, ge=1, le=16)
    value_min: int | None = Field(default=None, ge=0, le=16383)
    value_max: int | None = Field(default=None, ge=0, le=16383)
    # Press-duration matching (release only):
    min_press_ms: int | None = Field(default=None, ge=0)
    max_press_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _value_range_valid(self) -> InputSpec:
        if (
            self.value_min is not None
            and self.value_max is not None
            and self.value_min > self.value_max
        ):
            raise ValueError("value_min must be <= value_max")
        if (
            self.min_press_ms is not None
            and self.max_press_ms is not None
            and self.min_press_ms > self.max_press_ms
        ):
            raise ValueError("min_press_ms must be <= max_press_ms")
        return self


# ---------------------------------------------------------------------------
# Action side (discriminated union by ``type``)
# ---------------------------------------------------------------------------


class _ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeyboardAction(_ActionBase):
    """Send a key combination via pynput.

    ``keys`` is a list in human-friendly form:
        ["ctrl", "shift", "k"]   -> Ctrl+Shift+K
        ["F5"]                    -> F5
        ["a"]                     -> lowercase 'a'
    Order is not significant for modifiers.
    """

    type: Literal["keyboard"] = "keyboard"
    keys: list[str] = Field(min_length=1)

    @field_validator("keys")
    @classmethod
    def _normalise_keys(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for k in v:
            k = k.strip()
            if not k:
                continue
            out.append(k.lower())
        if not out:
            raise ValueError("keys must contain at least one non-empty entry")
        return out


class MediaAction(_ActionBase):
    """Send a media key (play/pause, next, vol+…). Implemented in M3."""

    type: Literal["media"] = "media"
    key: Literal[
        "play_pause", "next", "prev", "stop", "volume_up", "volume_down", "mute"
    ]


class BuiltinAction(_ActionBase):
    """A supported built-in OS action.

    Target-process termination is intentionally not a built-in action.  Use a
    ``ScriptAction`` with ``risky=True`` for that explicit, reviewable choice.
    """

    type: Literal["builtin"] = "builtin"
    name: Literal[
        "launch_app",
        "open_url",
        "volume_up",
        "volume_down",
        "volume_mute",
        "volume_set",
        "noop",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class ScriptAction(_ActionBase):
    """Spawn a subprocess. ``shell=False`` — args are passed as a list.

    The user must consciously opt-in to scripts; this is the most
    security-sensitive action type. The runner enforces timeouts, the
    ``risky`` flag triggers a confirm dialog, and ``disable_scripts`` in
    global settings can hard-disable all script actions.
    """

    type: Literal["script"] = "script"
    command: list[str] = Field(min_length=1)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = Field(default=30.0, gt=0)
    risky: bool = False


class PluginAction(_ActionBase):
    """An action provided by a third-party ``midimap.actions`` entry point.

    The plugin is looked up at action-execution time by ``name`` and
    invoked with ``params`` and the triggering event. Plugins are loaded
    in M6.
    """

    type: Literal["plugin"] = "plugin"
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


# Discriminated union — pydantic v2 picks the right variant by ``type``.
Action = Annotated[
    KeyboardAction | MediaAction | BuiltinAction | ScriptAction | PluginAction,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Mapping + Layer
# ---------------------------------------------------------------------------


class Mapping(BaseModel):
    """One rule: when ``input`` matches, run ``action``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    input: InputSpec
    action: Action
    description: str | None = None


class Layer(BaseModel):
    """A named, optional layer. Layer 0 is always active.

    ``hold_to_activate`` is the M3 "shift" behaviour: holding the first
    mapping's control in the layer keeps the layer active. In M2 we
    parse it but don't yet implement the hold-tracking (it lives in
    MappingEngine's ``_update_layers``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = "Layer"
    hold_to_activate: bool = False
    mappings: list[Mapping] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class Profile(BaseModel):
    """The root document."""

    model_config = ConfigDict(extra="forbid")

    # Schema version. Bump on any incompatible change.
    version: Literal[1] = 1
    name: str = "Untitled"
    description: str | None = None

    device_match: DeviceMatch = Field(default_factory=DeviceMatch)
    layers: dict[int, Layer] = Field(default_factory=dict)
    default_layer: int = 0
    global_settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_layer_zero(self) -> Profile:
        if not self.layers:
            # Provide a default empty layer 0 so the engine never has to
            # special-case "no layers".
            self.layers = {0: Layer(name="Default")}
        if 0 not in self.layers:
            raise ValueError("layers must include key 0 (the default layer)")
        # Ensure layer keys are non-negative ints.
        for k in self.layers:
            if not isinstance(k, int) or k < 0:
                raise ValueError(f"layer key must be a non-negative int, got {k!r}")
        return self

    def all_mappings(self, layer_idx: int) -> list[Mapping]:
        layer = self.layers.get(layer_idx)
        if layer is None:
            return []
        return list(layer.mappings)

    def matches_device(self, device: dict[str, Any]) -> bool:
        return self.device_match.matches(device)

    @property
    def disable_scripts(self) -> bool:
        """Read ``global_settings.disable_scripts`` as a typed bool.

        The ``global_settings`` field is a free-form dict in the schema
        (so users can stash arbitrary app-level knobs without bumping
        the version), but a few well-known keys have typed accessors.
        """
        return bool(self.global_settings.get("disable_scripts", False))

    @property
    def confirm_risky(self) -> bool:
        return bool(self.global_settings.get("confirm_risky", True))


# ---------------------------------------------------------------------------
# Loader helpers (used by store.py and tests)
# ---------------------------------------------------------------------------


# Strip // and # line comments from YAML/JSON-with-comments input. We only
# use this for YAML; JSON strictly does not allow comments, but many users
# hand-edit .json files and add them.
_LINE_COMMENT = re.compile(r"(^|\s)(//|#).*$")


def _strip_json_comments(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = _LINE_COMMENT.sub("", line)
        # also strip trailing comma on the last value of an object/array
        out_lines.append(stripped)
    return "\n".join(out_lines)


def load_profile_text(text: str, *, format: str | None = None) -> Profile:
    """Parse a profile from a string.

    ``format`` is ``"json"`` or ``"yaml"``. If omitted, we try JSON first
    (because it's stricter and unambiguous) and fall back to YAML.
    """
    from .store import _parse_text  # local import to avoid a cycle

    data = _parse_text(text, format=format)
    return Profile.model_validate(data)
