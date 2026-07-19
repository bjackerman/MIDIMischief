# midimap

Cross-platform desktop app that maps USB MIDI controllers and USB HID devices to keyboard shortcuts, OS-level actions, and user-defined scripts.

- **M1 (now):** MIDI input + live event log via CLI.
- **M2:** Mapping engine (JSON profile) → keyboard output via `pynput`.
- **M3:** Scripts, OS built-ins (volume, media, launch app), safety controls.
- **M4:** Qt (PySide6) GUI editor with live device render and Learn Mode.
- **M5:** Profile import/export, polish, OS packaging.
- **M6:** HID (raw reports) + plugin registry.

## Quick start (M1)

```bash
# from D:\hermes\midimap
python -m pip install -e ".[dev]"

# list MIDI devices
python -m midimap monitor --list

# listen for events from any device containing "ATM SQ"
python -m midimap monitor --device "ATM SQ"
```

The full design is in `.hermes/plans/2026-07-19_105037-midicontroller-desktop-app.md`.

## Layout

```
src/midimap/
  __init__.py          # version
  logging_setup.py
  events.py            # NormalizedEvent, EventType
  event_bus.py
  devices/
    manager.py         # DeviceManager
    midi_normalizer.py
  cli/
    main.py            # argparse entry
    monitor.py         # M1 headless monitor
tests/
  test_midi_normalizer.py
  test_event_bus.py
```
