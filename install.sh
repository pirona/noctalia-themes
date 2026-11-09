#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install Noctalia Themes for the current user. Idempotent; never uses sudo.
#   ./install.sh              check dependencies, copy the app to ~/.local, add launcher, icon and AppStream entry
#   ./install.sh --uninstall  remove all of that (backups, imported themes and preferences are kept)
set -euo pipefail

APP_ID="com.billisdead.NoctaliaThemes"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$SHARE/noctalia-themes/app"  # next to the backups (DATA); the repository can move or go once installed
BIN="$HOME/.local/bin/noctalia-themes"
DESKTOP="$SHARE/applications/$APP_ID.desktop"
ICON="$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg"
METAINFO="$SHARE/metainfo/$APP_ID.metainfo.xml"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$DESKTOP" "$ICON" "$METAINFO" "$BIN"
    rm -rf "${DEST:?}"
    echo "Removed the app. Kept: backups, imported themes ($SHARE/noctalia-themes/) and preferences."
    echo "A theme still applied stays applied: remove it from the app first if you want your desktop back."
    exit 0
fi

# Check what the app imports rather than package names: they differ between distributions.
if ! python3 - 2>/dev/null <<'EOF'
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
# Adw.AboutDialog needs libadwaita 1.5, CssProvider.load_from_string GTK 4.12.
sys.exit(0 if sys.version_info >= (3, 11) and Gtk.get_minor_version() >= 12 and Adw.get_minor_version() >= 5 else 1)
EOF
then
    echo "Missing dependencies: Python 3.11+, PyGObject, GTK 4.12+, libadwaita 1.5+. For example:"
    echo "  Fedora:        sudo dnf install python3-gobject gtk4 libadwaita"
    echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
    echo "  Arch:          sudo pacman -S python-gobject gtk4 libadwaita"
    exit 1
fi

# Optional tools: the app runs without them, with less.
warn() { echo "Note: $*"; }
if command -v noctalia >/dev/null; then
    ver="$(noctalia --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 || true)"
    if [[ -z "$ver" ]] || ! printf '5.3\n%s\n' "$ver" | sort -VC; then
        warn "Noctalia ${ver:-of unknown version} found; the themes are made for 5.3 or later."
    fi
else
    warn "noctalia not found: install Noctalia v5 (https://docs.noctalia.dev/noctalia/) to apply themes."
fi
command -v playerctl >/dev/null || warn "playerctl not found: the themes' music player stays empty (package 'playerctl')."
if command -v noctalia-greeter >/dev/null && ! command -v pkexec >/dev/null; then
    warn "pkexec (polkit) not found: the login screen can't follow the theme."
fi

# Translations: optional, the app falls back to English without them.
if command -v msgfmt >/dev/null; then
    for po in "$REPO"/po/*.po; do
        lang="$(basename "$po" .po)"
        mkdir -p "$REPO/app/locale/$lang/LC_MESSAGES"
        msgfmt -o "$REPO/app/locale/$lang/LC_MESSAGES/noctalia-themes.mo" "$po"
    done
else
    warn "msgfmt (gettext) not found: the app will be in English."
fi

# Copy to a fresh folder, then swap: a running copy of the app never sees half an update.
mkdir -p "$(dirname "$DEST")"
chmod 700 "$(dirname "$DEST")"  # holds the backups too (copies of settings.toml): owner only, as the app does
rm -rf "${DEST:?}.new" "${DEST:?}.old"
mkdir "$DEST.new"
tar -C "$REPO" --exclude=__pycache__ -cf - app data plugins themes LICENSE | tar -C "$DEST.new" -xf -
[[ -d "$DEST" ]] && mv "$DEST" "$DEST.old"
mv "$DEST.new" "$DEST"
rm -rf "${DEST:?}.old"

mkdir -p "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")" "$(dirname "$METAINFO")"
printf '#!/bin/sh\nexec python3 "%s/app/main.py" "$@"\n' "$DEST" >"$BIN"
chmod 755 "$BIN"
cp "$REPO/data/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICON"
cp "$REPO/data/$APP_ID.metainfo.xml" "$METAINFO"
cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Noctalia Themes
Name[fr]=Thèmes Noctalia
Comment=Apply and remove Noctalia themes, with rollback
Comment[fr]=Appliquer et retirer des thèmes Noctalia, avec retour arrière
Exec="$BIN"
Icon=$APP_ID
Terminal=false
Categories=Settings;DesktopSettings;
Keywords=theme;wallpaper;noctalia;niri;
StartupWMClass=$APP_ID
EOF
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$DESKTOP"
fi

echo "Installed in $DEST"
echo "Start “Noctalia Themes” from the launcher, or run: noctalia-themes"
[[ ":$PATH:" == *":$HOME/.local/bin:"* ]] || warn "$HOME/.local/bin is not in PATH: use the launcher or $BIN."
