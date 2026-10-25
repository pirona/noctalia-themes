#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Capture the themed desktop as <theme>/preview.webp, without the top bar. Apply the theme first. Niri only.
#   CROP_TOP=64 (physical px to drop at the top)
#   tools/preview.sh themes/vaporwave
set -euo pipefail

theme="${1:?usage: tools/preview.sh themes/<name>}"
[[ -f "$theme/theme.toml" ]] || { echo "pas un thème : $theme" >&2; exit 1; }
for cmd in niri grim magick; do command -v "$cmd" >/dev/null || { echo "manque : $cmd" >&2; exit 1; }; done

shot="$(mktemp --suffix=.png)"
output="$(niri msg --json focused-output | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

# niri always keeps an empty workspace last: a huge index lands there, windows stay out of the shot.
niri msg action focus-workspace 255
trap 'niri msg action focus-workspace-previous; rm -f "$shot"' EXIT  # always bring the user back
sleep 1.5  # let the workspace animation finish
grim -o "$output" "$shot"

# Drop the top bar (network name, IPs…) then crop back to 16:9: the preview lives in the repo.
crop_top="${CROP_TOP:-64}"
magick "$shot" -gravity south -crop "x$(( $(magick identify -format %h "$shot") - crop_top ))+0+0" +repage \
    -resize 640x360^ -gravity center -extent 640x360 -quality 85 "$theme/preview.webp"
echo "aperçu : $theme/preview.webp"
