#!/usr/bin/env bash
# Create a distributable DMG from the PyInstaller app bundle.
set -euo pipefail

version="${VERSION:-0.1.0}"
dist_dir="${DIST_DIR:-dist}"
app="$dist_dir/MIDIMischief.app"
stage="${TMPDIR:-/tmp}/MIDIMischief-dmg"

[[ -d "$app" ]] || { echo "Missing $app; run PyInstaller first." >&2; exit 1; }
rm -rf "$stage"
mkdir -p "$stage"
cp -R "$app" "$stage/"
ln -s /Applications "$stage/Applications"
hdiutil create -volname "MIDIMischief" -srcfolder "$stage" -ov -format UDZO \
  "$dist_dir/MIDIMischief-${version}-macos.dmg"
