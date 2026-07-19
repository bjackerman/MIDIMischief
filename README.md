# midimap

Cross-platform desktop app that maps USB MIDI controllers and USB HID
devices to keyboard shortcuts, OS-level actions, and user-defined
scripts.

- **M1 (done):** MIDI input + live event log via CLI.
- **M2 (done):** Mapping engine (JSON/YAML profile) + keyboard output
  via `pynput`.
- **M3 (done):** Script runner, OS built-ins (volume, media, launch
  app, open URL), media keys, template substitution (`$value` etc.),
  safety controls.
- **M4 (done):** Qt (PySide6) GUI editor — main window, 4 tabs
  (Devices, Profile, Event Log, Settings), binding wizard, Learn Mode.
- **M5 (done):** Profile hot-reload, validate/diff/export/import
  CLI, edit-existing bindings, tray "hide to tray", packaging notes.
- **M6 (now):** HID backend (`hidapi`) + device descriptors +
  plugin registry + auto-start.

**Goal complete.**

## Quick start

```bash
# from D:\hermes\midimap
python -m pip install -e ".[dev,gui]"

# list MIDI devices
python -m midimap monitor --list

# listen for events from any device containing "ATM SQ"
python -m midimap monitor --device "ATM SQ"

# run a profile headless
python -m midimap run --profile tests/fixtures/sample_profile.json --dry-run

# validate a profile
python -m midimap validate tests/fixtures/sample_profile.json

# diff two profiles (exit 1 if no changes by default)
python -m midimap diff a.json b.json

# convert between JSON and YAML
python -m midimap export sample.json sample.yaml
python -m midimap import sample.yaml sample.json

# launch the GUI
python -m midimap gui
# or open a profile at launch:
python -m midimap gui --profile tests/fixtures/sample_profile.json

# list HID devices (M6)
python -c "import hid; [print(d['product_string'], d['vendor_id'], d['product_id']) for d in hid.enumerate()]"
```

The full design lives at
`C:\Users\bjack\.hermes\plans\2026-07-19_105037-midicontroller-desktop-app.md`.

## Layout

```
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
