# midimap

> Cross-platform desktop app that maps USB MIDI controllers and USB
> HID devices to keyboard shortcuts, OS-level actions, and user-defined
> scripts. Free, open-source, no DAW or proprietary drivers required.

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
| M1 | done | MIDI input + live monitor CLI | [commit `f3c3901`](https://github.com/ctrlaltbrian/midimap/commit/f3c3901) |
| M2 | done | Mapping engine + keyboard output | [commit `6914df9`](https://github.com/ctrlaltbrian/midimap/commit/6914df9) |
| M3 | done | Scripts, builtins, media, templates, safety | [commit `29649d4`](https://github.com/ctrlaltbrian/midimap/commit/29649d4) |
| M4 | done | PySide6 GUI editor | [commit `3b5dfee`](https://github.com/ctrlaltbrian/midimap/commit/3b5dfee) |
| M5 | done | Profile hot-reload, validate/diff/export, edit-existing | [commit `5457984`](https://github.com/ctrlaltbrian/midimap/commit/5457984) |
| M6 | done | HID + descriptors + plugins + auto-start | [commit `b8faa7a`](https://github.com/ctrlaltbrian/midimap/commit/b8faa7a) |
| M6.5 | done | Bind from live event (right-click) | [commit `37dcac5`](https://github.com/ctrlaltbrian/midimap/commit/37dcac5) |

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

src/midimap/
  __init__.py            # version
  logging_setup.py
  events.py              # NormalizedEvent, EventType, Value
  event_bus.py           # pub/sub with drop-oldest per-subscriber queues
  app.py                 # App: DeviceManager -> EventBus -> Engine -> Executor
  actions/
    __init__.py          # Action, ActionExecutor dispatcher
    template.py          # $value/$control/$device/... substitution
    keyboard.py          # pynput wrapper, dry_run
    media.py             # MediaKeySender (Win/mac/Linux)
    builtin.py           # launch_app, open_url, volume_*
    script.py            # ScriptRunner (subprocess, timeout, MIDIMAP_EVENT)
  cli/
    main.py              # argparse entry
    monitor.py           # M1 headless monitor
    run.py               # M2-M3 headless run
    gui.py               # M4 Qt entry
    validate.py          # M5 validate subcommand
    diff.py              # M5 diff subcommand
    export_import.py     # M5 export/import subcommands
  devices/
    manager.py         # DeviceManager (MIDI + HID)
    midi_normalizer.py
    hid_manager.py      # HIDDeviceManager (M6)
    hid_normalizer.py   # HID boot-keyboard + generic (M6)
    descriptors.py      # YAML/JSON device descriptors (M6)
    builtin_descriptors/descriptors.yaml  # Shipped defaults (M6)
  actions/
    __init__.py          # Action, ActionExecutor dispatcher
    template.py          # $value/$control/$device/... substitution
    keyboard.py          # pynput wrapper, dry_run
    media.py             # MediaKeySender (Win/mac/Linux)
    builtin.py           # launch_app, open_url, volume_*
    script.py            # ScriptRunner (subprocess, timeout, MIDIMAP_EVENT)
    plugin.py            # PluginAction (M6)
  plugins/
    registry.py          # entry-point discovery (M6)
  autostart.py           # per-OS login auto-start (M6)
  events.py
  event_bus.py
  mapping/
    engine.py            # MappingEngine: layers, value range, press duration
  profile/
    schema.py            # pydantic v2: Profile/Layer/Mapping/Action union
    store.py             # JSON+YAML load/save
    diff.py              # structural diff
    watcher.py           # QFileSystemWatcher + reload signal
  gui/
    app.py               # QApplication + single-instance lock
    main_window.py       # QMainWindow + QTabWidget + menubar
    qt_bridge.py         # EventBusQtBridge: any-thread -> Qt signal
    tabs/
      devices.py         # Devices + Live Monitor
      profile_editor.py  # Profile editor
      event_log.py       # Event log (logging.Handler bridge)
      settings.py        # Global toggles
    widgets/
      event_table.py     # model/view for live events
      binding_list.py    # Profile bindings list
    dialogs/
      bind_control.py    # 3-page binding wizard
      learn_mode.py      # Learn-mode dialog
tests/
  fixtures/sample_profile.json
  fixtures/sample_profile.yaml
  fixtures/bad_profile.json
  test_*                 # 165 tests across all layers
```

## Status

```
194 tests pass, ruff clean, 3 platform-skipped.
```
