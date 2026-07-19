"""``python -m midimap`` entry point."""

from __future__ import annotations

import argparse

from .. import __version__
from . import gui, monitor, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midimap",
        description="Cross-platform MIDI/HID controller mapper.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")
    monitor.add_subparser(sub)
    run.add_subparser(sub)
    gui.add_subparser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
