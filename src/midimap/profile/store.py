"""Load and save profiles in JSON or YAML.

Both formats round-trip through the same ``Profile`` model. JSON is the
default (unambiguous, no comment stripping). YAML is friendlier for
hand-editing; we also accept JSON-with-comments and strip them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml

from .schema import Profile, _strip_json_comments

ProfileFormat = Literal["json", "yaml"]


class ProfileLoadError(ValueError):
    """Raised when a profile can't be parsed or validated.

    The message includes the underlying pydantic/yaml error path so the
    GUI can show "Import errors" with "go to field" buttons later.
    """


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _parse_text(text: str, *, format: str | None = None) -> dict[str, Any]:
    if format == "json":
        try:
            return json.loads(_strip_json_comments(text))
        except json.JSONDecodeError as e:
            raise ProfileLoadError(f"JSON parse error: {e.msg} (line {e.lineno})") from e
    if format == "yaml":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ProfileLoadError(f"YAML parse error: {e}") from e
        if not isinstance(data, dict):
            raise ProfileLoadError("YAML root must be a mapping")
        return data
    # Auto-detect: try JSON first (cheap and unambiguous), then YAML.
    try:
        return json.loads(_strip_json_comments(text))
    except json.JSONDecodeError:
        pass
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ProfileLoadError(f"profile is not valid JSON or YAML: {e}") from e
    if not isinstance(data, dict):
        raise ProfileLoadError("profile root must be a mapping")
    return data


def load_profile(path: str | Path) -> Profile:
    """Load a profile from disk. Format is auto-detected by extension
    (``.json`` → JSON, otherwise YAML) with a JSON-first sniff.
    """
    p = Path(path)
    if not p.exists():
        raise ProfileLoadError(f"profile not found: {p}")
    text = p.read_text(encoding="utf-8")
    ext = p.suffix.lower()
    fmt: str | None
    if ext == ".json":
        fmt = "json"
    elif ext in (".yaml", ".yml"):
        fmt = "yaml"
    else:
        fmt = None
    data = _parse_text(text, format=fmt)
    try:
        return Profile.model_validate(data)
    except Exception as e:
        # pydantic ValidationError carries structured info; re-raise as our type
        raise ProfileLoadError(f"profile validation failed: {e}") from e


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def save_profile(
    profile: Profile, path: str | Path, *, format: str | None = None
) -> None:
    """Write a profile to disk. ``format`` defaults to extension."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = profile.model_dump(mode="json")  # JSON-safe (no tuples, etc.)
    if format is None:
        ext = p.suffix.lower()
        if ext == ".json":
            format = "json"
        elif ext in (".yaml", ".yml"):
            format = "yaml"
        else:
            format = "json"  # default

    if format == "json":
        p.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    elif format == "yaml":
        p.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    else:
        raise ValueError(f"unknown format: {format!r}")
