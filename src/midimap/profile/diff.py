"""Structural diff between two Profiles.

A diff is a tree of change records:

- ProfileDiff
  - layer_diffs: dict[layer_index, LayerDiff]
  - added_layers: dict[layer_index, Layer]
  - removed_layers: dict[layer_index, Layer]
  - global_settings_changed: bool

A LayerDiff contains:
- added_mappings: dict[mapping_id, Mapping]
- removed_mappings: dict[mapping_id, Mapping]
- changed_mappings: dict[mapping_id, MappingChange]

MappingChange carries the before / after and a list of human-readable
field-level change strings.

Use :func:`diff` to compute a ProfileDiff and :meth:`ProfileDiff.summary`
to print a human-friendly summary. The text format is stable and
machine-parseable; downstream tooling can rely on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import Layer, Mapping, Profile


@dataclass
class MappingChange:
    """A single mapping that was edited."""

    before: Mapping
    after: Mapping
    field_changes: list[str] = field(default_factory=list)


@dataclass
class LayerDiff:
    added_mappings: dict[str, Mapping] = field(default_factory=dict)
    removed_mappings: dict[str, Mapping] = field(default_factory=dict)
    changed_mappings: dict[str, MappingChange] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.added_mappings or self.removed_mappings or self.changed_mappings)


@dataclass
class ProfileDiff:
    layer_diffs: dict[int, LayerDiff] = field(default_factory=dict)
    added_layers: dict[int, Layer] = field(default_factory=dict)
    removed_layers: dict[int, Layer] = field(default_factory=dict)
    global_settings_changed: bool = False

    def is_empty(self) -> bool:
        return (
            not self.layer_diffs
            and not self.added_layers
            and not self.removed_layers
            and not self.global_settings_changed
        )

    def summary(self) -> str:
        """Return a human-readable multi-line summary."""
        if self.is_empty():
            return "no changes"
        out: list[str] = []
        if self.global_settings_changed:
            out.append("global settings: changed")
        for idx, ld in sorted(self.layer_diffs.items()):
            if ld.is_empty():
                continue
            head = f"layer {idx}:"
            if ld.added_mappings:
                head += f" +{len(ld.added_mappings)}"
            if ld.removed_mappings:
                head += f" -{len(ld.removed_mappings)}"
            if ld.changed_mappings:
                head += f" ~{len(ld.changed_mappings)}"
            out.append(head)
            for mid, m in ld.added_mappings.items():
                out.append(f"  + {mid}: {m.input.control} -> {m.action.type}")
            for mid, m in ld.removed_mappings.items():
                out.append(f"  - {mid}: {m.input.control} -> {m.action.type}")
            for mid, change in ld.changed_mappings.items():
                out.append(f"  ~ {mid}: {', '.join(change.field_changes)}")
        for idx, layer in sorted(self.added_layers.items()):
            out.append(f"+ layer {idx} ({layer.name}, {len(layer.mappings)} mappings)")
        for idx, layer in sorted(self.removed_layers.items()):
            out.append(f"- layer {idx} ({layer.name}, {len(layer.mappings)} mappings)")
        return "\n".join(out)


def _mapping_field_diff(before: Mapping, after: Mapping) -> list[str]:
    """Return a list of human-readable 'field: before -> after' strings."""
    changes: list[str] = []
    if before.input != after.input:
        changes.append(f"input: {before.input.model_dump()} -> {after.input.model_dump()}")
    if before.action.type != after.action.type:
        changes.append(f"action.type: {before.action.type} -> {after.action.type}")
    elif before.action.model_dump() != after.action.model_dump():
        changes.append(f"action: {before.action.model_dump()} -> {after.action.model_dump()}")
    if (before.description or "") != (after.description or ""):
        changes.append(f"description: {before.description!r} -> {after.description!r}")
    return changes


def diff(before: Profile, after: Profile) -> ProfileDiff:
    """Compute a :class:`ProfileDiff` between two profiles."""
    result = ProfileDiff()
    if (before.global_settings or {}) != (after.global_settings or {}):
        result.global_settings_changed = True

    # Layers
    all_layer_idxs = set(before.layers) | set(after.layers)
    for idx in sorted(all_layer_idxs):
        b = before.layers.get(idx)
        a = after.layers.get(idx)
        if b is None and a is not None:
            result.added_layers[idx] = a
            continue
        if a is None and b is not None:
            result.removed_layers[idx] = b
            continue
        assert b is not None and a is not None  # for type-checkers

        ld = LayerDiff()
        b_by_id = {m.id: m for m in b.mappings}
        a_by_id = {m.id: m for m in a.mappings}
        for mid, am in a_by_id.items():
            if mid not in b_by_id:
                ld.added_mappings[mid] = am
        for mid, bm in b_by_id.items():
            if mid not in a_by_id:
                ld.removed_mappings[mid] = bm
        for mid in sorted(set(b_by_id) & set(a_by_id)):
            bm = b_by_id[mid]
            am = a_by_id[mid]
            if bm.model_dump() == am.model_dump():
                continue
            fc = _mapping_field_diff(bm, am)
            if fc:
                ld.changed_mappings[mid] = MappingChange(before=bm, after=am, field_changes=fc)
        if not ld.is_empty():
            result.layer_diffs[idx] = ld
    return result


def diff_to_dict(d: ProfileDiff) -> dict[str, Any]:
    """Serialize a ProfileDiff to a JSON-compatible dict."""
    return {
        "global_settings_changed": d.global_settings_changed,
        "added_layers": {str(i): layer.name for i, layer in d.added_layers.items()},
        "removed_layers": {str(i): layer.name for i, layer in d.removed_layers.items()},
        "layer_diffs": {
            str(i): {
                "added_mappings": list(ld.added_mappings),
                "removed_mappings": list(ld.removed_mappings),
                "changed_mappings": {
                    mid: change.field_changes for mid, change in ld.changed_mappings.items()
                },
            }
            for i, ld in d.layer_diffs.items()
        },
    }


__all__ = [
    "LayerDiff",
    "MappingChange",
    "ProfileDiff",
    "diff",
    "diff_to_dict",
]
