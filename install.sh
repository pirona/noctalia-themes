#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install the Noctalia Themes launcher for the current user. Idempotent; never uses sudo.
#   ./install.sh              check dependencies, build translations, install / update the desktop entry
#   ./install.sh --uninstall  remove the desktop entry (themes and backups are kept)
set -euo pipefail

APP_ID="com.billisdead.NoctaliaThemes"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP_ID.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$DESKTOP"
    echo "Removed: $DESKTOP (backups kept in ${XDG_DATA_HOME:-$HOME/.local/share}/noctalia-themes/)"
    exit 0
fi

# Check what the app imports rather than package names: they differ between distributions.
if ! python3 - 2>/dev/null <<'EOF'
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
sys.exit(0 if sys.version_info >= (3, 11) else 1)
EOF
then
    echo "Missing dependencies: Python 3.11+, PyGObject, GTK 4, libadwaita. For example:"
    echo "  Fedora:        sudo dnf install python3-gobject gtk4 libadwaita"
    echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
    echo "  Arch:          sudo pacman -S python-gobject gtk4 libadwaita"
    exit 1
fi

# Translations: optional, the app falls back to English without them.
if command -v msgfmt >/dev/null; then
    for po in "$REPO"/po/*.po; do
        lang="$(basename "$po" .po)"
        mkdir -p "$REPO/app/locale/$lang/LC_MESSAGES"
        msgfmt -o "$REPO/app/locale/$lang/LC_MESSAGES/noctalia-themes.mo" "$po"
    done
else
    echo "msgfmt (gettext) not found: the app will be in English."
fi

mkdir -p "$(dirname "$DESKTOP")"
cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Noctalia Themes
Name[fr]=Thèmes Noctalia
Comment=Apply and remove Noctalia themes, with rollback
Comment[fr]=Appliquer et retirer des thèmes Noctalia, avec retour arrière
Exec=python3 "$REPO/app/main.py"
Icon=preferences-desktop-theme
Terminal=false
Categories=Settings;DesktopSettings;
StartupWMClass=$APP_ID
EOF
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$DESKTOP"
fi
echo "Installed: $DESKTOP"
echo "Start “Noctalia Themes” from the launcher, or: python3 \"$REPO/app/main.py\""
