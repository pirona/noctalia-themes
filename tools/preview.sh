#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Capture the themed desktop as <theme>/preview.webp, without the bar. Apply the theme first. Niri only.
#   CROP_BAR=64 (physical px of bar to drop, on the edge the bar is set to)
#   tools/preview.sh themes/vaporwave
set -euo pipefail

theme="${1:?usage: tools/preview.sh themes/<name>}"
[[ -f "$theme/theme.toml" ]] || { echo "not a theme: $theme" >&2; exit 1; }
for cmd in niri grim magick; do command -v "$cmd" >/dev/null || { echo "missing: $cmd" >&2; exit 1; }; done

shot="$(mktemp --suffix=.png)"
output="$(niri msg --json focused-output | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

# niri always keeps an empty workspace last: a huge index lands there, windows stay out of the shot.
niri msg action focus-workspace 255
trap 'niri msg action focus-workspace-previous; rm -f "$shot"' EXIT  # always bring the user back
sleep 1.5  # let the workspace animation finish
grim -o "$output" "$shot"

# Drop the bar (network name, IPs…) on whichever edge it sits, then crop back to 16:9: the preview lives in the repo.
crop="${CROP_BAR:-64}"
side="$(noctalia msg config-get bar 2>/dev/null | python3 -c 'import sys,tomllib
print(tomllib.loads(sys.stdin.read()).get("default",{}).get("position","top"))' || echo top)"  # merged config: the theme's fragment counts
case "$side" in  # keep the edge opposite the bar
    top) cut="x$(( $(magick identify -format %h "$shot") - crop ))+0+0"; keep="south" ;;
    bottom) cut="x$(( $(magick identify -format %h "$shot") - crop ))+0+0"; keep="north" ;;
    left) cut="$(( $(magick identify -format %w "$shot") - crop ))x+0+0"; keep="east" ;;
    *) cut="$(( $(magick identify -format %w "$shot") - crop ))x+0+0"; keep="west" ;;
esac
magick "$shot" -gravity "$keep" -crop "$cut" +repage \
    -resize 640x360^ -gravity center -extent 640x360 -quality 85 "$theme/preview.webp"
echo "preview: $theme/preview.webp"
