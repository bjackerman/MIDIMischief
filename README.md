# MIDIMischief

> Cross-platform desktop app that maps USB MIDI controllers and USB
> HID devices to keyboard shortcuts, OS-level actions, and user-defined
> scripts. Free, open-source, no DAW or proprietary drivers required.
> The Python package is still imported as `midimap` (shorter, ergonomic
> CLI command). The project is published as **MIDIMischief**.

[![Tests](https://img.shields.io/badge/tests-245%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

## What it does

- Reads MIDI notes / CCs / velocity / pressure from any controller your
  OS exposes (Maschine, Akai MPD / MPK, Arturia, Launchpad, Korg
  nanoKONTROL, etc.)
- Reads HID reports from gamepads, macro pads, custom boards, and the
  Logitech POP Icon Keys (boot protocol). Add a YAML descriptor for
  any other device.
- Maps each event to a **keyboard combo**, **media key** (play/pause,
  volume, etc.), **OS action** (launch app, open URL, system volume),
  **shell command** (with template substitution like `$value` and
  `$control`), or **Python plugin** (entry-point discovered).
- Layers, hold-to-activate, value-range bands, and press-duration
  filters for granular control.
- JSON or YAML profiles; CLI validate / diff / export / import.
- Qt (PySide6) GUI editor with live event monitor, learn mode,
  and a profile hot-reload that survives bad edits.

## Milestone status

All six milestones shipped:

| | | | |
|--|--|--|--|
| M1 | done | MIDI input + live monitor CLI | [commit `f3c3901`](https://github.com/bjackerman/MIDIMischief/commit/f3c3901) |
| M2 | done | Mapping engine + keyboard output | [commit `6914df9`](https://github.com/bjackerman/MIDIMischief/commit/6914df9) |
| M3 | done | Scripts, builtins, media, templates, safety | [commit `29649d4`](https://github.com/bjackerman/MIDIMischief/commit/29649d4) |
| M4 | done | PySide6 GUI editor | [commit `3b5dfee`](https://github.com/bjackerman/MIDIMischief/commit/3b5dfee) |
| M5 | done | Profile hot-reload, validate/diff/export, edit-existing | [commit `5457984`](https://github.com/bjackerman/MIDIMischief/commit/5457984) |
| M6 | done | HID + descriptors + plugins + auto-start | [commit `b8faa7a`](https://github.com/bjackerman/MIDIMischief/commit/b8faa7a) |
| M6.5 | done | Bind from live event (right-click) | [commit `37dcac5`](https://github.com/bjackerman/MIDIMischief/commit/37dcac5) |

**245 tests pass, ruff clean.** See [CHANGELOG.md](./CHANGELOG.md) for
the full list of features per milestone.

## Quick start

```bash
# from D:\hermes\midimap (or wherever you cloned)
python -m pip install -e ".[all,dev]"

# list MIDI devices
python -m midimap monitor --list

# list HID devices
python -c "import hid; [print(d) for d in hid.enumerate()]"

# run a profile headless
python -m midimap run --profile tests/fixtures/sample_profile.json --dry-run

# validate a profile
python -m midimap validate tests/fixtures/sample_profile.json

# diff two profiles
python -m midimap diff tests/fixtures/sample_profile.json tests/fixtures/sample_profile.yaml

# convert JSON <-> YAML
python -m midimap export tests/fixtures/sample_profile.json /tmp/out.yaml
python -m midimap import /tmp/out.yaml /tmp/out.json

# launch the GUI
python -m midimap gui
# or open a profile at launch:
python -m midimap gui --profile tests/fixtures/sample_profile.json
```

## Profile example

```json
{
  "version": 1,
  "name": "Maschine Mikro — Default",
  "device_match": {"kind": "midi", "name_contains": "Maschine Mikro"},
  "default_layer": 0,
  "layers": {
    "0": {
      "name": "Default",
      "mappings": [
        {
          "id": "pad1",
          "input": {"control": "note:60", "event": "press"},
          "action": {"type": "keyboard", "keys": ["ctrl", "1"]}
        },
        {
          "id": "knob1_high",
          "input": {"control": "cc:1", "event": "change", "value_min": 86},
          "action": {"type": "script", "command": ["logger", "$value"], "timeout_s": 5.0}
        }
      ]
    }
  }
}
```

## Platform-specific setup

- **Windows 11** — no extra setup. Run `python -m midimap gui`.
- **macOS** — first time a HID device is read the OS will pop a
  permission dialog. Approve it. MIDI works without setup.
- **Linux** — non-root users need a udev rule for raw HID access. One
  example for a specific device (replace `vid`/`pid` with the values
  from `hid.enumerate()`):
  ```
  # /etc/udev/rules.d/99-midimap.rules
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="b38f", MODE="0660", TAG+="uaccess"
  ```
  Then `sudo udevadm control --reload && sudo udevadm trigger`.

## Project layout

```
src/midimap/
  __init__.py            # version
  __main__.py            # python -m midimap
  app.py                 # App: wires DeviceManager -> bus -> engine -> executor
  events.py              # NormalizedEvent, EventType, Value
  event_bus.py           # pub/sub with per-subscriber queues
  logging_setup.py
  cli/                   # argparse entry, monitor, run, gui, validate, diff, export, import
  devices/
    manager.py           # DeviceManager (MIDI + HID)
    midi_normalizer.py
    hid_manager.py       # HIDDeviceManager
    hid_normalizer.py    # boot-keyboard + generic layouts
    descriptors.py       # YAML/JSON device descriptors
    builtin_descriptors/descriptors.yaml
  actions/               # Action, ActionExecutor, keyboard, media, builtin, script, plugin, template
  mapping/engine.py
  profile/               # schema (pydantic v2), store, diff, watcher
  plugins/registry.py    # entry-point discovery
  autostart.py           # per-OS auto-start
  gui/                   # PySide6: main_window, 4 tabs, dialogs, widgets
tests/                   # 245 tests, fully self-contained, headless-safe
```

## License

[MIT](./LICENSE). See [CONTRIBUTING.md](./CONTRIBUTING.md) for the
contribution guide and the [full design plan][plan] for the
architecture rationale.

[plan]: C:\Users\bjack\.hermes\plans\2026-07-19_105037-midicontroller-desktop-app.md

