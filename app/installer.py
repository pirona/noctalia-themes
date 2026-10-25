# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply / roll back Noctalia themes. Every apply snapshots first; rollback restores bytes exactly."""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import palette

log = logging.getLogger("noctalia-themes")


def _home(var, xdg, default):
    return Path(os.environ.get(var) or os.environ.get(xdg) or Path.home() / default)


CONFIG = _home("NOCTALIA_CONFIG_HOME", "XDG_CONFIG_HOME", ".config") / "noctalia"
STATE = _home("NOCTALIA_STATE_HOME", "XDG_STATE_HOME", ".local/state") / "noctalia" / "settings.toml"
DATA = _home("NOCTALIA_THEMES_HOME", "XDG_DATA_HOME", ".local/share") / "noctalia-themes"
BACKUPS = DATA / "backups"
FRAGMENT = CONFIG / "zz-theme.toml"
CURRENT = DATA / "current"
# Tables the theme owns entirely: their state overrides are dropped as a whole.
OWNED_TABLES = ("desktop_widgets",)


def list_themes(root):
    themes = []
    for d in sorted(Path(root).glob("*/theme.toml")):
        meta = tomllib.loads(d.read_text())
        meta["dir"] = d.parent
        themes.append(meta)
    return themes


def list_backups():
    out = []
    for d in sorted(BACKUPS.glob("*/manifest.json")):
        m = json.loads(d.read_text())
        m["id"] = d.parent.name
        out.append(m)
    return out


def _leaf_keys(table, prefix=()):
    for k, v in table.items():
        if isinstance(v, dict):
            yield from _leaf_keys(v, prefix + (k,))
        else:
            yield prefix + (k,)


def _header(line):
    s = line.strip()
    if not s.startswith("["):
        return None
    return tuple(p.strip().strip('"') for p in s.strip("[]").split("."))


def _bracket_delta(text):
    depth, quote = 0, None
    for ch in text:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    return depth


def strip_overrides(state_text, fragment):
    """Drop from state every key the fragment sets, plus whole owned tables. Line-based to keep the rest untouched."""
    drop_keys = {k for k in _leaf_keys(fragment) if k[0] not in OWNED_TABLES}
    owned = [t for t in OWNED_TABLES if t in fragment]
    out, table, skipping_value, skipping_table = [], (), 0, False
    for line in state_text.splitlines(keepends=True):
        if skipping_value:
            skipping_value += _bracket_delta(line)
            continue
        h = _header(line)
        if h is not None:
            table = h
            skipping_table = bool(h) and h[0] in owned
        if skipping_table:
            continue
        if h is None and "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip().strip('"')
            if table + (key,) in drop_keys:
                skipping_value = _bracket_delta(line.split("=", 1)[1])
                continue
        out.append(line)
    result = "".join(out)
    tomllib.loads(result)  # refuse to write anything Noctalia could not parse
    return result


def _reload():
    # Files are hot-reloaded anyway; this only makes it immediate.
    try:
        subprocess.run(["noctalia", "msg", "config-reload"], check=False, capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _atomic_copy(src, dst):
    # Noctalia watches these files: never let it read a half-written one.
    tmp = Path(dst).with_name(Path(dst).name + ".tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


def current():
    """Backup id of the theme currently applied, or None."""
    return CURRENT.read_text().strip() if CURRENT.exists() else None


def current_theme():
    """Manifest of the applied theme, or None."""
    bid = current()
    return next((b for b in list_backups() if b["id"] == bid), None)


def validate(theme_dir):
    """Raise ValueError if the theme is broken; nothing is touched before this passes."""
    theme_dir = Path(theme_dir)
    errors = palette.check(theme_dir / "palette.json")
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    for key in ("name", "palette"):
        if key not in meta:
            errors.append(f"theme.toml: missing '{key}'")
    # The palette name becomes a file name: keep it from escaping palettes/.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(meta.get("palette", ""))):
        errors.append("theme.toml: 'palette' must match [A-Za-z0-9_-]+")
    tomllib.loads((theme_dir / "noctalia.toml").read_text())
    if errors:
        raise ValueError("\n".join(errors))


def apply(theme_dir, label=None):
    theme_dir = Path(theme_dir).resolve()
    validate(theme_dir)
    if current():
        rollback(current())  # snapshot must capture the untouched user state, not a themed one
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bdir = BACKUPS / stamp
    bdir.mkdir(parents=True)

    installed = DATA / "themes" / theme_dir.name
    palette_dst = CONFIG / "palettes" / f"{meta['palette']}.json"
    targets = [palette_dst, FRAGMENT]
    manifest = {"theme": meta["name"], "date": stamp, "label": label or f"Avant « {meta['name']} »",
                "state_existed": STATE.exists(), "files": {}}
    # Snapshot first, before anything is written.
    if STATE.exists():
        shutil.copy2(STATE, bdir / "settings.toml")
    for i, t in enumerate(targets):
        saved = None
        if t.exists():
            saved = f"file{i}"
            shutil.copy2(t, bdir / saved)
        manifest["files"][str(t)] = saved
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    try:
        if installed.exists():
            shutil.rmtree(installed)
        shutil.copytree(theme_dir, installed, ignore=shutil.ignore_patterns("SOURCES.md", "*.py", "__pycache__"))
        fragment_text = (theme_dir / "noctalia.toml").read_text().replace("@THEME_DIR@", str(installed))
        fragment = tomllib.loads(fragment_text)
        stripped = strip_overrides(STATE.read_text(), fragment) if STATE.exists() else None
        palette_dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(theme_dir / "palette.json", palette_dst)
        (bdir / "fragment.toml").write_text(fragment_text)
        _atomic_copy(bdir / "fragment.toml", FRAGMENT)
        if stripped is not None:
            # ponytail: no lock with Noctalia; a write it makes between our read and replace is lost (sub-second window)
            (bdir / "stripped.toml").write_text(stripped)
            _atomic_copy(bdir / "stripped.toml", STATE)
        CURRENT.write_text(stamp)
    except Exception:
        rollback(stamp)  # leave the user exactly where they were
        raise
    log.info("applied theme %s (backup %s)", meta["name"], stamp)
    _reload()
    return stamp


def rollback(backup_id):
    if current() and current() != backup_id:
        rollback(current())  # remove the active theme cleanly before going further back
    bdir = BACKUPS / backup_id
    manifest = json.loads((bdir / "manifest.json").read_text())
    for path, saved in manifest["files"].items():
        p = Path(path)
        if saved:
            _atomic_copy(bdir / saved, p)
        elif p.exists():
            p.unlink()  # created by the theme, not there before
    if manifest["state_existed"]:
        _atomic_copy(bdir / "settings.toml", STATE)
    CURRENT.unlink(missing_ok=True)  # every backup is a theme-free state
    log.info("restored backup %s", backup_id)
    _reload()


if __name__ == "__main__":
    cmd = sys.argv[1:2] or ["list"]
    if cmd == ["apply"]:
        print(apply(sys.argv[2]))
    elif cmd == ["rollback"]:
        rollback(sys.argv[2])
        print("restored", sys.argv[2])
    else:
        for b in list_backups():
            print(b["id"], b["label"])
