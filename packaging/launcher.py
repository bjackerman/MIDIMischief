"""PyInstaller entry point for the MIDIMischief command-line and GUI app."""

from midimap.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
