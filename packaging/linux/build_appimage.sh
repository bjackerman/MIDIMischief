#!/usr/bin/env bash
# Build an AppImage from the PyInstaller executable. Requires appimagetool.
set -euo pipefail

version="${VERSION:-0.1.0}"
dist_dir="${DIST_DIR:-dist}"
appdir="$dist_dir/AppDir"
source_bin="$dist_dir/MIDIMischief"

[[ -x "$source_bin" ]] || { echo "Missing $source_bin; run PyInstaller first." >&2; exit 1; }
rm -rf "$appdir"
install -d "$appdir/usr/bin" "$appdir/usr/share/applications"
install -m 0755 "$source_bin" "$appdir/usr/bin/MIDIMischief"
install -m 0644 "packaging/linux/MIDIMischief.desktop" "$appdir/MIDIMischief.desktop"
install -m 0644 "packaging/linux/MIDIMischief.desktop" "$appdir/usr/share/applications/MIDIMischief.desktop"
cat > "$appdir/AppRun" <<'APP_RUN'
#!/bin/sh
exec "$(dirname "$0")/usr/bin/MIDIMischief" gui "$@"
APP_RUN
chmod +x "$appdir/AppRun"
appimagetool --appimage-extract-and-run "$appdir" \
  "$dist_dir/MIDIMischief-${version}-linux-x86_64.AppImage"
