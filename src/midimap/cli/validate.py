"""``midimap validate`` — load and validate a profile, print a summary."""

from __future__ import annotations

import argparse

from ..logging_setup import configure as configure_logging
from ..profile import Profile, load_profile


def _summarise(profile: Profile) -> str:
    out: list[str] = []
    out.append(f"profile: {profile.name}")
    if profile.description:
        out.append(f"  description: {profile.description}")
    if profile.device_match.kind or profile.device_match.name_contains:
        out.append(
            f"  device_match: kind={profile.device_match.kind!r} "
            f"name_contains={profile.device_match.name_contains!r}"
        )
    out.append(f"  layers: {len(profile.layers)}")
    for idx, layer in sorted(profile.layers.items()):
        active = " (default)" if idx == profile.default_layer else ""
        out.append(f"    [{idx}] {layer.name} — {len(layer.mappings)} mapping(s){active}")
    out.append(f"  global_settings: {profile.global_settings or '{}'}")
    return "\n".join(out)


def run(args: argparse.Namespace) -> int:
    configure_logging(args.log_level)
    try:
        profile = load_profile(args.profile)
    except Exception as e:
        print(f"FAIL: {e}", flush=True)
        return 1
    print(_summarise(profile))
    if args.json:
        import json

        print(json.dumps(profile.model_dump(mode="json"), indent=2, default=str))
    return 0


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "validate",
        help="Load + validate a profile and print a summary",
    )
    p.add_argument("profile", help="Path to a profile file (.json or .yaml)")
    p.add_argument(
        "--json",
        action="store_true",
        help="Also print the full profile as JSON to stdout",
    )
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: WARNING)",
    )
    p.set_defaults(func=run)
