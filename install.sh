#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install the Noctalia Themes launcher for the current user. Idempotent; never uses sudo.
#   ./install.sh              install / update the desktop entry
#   ./install.sh --uninstall  remove the desktop entry (themes and backups are kept)
set -euo pipefail

APP_ID="fr.gyozamancave.NoctaliaThemes"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP_ID.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$DESKTOP"
    echo "Entrée retirée : $DESKTOP (sauvegardes conservées dans ~/.local/share/noctalia-themes/)"
    exit 0
fi

missing=()
for pkg in python3-gobject gtk4 libadwaita; do
    rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    echo "Dépendances manquantes. Lance :"
    echo "  sudo dnf install ${missing[*]}"
    exit 1
fi

mkdir -p "$(dirname "$DESKTOP")"
cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Thèmes Noctalia
Comment=Appliquer et retirer des thèmes Noctalia, avec retour arrière
Exec=python3 $REPO/app/main.py
Icon=preferences-desktop-theme
Terminal=false
Categories=Settings;DesktopSettings;
StartupWMClass=$APP_ID
EOF
desktop-file-validate "$DESKTOP"
echo "Installé : $DESKTOP"
echo "Lance « Thèmes Noctalia » depuis le lanceur, ou : python3 $REPO/app/main.py"
