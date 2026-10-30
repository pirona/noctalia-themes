# SPDX-License-Identifier: GPL-3.0-or-later
"""Every path the app reads or writes, in one place.

Each base directory follows the XDG spec and can be overridden (tests run in a sandbox this way):
  NOCTALIA_CONFIG_HOME   instead of XDG_CONFIG_HOME, for Noctalia's config   (~/.config/noctalia)
  NOCTALIA_STATE_HOME    instead of XDG_STATE_HOME,  for Noctalia's state    (~/.local/state/noctalia)
  NOCTALIA_DATA_HOME     instead of XDG_DATA_HOME,   for Noctalia's local plugins (~/.local/share/noctalia/plugins)
  NOCTALIA_THEMES_HOME   instead of XDG_DATA_HOME,   for installed themes and backups (~/.local/share/noctalia-themes)
  NOCTALIA_THEMES_FONTS  instead of XDG_DATA_HOME,   for theme fonts         (~/.local/share/fonts/noctalia-themes)
  NOCTALIA_THEMES_CONFIG instead of XDG_CONFIG_HOME, for app preferences     (~/.config/noctalia-themes)
Nothing is created at import: callers create what they write with ensure_dir().
"""
import os
import subprocess
from pathlib import Path


def _base(override, xdg, default):
    return Path(os.environ.get(override) or os.environ.get(xdg) or Path.home() / default)


ROOT = Path(__file__).resolve().parent.parent
THEMES = ROOT / "themes"  # themes shipped with the app
PLUGINS = ROOT / "plugins"  # Noctalia plugins shipped with the app, installed when a theme uses them
LOCALE = ROOT / "app" / "locale"  # compiled translations (install.sh builds them from po/)

# Noctalia's files. It loads its defaults, then config/*.toml in alphabetical order, then state (wins over all).
CONFIG = _base("NOCTALIA_CONFIG_HOME", "XDG_CONFIG_HOME", ".config") / "noctalia"
PALETTES = CONFIG / "palettes"
FRAGMENT = CONFIG / "zz-theme.toml"  # the active theme
OPTIONS = CONFIG / "zzz-theme-options.toml"  # app preferences: loaded after the theme, so they win over it
NOCTALIA_PLUGINS = _base("NOCTALIA_DATA_HOME", "XDG_DATA_HOME", ".local/share") / "noctalia" / "plugins"
STATE = _base("NOCTALIA_STATE_HOME", "XDG_STATE_HOME", ".local/state") / "noctalia" / "settings.toml"

# The app's own files. DATA holds copies of settings.toml (which may carry tokens): private.
DATA = _base("NOCTALIA_THEMES_HOME", "XDG_DATA_HOME", ".local/share") / "noctalia-themes"
INSTALLED = DATA / "themes"  # stable copy of the active theme, referenced by Noctalia
BACKUPS = DATA / "backups"
CURRENT = DATA / "current"  # backup id of the applied theme
GLUE = DATA / "glue.json"  # widget positions at the last glue pass
LOG = DATA / "app.log"
# Widgets name fonts by family: fontconfig must see them, so they go to the user font dir.
FONTS = _base("NOCTALIA_THEMES_FONTS", "XDG_DATA_HOME", ".local/share") / "fonts" / "noctalia-themes"
SETTINGS = _base("NOCTALIA_THEMES_CONFIG", "XDG_CONFIG_HOME", ".config") / "noctalia-themes" / "settings.json"

PRIVATE = (DATA, SETTINGS.parent)


def ensure_dir(path):
    """Create `path` if needed; the app's own folders are owner-only (0700), Noctalia's keep the umask."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    root = next((p for p in PRIVATE if p == path or p in path.parents), None)
    if root:
        root.chmod(0o700)  # a 0700 root protects everything below; also tightens one made by an older version
    return path


def pictures():
    """The user's pictures folder (xdg-user-dir), for the wallpaper tools."""
    try:
        out = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return Path(out) if out and out != str(Path.home()) else Path.home() / "Pictures"
