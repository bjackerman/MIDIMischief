#!/usr/bin/env bash
# Optional release signing. Required env: APPLE_SIGNING_IDENTITY,
# APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD. Run after create_dmg.sh.
set -euo pipefail

version="${VERSION:-0.1.0}"
dist_dir="${DIST_DIR:-dist}"
app="$dist_dir/MIDIMischief.app"
dmg="$dist_dir/MIDIMischief-${version}-macos.dmg"
: "${APPLE_SIGNING_IDENTITY:?Set APPLE_SIGNING_IDENTITY}"

codesign --force --deep --options runtime --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$app"
codesign --verify --deep --strict --verbose=2 "$app"
[[ -f "$dmg" ]] || "$(dirname "$0")/create_dmg.sh"
codesign --force --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$dmg"

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
  xcrun notarytool submit "$dmg" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" --wait
  xcrun stapler staple "$dmg"
fi
