# GitHub deltas: 2026-07-20 (corrected)

## TL;DR — the first draft of this doc was wrong

I originally read the situation as "remote has 17 commits that need
merging" and predicted 14 conflict sites. **Both were wrong.** When
I actually opened a worktree at origin/master and tried `git merge
master`, the answer was: "Already up to date." My local `master`
(`7dcd087`) is a direct ancestor of origin/master (`ee344d9`). All
my local commits are already in remote history; the 17 "new" commits
are simply the work that happened *on top of* my last push.

The correct action was a **fast-forward**, not a merge. Local `master`
is now at `ee344d9` (the new origin/master HEAD). 264/264 tests
pass, ruff clean.

## What really happened

| Time | Event | State |
|---|---|---|
| 2026-07-19 19:32 | I pushed v0.1.0 (tag at `9a1ff83`) | local + remote in sync |
| 2026-07-19 20:?? – 2026-07-20 ??:?? | Someone (you, or codex automation, or both) opened 9 PRs branching from `7dcd087` and merged them all back | remote is `ee344d9`, 17 commits ahead |
| 2026-07-20 14:23 | I noticed remote was ahead | I wrote DELTAS.md predicting conflicts |
| 2026-07-20 14:24 | I created a worktree, tried the merge, discovered fast-forward | This doc |

## The 8 PRs (all merged, in remote order)

| # | What | Closes one of my "known gaps"? |
|---|---|---|
| **#1** | **Add descriptor-driven device render widget** (`gui/widgets/device_render.py` 216 LOC + 84 LOC of tests) | ✅ Yes — gap #1 closed |
| **#2** | **Implement MIDI hotplug reconciliation** (real loop, not the stub) | ✅ Yes — hotplug was a no-op in v0.1.0 |
| #3 | Add profile editor layer controls (add/rename/delete buttons) | — |
| #4 | Preserve bindings when editing action details | — |
| #5 | **Remove unsupported `quit_app` builtin** (I shipped a stub) | — |
| #6 | **Track HID device connection state** (my `is_connected()` returned `False` for HID) | ✅ Correctness fix |
| #7 | **Add bundled HID device descriptors** (split `descriptors.yaml` into per-category files: `gamepads`, `macro_pads`, `midi_adjacent`, `controller_boards`) | — |
| **#9** | **Add cross-platform desktop packaging** (PyInstaller spec + NSIS + .desktop + DMG + AppImage + CI workflow) | ✅ Yes — gap #2 closed |

(The numbering skips #10 — likely a closed/abandoned PR.)

## What actually changed (post-merge file diff)

```
.github/workflows/package.yml                      |  73 +++++
CONTRIBUTING.md                                    | 113 ++++++++-
README.md                                          |  59 ++++-
midimap.spec                                       |  82 ++++++++
packaging/launcher.py                              |   6 +
packaging/linux/MIDIMischief.desktop               |   7 +
packaging/linux/build_appimage.sh                  |  22 +++
packaging/macos/create_dmg.sh                      |  16 ++
packaging/macos/sign_and_notarize.sh               |  21 ++
packaging/windows/MIDIMischief.nsi                 |  43 +++
pyproject.toml                                     |   7 +
src/midimap/actions/builtin.py                     |  15 +-
src/midimap/app.py                                 |   7 +-
src/midimap/devices/builtin_descriptors/*.yaml     |  +/-
src/midimap/devices/descriptors.py                 |  41 +/-
src/midimap/devices/hid_manager.py                 |  24 +-
src/midimap/devices/manager.py                     | 106 ++++++-
src/midimap/gui/dialogs/bind_control.py            | 150 ++++++-
src/midimap/gui/main_window.py                     |  28 +-
src/midimap/gui/tabs/devices.py                    |  32 +-
src/midimap/gui/tabs/profile_editor.py             | 164 ++++++-
src/midimap/gui/widgets/device_render.py           | 216 +++++++++++ (NEW)
src/midimap/profile/schema.py                      |  16 +-
tests/fixtures/builtin_hid_reports.yaml            |  50 +++++
tests/test_builtin.py                              |  14 +-
tests/test_device_manager.py                       | 109 +++++
tests/test_device_render.py                        |  84 ++++++ (NEW)
tests/test_gui_dialogs.py                          |  57 +++-
tests/test_gui_m5.py                               |  56 +++-
tests/test_hid.py                                  |  47 +++
tests/test_hid_manager.py                          |  14 +
tests/test_profile_schema.py                       |   9 +
```

Net: **+1720 / −133 across 37 files, 19 new tests pass (245 → 264).**

## Status of the v0.1.0 README's "Known gaps" claims

| Claim in README | Still true? | Action needed |
|---|---|---|
| "Visual device render widget is missing" | ❌ NO — PR #1 ships `device_render.py` | Update README to remove this gap |
| "Cross-platform packaging is not built" | ❌ NO — PR #9 ships the full pipeline + CI | Update README |
| "MIDI hotplug reconciliation" (the M1 stub) | ❌ NO — PR #2 ships the real loop | Update README |
| `quit_app` is a stub returning `False` | ❌ NO — PR #5 deletes it entirely | Update README (if it mentioned quit_app) |
| `is_connected(device_id)` returns `False` for HID | ❌ NO — PR #6 makes it real | (README didn't claim this; no action) |

Three of the "known gaps" I documented in the v0.1.0 README are
**closed** by the post-v0.1.0 PRs. The README is now wrong on three
counts.

## Tag policy

`v0.1.0` is at `9a1ff83` (Switch owner: bjack → bjackerman). It is
still reachable from `master` but is no longer at the tip.

| Option | Pro | Con |
|---|---|---|
| A. Leave `v0.1.0` where it is, cut `v0.2.0` at `ee344d9` | Clean; the v0.1.0 GitHub Release is honest about what shipped at v0.1.0 time | Two releases; users on `pip install` need to bump |
| B. Move `v0.1.0` to `ee344d9` (delete the v0.1.0 GitHub Release, re-cut it from master) | One release; everyone gets everything at `v0.1.0` | The v0.1.0 GitHub Release is a lie (the original v0.1.0 didn't include the new code) |
| C. Keep `v0.1.0` as-is, never tag a `v0.2.0`, develop on master | "We don't tag" is honest | Loses a checkpoint |

**Recommended: A.** Cut `v0.2.0` at `ee344d9`. Document the gap-closure
in the v0.2.0 release notes. Update the README's "Known gaps" to
match the v0.2.0 reality.

## My next steps (proposed, in order)

1. **Update README** to remove the three now-closed gaps.
2. **Update CHANGELOG** with a new `[0.2.0]` section summarizing the
   8 PRs.
3. **Cut tag `v0.2.0`** at `ee344d9`, push it.
4. **Re-run tests** — already 264/264 green.
5. **Smoke-test the packaging** locally (or at least dry-run
   `pyinstaller midimap.spec --noconfirm` to verify the spec is
   valid; actually building a Windows installer requires running
   on Windows + NSIS installed, which is doable on this host).

Say the word and I'll do 1–4 in one turn.
