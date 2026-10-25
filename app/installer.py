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

import options
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
# Loaded after zz-theme.toml (alphabetical), so the app preferences win over the theme.
OPTIONS = CONFIG / "zzz-theme-options.toml"
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


def _toml_escape(value):
    # Placeholders sit inside "..." basic strings; JSON escaping is valid TOML there.
    return json.dumps(str(value))[1:-1]


def detect_output():
    """Connector the widgets go to: override, else niri's focused output, else the first wlr output."""
    if os.environ.get("NOCTALIA_THEMES_OUTPUT"):
        return os.environ["NOCTALIA_THEMES_OUTPUT"]
    if options.load()["output"]:
        return options.load()["output"]
    for cmd, pick in ((["niri", "msg", "--json", "focused-output"], lambda o: o["name"]),
                      (["wlr-randr", "--json"], lambda o: next(x["name"] for x in o if x.get("enabled")))):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout
            return pick(json.loads(out))
        except (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError, StopIteration):
            continue
    raise ValueError("Aucun écran détecté (ni niri ni wlr-randr). Définis NOCTALIA_THEMES_OUTPUT, ex. eDP-1.")


def _flatten(table, prefix=""):
    out = {}
    for k, v in table.items():
        key = f"{prefix}{k}"
        out.update(_flatten(v, key + ".") if isinstance(v, dict) else {key: v})
    return out


# Written by Noctalia itself on every wallpaper change: not a user setting.
NOISE_PREFIXES = ("wallpaper.last.",)
UNREADABLE = "(configuration illisible : impossible de vérifier ce qui serait perdu)"


def changes_since_apply():
    """Settings changed in Noctalia while the theme was active; they are lost on removal."""
    bid = current()
    written = BACKUPS / str(bid) / "stripped.toml"
    if not bid or not written.exists() or not STATE.exists():
        return []
    try:
        before = _flatten(tomllib.loads(written.read_text()))
        now = _flatten(tomllib.loads(STATE.read_text()))
        theme = _flatten(tomllib.loads(FRAGMENT.read_text())) if FRAGMENT.exists() else {}
        theme |= _flatten(tomllib.loads(OPTIONS.read_text())) if OPTIONS.exists() else {}
    except (OSError, tomllib.TOMLDecodeError):
        return [UNREADABLE]  # warn rather than block the way back
    changed = {k for k in before.keys() | now.keys() if before.get(k) != now.get(k)}
    # A theme value echoed back into state by Noctalia is not a user change.
    return sorted(k for k in changed if not k.startswith(NOISE_PREFIXES) and now.get(k) != theme.get(k, object()))


def list_outputs():
    """Connected output names, for the screen picker. Empty if neither niri nor wlr-randr answers."""
    for cmd, names in ((["niri", "msg", "--json", "outputs"], lambda o: sorted(o)),
                       (["wlr-randr", "--json"], lambda o: [x["name"] for x in o if x.get("enabled")])):
        try:
            return names(json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout))
        except (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError):
            continue
    return []


def wallpapers(theme_dir):
    """Wallpapers of a theme, from its installed copy when there is one (stable path for Noctalia)."""
    installed = DATA / "themes" / Path(theme_dir).name / "wallpapers"
    folder = installed if installed.is_dir() else Path(theme_dir) / "wallpapers"
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in (".webp", ".png", ".jpg", ".jpeg", ".avif"))


def set_wallpaper(path):
    """Set the wallpaper through Noctalia's IPC (it persists the choice in settings.toml itself)."""
    subprocess.run(["noctalia", "msg", "wallpaper-set", str(path)], check=True, capture_output=True, timeout=10)
    log.info("wallpaper set to %s", path)


def write_options(fragment=None, reload=True):
    """Write the preferences fragment for the active theme (or remove it when it changes nothing).

    `fragment` is the theme fragment the options apply to; by default the installed one.
    """
    if fragment is None:
        if not current() or not FRAGMENT.exists():
            return
        fragment = tomllib.loads(FRAGMENT.read_text())
    text = options.dump(options.overrides(fragment, options.load()))
    if not text.strip():
        OPTIONS.unlink(missing_ok=True)
    else:
        tomllib.loads(text)
        tmp = DATA / "options.tmp.toml"
        tmp.write_text("# Written by the Noctalia Themes app: preferences layered over the theme.\n" + text)
        _atomic_copy(tmp, OPTIONS)
        tmp.unlink()
    if reload:
        _reload()


def overridden_by_state():
    """Preference keys that settings.toml overrides anyway (it is loaded last and wins)."""
    if not OPTIONS.exists() or not STATE.exists():
        return []
    try:
        mine = _flatten(tomllib.loads(OPTIONS.read_text()))
        state = _flatten(tomllib.loads(STATE.read_text()))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return sorted(k for k in mine if k in state and state[k] != mine[k])


def excess_backups(keep):
    """Oldest backups beyond `keep`, never the one of the active theme (its only way back)."""
    ids = [b["id"] for b in list_backups() if b["id"] != current()]
    room = max(keep - (1 if current() else 0), 0)
    return ids[:max(len(ids) - room, 0)]


def delete_backup(backup_id):
    if backup_id == current():
        raise ValueError("Cette sauvegarde est le seul retour possible pour le thème actif : retire le thème d'abord.")
    shutil.rmtree(BACKUPS / backup_id)
    log.info("deleted backup %s", backup_id)


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


def _render(theme_dir, output):
    """Copy the theme to its installed place and return its fragment with placeholders filled."""
    installed = DATA / "themes" / theme_dir.name
    if installed.exists():
        shutil.rmtree(installed)
    shutil.copytree(theme_dir, installed, ignore=shutil.ignore_patterns("SOURCES.md", "*.py", "__pycache__"))
    text = (theme_dir / "noctalia.toml").read_text().replace("@THEME_DIR@", _toml_escape(installed))
    return text.replace("@OUTPUT@", _toml_escape(output)) if output else text


def refresh(theme_dir):
    """Update the active theme's files in place (stickers, palette, fragment).

    The user's settings.toml and the backups are left untouched, so settings changed
    since the theme was applied survive; keys they override keep winning over the theme.
    """
    theme_dir = Path(theme_dir).resolve()
    validate(theme_dir)
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    active = current_theme()
    if not active or active["theme"] != meta["name"]:
        raise ValueError(f"« {meta['name']} » n'est pas le thème actif : utilise apply.")
    output = detect_output() if "@OUTPUT@" in (theme_dir / "noctalia.toml").read_text() else None
    text = _render(theme_dir, output)
    fragment = tomllib.loads(text)
    tmp = DATA / "fragment.refresh.toml"
    tmp.write_text(text)
    _atomic_copy(theme_dir / "palette.json", CONFIG / "palettes" / f"{meta['palette']}.json")
    write_options(fragment, reload=False)  # options first: Noctalia never sees new fragment + stale options
    _atomic_copy(tmp, FRAGMENT)
    tmp.unlink()
    log.info("refreshed theme %s", meta["name"])
    _reload()


def apply(theme_dir, label=None):
    theme_dir = Path(theme_dir).resolve()
    validate(theme_dir)
    output = detect_output() if "@OUTPUT@" in (theme_dir / "noctalia.toml").read_text() else None
    if current():
        rollback(current())  # snapshot must capture the untouched user state, not a themed one
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bdir = BACKUPS / stamp
    bdir.mkdir(parents=True)

    palette_dst = CONFIG / "palettes" / f"{meta['palette']}.json"
    targets = [palette_dst, FRAGMENT, OPTIONS]
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
        fragment_text = _render(theme_dir, output)
        fragment = tomllib.loads(fragment_text)
        stripped = strip_overrides(STATE.read_text(), fragment) if STATE.exists() else None
        palette_dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(theme_dir / "palette.json", palette_dst)
        write_options(fragment, reload=False)
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
    if str(OPTIONS) not in manifest["files"]:
        OPTIONS.unlink(missing_ok=True)  # backups made before preferences existed don't list it
    if manifest["state_existed"]:
        _atomic_copy(bdir / "settings.toml", STATE)
    CURRENT.unlink(missing_ok=True)  # every backup is a theme-free state
    log.info("restored backup %s", backup_id)
    _reload()


if __name__ == "__main__":
    cmd = sys.argv[1:2] or ["list"]
    if cmd == ["apply"]:
        print(apply(sys.argv[2]))
    elif cmd == ["refresh"]:
        refresh(sys.argv[2])
        print("refreshed", sys.argv[2])
    elif cmd == ["rollback"]:
        rollback(sys.argv[2])
        print("restored", sys.argv[2])
    else:
        for b in list_backups():
            print(b["id"], b["label"])
