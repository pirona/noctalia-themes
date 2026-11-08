# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply / roll back Noctalia themes. Every apply snapshots first; removing a theme restores that snapshot
plus the settings changed in Noctalia meanwhile. A "setup" backup copies the whole Noctalia state as is."""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import options
import palette
from i18n import _, localize
from paths import (
    BACKUPS,
    CONFIG,
    CURRENT,
    DATA,
    EXPECT,
    FONTS,
    FRAGMENT,
    GLUE,
    INSTALLED,
    NOCTALIA_PLUGINS,
    OPTIONS,
    PALETTES,
    PLUGINS,
    STATE,
    WALLS,
    ensure_dir,
)

log = logging.getLogger("noctalia-themes")


# Tables the theme owns entirely: their state overrides are dropped as a whole.
OWNED_TABLES = ("desktop_widgets",)


def list_themes(root):
    themes = []
    for d in sorted(Path(root).glob("*/theme.toml")):
        meta = tomllib.loads(d.read_text())
        meta["dir"] = d.parent
        themes.append(localize(meta))
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
    raise ValueError(_("No screen found (neither niri nor wlr-randr answered). Set NOCTALIA_THEMES_OUTPUT, "
                       "e.g. eDP-1."))


def _flatten(table, prefix=""):
    out = {}
    for k, v in table.items():
        key = f"{prefix}{k}"
        out.update(_flatten(v, key + ".") if isinstance(v, dict) else {key: v})
    return out


# Written by Noctalia itself on every wallpaper change: not a user setting.
NOISE_PREFIXES = ("wallpaper.last.",)
UNREADABLE = _("(unreadable configuration: cannot check what would be lost)")
_GONE = object()  # a setting removed in Noctalia


def _flat(table, prefix=()):
    """Leaves keyed by tuple paths (dotted strings break on keys like "my.widget"); lists are leaves."""
    out = {}
    for k, v in table.items():
        out.update(_flat(v, prefix + (k,)) if isinstance(v, dict) else {prefix + (k,): v})
    return out


def _put(table, path, value):
    for k in path[:-1]:
        table = table.setdefault(k, {})
    if value is _GONE:
        table.pop(path[-1], None)
    else:
        table[path[-1]] = value


def _theme_dir_name(bdir):
    """Folder name of the theme a backup was made for, read from its installed fragment."""
    frag = bdir / "fragment.toml"
    m = re.search(re.escape(str(INSTALLED)) + r"/([A-Za-z0-9_-]+)", frag.read_text()) if frag.exists() else None
    return m.group(1) if m else None


def _user_changes(bid):
    """Settings changed in Noctalia while the theme of backup `bid` was active: ({path: value} kept, [lost]).

    Kept: everything that is yours (bar, dock, plugins...). Lost: what belongs to the theme (keys it sets,
    its widgets). A wallpaper from the theme's own folder is dropped silently: it leaves with the theme.
    """
    bdir = BACKUPS / str(bid)
    written = bdir / "stripped.toml"
    if not written.exists() or not STATE.exists():
        return {}, []
    before = _flat(tomllib.loads(written.read_text()))
    now = _flat(tomllib.loads(STATE.read_text()))
    theme = _flat(tomllib.loads((bdir / "fragment.toml").read_text())) if (bdir / "fragment.toml").exists() else {}
    if bid == current() and OPTIONS.exists():
        theme |= _flat(tomllib.loads(OPTIONS.read_text()))
    tdir = _theme_dir_name(bdir)
    kept, lost = {}, []
    for k in before.keys() | now.keys():
        v = now.get(k, _GONE)
        if before.get(k, _GONE) == v or ".".join(k).startswith(NOISE_PREFIXES):
            continue
        if isinstance(v, str) and tdir and (v.startswith(str(INSTALLED / tdir) + "/")
                                            or Path(v).parent.parts[-2:] == ("wallpapers", tdir)):
            continue
        if k[0] in OWNED_TABLES or k in theme:
            if v is not _GONE and v == theme.get(k, _GONE):
                continue  # a theme value echoed back into state by Noctalia
            lost.append(".".join(k))
        else:
            kept[k] = v
    return kept, sorted(lost)


def changes_since_apply():
    """Theme settings changed while it was active: they leave with it (yours are carried over)."""
    try:
        return _user_changes(current())[1] if current() else []
    except (OSError, tomllib.TOMLDecodeError):
        return [UNREADABLE]  # warn rather than block the way back


def kept_since_apply():
    """Your settings changed while the theme was active: carried over when it is removed."""
    try:
        return sorted(".".join(k) for k in _user_changes(current())[0]) if current() else []
    except (OSError, tomllib.TOMLDecodeError):
        return []


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
    installed = INSTALLED / Path(theme_dir).name / "wallpapers"
    folder = installed if installed.is_dir() else Path(theme_dir) / "wallpapers"
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in (".webp", ".png", ".jpg", ".jpeg", ".avif"))


def set_wallpaper(path, output=None):
    """Set the wallpaper (of one output, or all) through Noctalia's IPC; it persists the choice itself."""
    cmd = ["noctalia", "msg", "wallpaper-set", *([output] if output else []), str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=10)
    log.info("wallpaper set to %s%s", path, f" on {output}" if output else "")


def current_wallpapers():
    """{output: path} shown now ("" = all outputs when none can be listed); {} if Noctalia does not answer."""
    out = {}
    for output in list_outputs() or [""]:
        try:
            cmd = ["noctalia", "msg", "wallpaper-get", *([output] if output else [])]
            path = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if path:
            out[output] = path
    return out


def _restore_wallpapers(saved, only_from=None):
    """Put back the wallpapers recorded in a backup. With `only_from`, only on outputs showing a file from that
    folder (a theme's wallpaper leaving with it): a wallpaper you picked yourself meanwhile stays."""
    shown = current_wallpapers() if only_from else {}
    for output, path in (saved or {}).items():
        if only_from and not shown.get(output, "").startswith(str(only_from) + "/"):
            continue
        if not Path(path).is_file():
            log.warning("saved wallpaper is gone, left as is: %s", path)
            continue
        try:
            set_wallpaper(path, output or None)
        except (OSError, subprocess.SubprocessError):
            log.warning("could not restore wallpaper %s", path)  # the rest of the restore already succeeded


def _walls():
    try:
        return json.loads(WALLS.read_text())
    except (OSError, ValueError):
        return {}


def _remember_wallpaper(tdir):
    """Note the theme's wallpaper on screen as it leaves, to show it again next time."""
    shown = next((p for p in current_wallpapers().values() if p.startswith(str(INSTALLED / tdir) + "/")), None)
    if shown:
        ensure_dir(WALLS.parent)
        WALLS.write_text(json.dumps(_walls() | {tdir: shown}, indent=2))


def _show_theme_wallpaper(theme_dir):
    """The wallpaper last shown with this theme, else its first one."""
    walls = wallpapers(theme_dir)
    if not walls:
        return
    last = Path(_walls().get(theme_dir.name, ""))
    try:
        set_wallpaper(last if last in walls else walls[0])
    except (OSError, subprocess.SubprocessError):
        log.warning("could not set the theme's wallpaper")  # the theme itself is applied


def sync_greeter():
    """One explicit greeter sync, for when auto_sync can't catch the change (it leaves with the theme's options)."""
    if not (options.greeter_installed() and options.load()["greeter_sync"]):
        return
    try:  # don't wait: the helper may sit on a Polkit prompt
        subprocess.Popen(["noctalia", "msg", "greeter-sync"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        log.warning("could not start the greeter sync")


def write_options(fragment=None, reload=True):
    """Write the preferences fragment for the active theme (or remove it when it changes nothing).

    `fragment` is the theme fragment the options apply to; by default the installed one.
    """
    if fragment is None:
        if not current() or not FRAGMENT.exists():
            return
        fragment = tomllib.loads(FRAGMENT.read_text())
    text = options.dump(options.overrides(fragment, options.load(), options.greeter_installed()))
    if not text.strip():
        OPTIONS.unlink(missing_ok=True)
    else:
        tomllib.loads(text)
        tmp = ensure_dir(DATA) / "options.tmp.toml"
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
    ids = [b["id"] for b in list_backups() if b["id"] != current() and b.get("kind") != "setup"]
    room = max(keep - (1 if current() else 0), 0)
    return ids[:max(len(ids) - room, 0)]


def delete_backup(backup_id):
    if backup_id == current():
        raise ValueError(_("This backup is the only way back from the active theme: remove the theme first."))
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
    installed = ensure_dir(INSTALLED) / theme_dir.name
    if installed.exists():
        shutil.rmtree(installed)
    shutil.copytree(theme_dir, installed, ignore=shutil.ignore_patterns("SOURCES.md", "*.py", "__pycache__"))
    text = (theme_dir / "noctalia.toml").read_text().replace("@THEME_DIR@", _toml_escape(installed))
    return text.replace("@OUTPUT@", _toml_escape(output)) if output else text


def _fonts(theme_dir):
    """(source, installed) pairs for the theme's fonts."""
    return [(f, FONTS / f.name) for f in sorted((theme_dir / "fonts").glob("*.[ot]tf"))]


def _install_fonts(pairs):
    for src, dst in pairs:
        ensure_dir(dst.parent)
        _atomic_copy(src, dst)
    if pairs:
        try:
            subprocess.run(["fc-cache", str(FONTS)], check=False, capture_output=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # fontconfig rescans on its own, just later


def _plugins_used(fragment):
    """(folder, id) of the app's plugins that the theme's widgets use."""
    used = {w.get("type", "").split(":")[0] for w in fragment.get("desktop_widgets", {}).get("widget", {}).values()}
    found = ((m.parent, tomllib.loads(m.read_text())["id"]) for m in sorted(PLUGINS.glob("*/plugin.toml")))
    return [(d, pid) for d, pid in found if pid in used]


def _install_plugins(fragment):
    """Copy the plugins the theme uses where Noctalia loads local ones.

    Files are written over the old ones: Noctalia hot-reloads edited files (not a swapped folder).
    Left in place on removal: an enabled plugin with no widget on the desktop draws nothing.
    """
    for src, _pid in _plugins_used(fragment):
        dst = ensure_dir(NOCTALIA_PLUGINS) / src.name
        if not dst.is_symlink():  # a symlink is a developer checkout: keep it live
            shutil.copytree(src, dst, dirs_exist_ok=True)


def _enable_plugins(fragment):
    """Enable the theme's plugins not enabled yet. Call after _reload(): enabling makes Noctalia save its
    settings from memory, which must already hold what we wrote (else it brings back what we removed)."""
    try:
        enabled = tomllib.loads(STATE.read_text()).get("plugins", {}).get("enabled", []) if STATE.exists() else []
    except tomllib.TOMLDecodeError:
        enabled = []
    failed = []
    for _src, pid in _plugins_used(fragment):
        if pid in enabled:
            continue
        try:
            ok = subprocess.run(["noctalia", "msg", "plugins", "enable", pid], capture_output=True,
                                timeout=10).returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            ok = False
        if not ok:
            log.warning("could not enable plugin %s: Noctalia not reachable, retried later", pid)
            failed.append(pid)
    return failed


def refresh(theme_dir):
    """Update the active theme's files in place (stickers, palette, fragment).

    The user's settings.toml and the backups are left untouched, so settings changed
    since the theme was applied survive; keys they override keep winning over the theme.
    """
    theme_dir = Path(theme_dir).resolve()
    validate(theme_dir)
    _close_editor()
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    active = current_theme()
    if not active or active["theme"] != meta["name"]:
        raise ValueError(_("“{name}” is not the active theme: use apply.").format(name=meta["name"]))
    output = detect_output() if "@OUTPUT@" in (theme_dir / "noctalia.toml").read_text() else None
    text = _render(theme_dir, output)
    fragment = tomllib.loads(text)
    tmp = ensure_dir(DATA) / "fragment.refresh.toml"
    tmp.write_text(text)
    _atomic_copy(theme_dir / "palette.json", PALETTES / f"{meta['palette']}.json")
    _install_fonts(_fonts(theme_dir))  # ponytail: a font added after apply isn't in the backup, so rollback keeps it
    write_options(fragment, reload=False)  # options first: Noctalia never sees new fragment + stale options
    _atomic_copy(tmp, FRAGMENT)
    tmp.unlink()
    _install_plugins(fragment)
    log.info("refreshed theme %s", meta["name"])
    _reload()
    _remember_pending(_enable_plugins(fragment))


def apply(theme_dir, label=None):
    theme_dir = Path(theme_dir).resolve()
    validate(theme_dir)
    _close_editor()
    output = detect_output() if "@OUTPUT@" in (theme_dir / "noctalia.toml").read_text() else None
    if current():
        rollback(current(), sync=False)  # snapshot the untouched user state; auto_sync follows the new theme
    meta = tomllib.loads((theme_dir / "theme.toml").read_text())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bdir = ensure_dir(BACKUPS / stamp)

    palette_dst = PALETTES / f"{meta['palette']}.json"
    fonts = _fonts(theme_dir)
    targets = [palette_dst, FRAGMENT, OPTIONS] + [dst for _src, dst in fonts]
    manifest = {"theme": meta["name"], "date": stamp, "label": label or _("Before “{name}”").format(name=meta["name"]),
                "state_existed": STATE.exists(), "files": {}, "wallpapers": current_wallpapers()}
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
        ensure_dir(palette_dst.parent)
        _atomic_copy(theme_dir / "palette.json", palette_dst)
        _install_fonts(fonts)  # before the fragment: widgets must find their font on first load
        write_options(fragment, reload=False)
        (bdir / "fragment.toml").write_text(fragment_text)
        _atomic_copy(bdir / "fragment.toml", FRAGMENT)
        if stripped is not None:
            # ponytail: no lock with Noctalia; a write it makes between our read and replace is lost (sub-second window)
            (bdir / "stripped.toml").write_text(stripped)
            _atomic_copy(bdir / "stripped.toml", STATE)
        _remember(stripped or "", fragment)
        _install_plugins(fragment)
        CURRENT.write_text(stamp)
    except Exception:
        rollback(stamp)  # leave the user exactly where they were
        raise
    log.info("applied theme %s (backup %s)", meta["name"], stamp)
    _reload()
    _remember_pending(_enable_plugins(fragment))
    heal()  # enabling may have made Noctalia save stale settings right away
    _show_theme_wallpaper(theme_dir)
    return stamp


def rollback(backup_id, sync=True):
    bdir = BACKUPS / backup_id
    manifest = json.loads((bdir / "manifest.json").read_text())
    _close_editor()
    if manifest.get("kind") == "setup":
        return _restore_setup(bdir, manifest)
    if current() and current() != backup_id:
        rollback(current(), sync=False)  # remove the active theme cleanly before going further back
    removing = backup_id == current()
    tdir = _theme_dir_name(bdir)
    if removing and tdir:
        _remember_wallpaper(tdir)  # before the state restore can change it
    try:  # your settings changed meanwhile survive the removal; only the theme's own leave
        carry = _user_changes(backup_id)[0] if backup_id == current() else {}
    except (OSError, tomllib.TOMLDecodeError):
        carry = {}  # unreadable state: fall back to the exact snapshot
    for path, saved in manifest["files"].items():
        p = Path(path)
        if saved:
            _atomic_copy(bdir / saved, p)
        elif p.exists():
            p.unlink()  # created by the theme, not there before
    if str(OPTIONS) not in manifest["files"]:
        OPTIONS.unlink(missing_ok=True)  # backups made before preferences existed don't list it
    if carry:
        state = tomllib.loads((bdir / "settings.toml").read_text()) if manifest["state_existed"] else {}
        for path, value in carry.items():
            _put(state, path, value)
        text = options.dump(state)
        tomllib.loads(text)  # refuse to write anything Noctalia could not parse
        (bdir / "carried.toml").write_text(text)
        ensure_dir(STATE.parent)
        _atomic_copy(bdir / "carried.toml", STATE)
        _remember(text)
        log.info("carried over %d setting(s): %s", len(carry), ", ".join(".".join(k) for k in sorted(carry)))
    elif manifest["state_existed"]:
        _atomic_copy(bdir / "settings.toml", STATE)
        _remember((bdir / "settings.toml").read_text())
    else:
        _remember("")
    CURRENT.unlink(missing_ok=True)  # every theme backup is a theme-free state
    log.info("restored backup %s", backup_id)
    _reload()
    # Leaving the theme: only its own wallpaper goes. Going back to an older backup: its wallpaper returns.
    _restore_wallpapers(manifest.get("wallpapers"), INSTALLED / tdir if removing and tdir else None)
    if sync:  # once, at the end: Noctalia refuses a sync while another runs
        sync_greeter()


GLUE_TOLERANCE = 0.5  # logical pixels; below that a position counts as unchanged


def _positions(state, fragment):
    """(cx, cy) of each theme widget: where Noctalia saved it after a drag, else where the theme put it."""
    saved = state.get("desktop_widgets", {}).get("widget", {})
    out = {}
    for wid, w in fragment.get("desktop_widgets", {}).get("widget", {}).items():
        s = saved.get(wid, {})
        out[wid] = (float(s.get("cx", w.get("cx", 0.0))), float(s.get("cy", w.get("cy", 0.0))))
    return out


def _set_position(text, wid, cx, cy):
    """Set cx/cy of one desktop widget in settings.toml text; line-based so the rest stays byte-identical."""
    lines = text.splitlines(keepends=True)
    path = ("desktop_widgets", "widget", wid)
    start = next((n for n, line in enumerate(lines) if _header(line) == path), None)
    if start is None:  # never dragged: Noctalia merges a partial table over the theme's
        sep = "\n" if text and not text.endswith("\n") else ""
        return f"{text}{sep}\n[desktop_widgets.widget.{options._key(wid)}]\ncx = {cx!r}\ncy = {cy!r}\n"
    end = next((n for n in range(start + 1, len(lines)) if _header(lines[n]) is not None), len(lines))
    todo = {"cx": cx, "cy": cy}
    for n in range(start + 1, end):
        line = lines[n]
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in todo:
            indent = line[:len(line) - len(line.lstrip())]
            lines[n] = f"{indent}{key} = {todo.pop(key)!r}\n"
    lines[start + 1:start + 1] = [f"{k} = {v!r}\n" for k, v in todo.items()]
    return "".join(lines)


def _editor_open():
    """True while Noctalia's widget editor is open: it ignores file changes then and rewrites its own on exit."""
    # ponytail: niri only; elsewhere assume closed (a glue during editing is then overwritten, not harmful)
    try:
        out = subprocess.run(["niri", "msg", "--json", "layers"], capture_output=True, text=True, timeout=5,
                             check=True).stdout
        return any(layer.get("namespace") == "noctalia-desktop-widgets-editor" for layer in json.loads(out))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return False



def _close_editor():
    """The widget editor ignores our files and saves its own layout when it closes: close it before we write."""
    if not _editor_open():
        return
    try:
        subprocess.run(["noctalia", "msg", "desktop-widgets-exit"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    for _i in range(30):
        time.sleep(0.1)
        if not _editor_open():
            time.sleep(0.5)  # let Noctalia finish the save it makes on exit
            return
    raise ValueError(_("Close Noctalia's widget editor, then try again."))


HEAL_WINDOW = 30  # s after we write settings.toml during which a stale rewrite is undone (seen: 11 s late)


def _remember(state_text, fragment=None):
    """Note the desktop widgets we just wrote (and the theme's), for heal()."""
    dw = tomllib.loads(state_text).get("desktop_widgets")
    ids = set((dw or {}).get("widget", {})) | set((fragment or {}).get("desktop_widgets", {}).get("widget", {}))
    ensure_dir(EXPECT.parent)
    EXPECT.write_text(json.dumps({"time": time.time(), "widgets": dw, "ids": sorted(ids), "pending": []}))


def _remember_pending(pids):
    try:
        exp = json.loads(EXPECT.read_text())
    except (OSError, ValueError):
        return
    exp["pending"] = pids
    EXPECT.write_text(json.dumps(exp))


def heal():
    """Undo what Noctalia brings back from memory right after we changed settings.toml, and enable plugins
    a theme needed while Noctalia was off. Returns True if something was fixed.

    Noctalia saves its whole settings from memory on some events (a `noctalia msg`, the editor closing); if it
    had not reloaded our files yet, that save restores the old desktop widgets. Such a rewrite is spotted
    because none of its widgets is one we wrote or the theme's; a layout edited in the editor keeps them.
    """
    try:
        exp = json.loads(EXPECT.read_text())
    except (OSError, ValueError):
        return False
    fixed = False
    if exp.get("pending") and FRAGMENT.exists() and current():
        exp["pending"] = _enable_plugins(tomllib.loads(FRAGMENT.read_text()))
        EXPECT.write_text(json.dumps(exp))
        fixed = not exp["pending"]
    if time.time() - exp.get("time", 0) > HEAL_WINDOW or not STATE.exists() or _editor_open():
        return fixed
    state = tomllib.loads(STATE.read_text())
    ids = set(state.get("desktop_widgets", {}).get("widget", {}))
    if not ids or ids & set(exp["ids"]):
        return fixed  # nothing there, or a layout built from ours
    if exp["widgets"] is None:
        del state["desktop_widgets"]
    else:
        state["desktop_widgets"] = exp["widgets"]
    text = options.dump(state)
    tomllib.loads(text)  # refuse to write anything Noctalia could not parse
    tmp = ensure_dir(DATA) / "heal.tmp.toml"
    tmp.write_text(text)
    _atomic_copy(tmp, STATE)
    tmp.unlink()
    log.warning("Noctalia rewrote stale desktop widgets (%s): put ours back", ", ".join(sorted(ids)))
    _reload()
    return True

def glue_groups():
    """Keep each `widget_groups` entry of the active theme together (e.g. a player and its frame).

    Noctalia drags widgets one by one; when one member of a group moved, the others get the same offset.
    Runs after the fact (app focus, settings.toml change), never while the editor is open. Returns the ids moved.
    """
    bid = current()
    tdir = _theme_dir_name(BACKUPS / bid) if bid else None
    meta = INSTALLED / tdir / "theme.toml" if tdir else None
    if not meta or not meta.exists() or not FRAGMENT.exists() or not STATE.exists() or _editor_open():
        return []  # editor open: wait for the save Noctalia makes when it closes
    groups = tomllib.loads(meta.read_text()).get("widget_groups", {})
    fragment = tomllib.loads(FRAGMENT.read_text())
    now = _positions(tomllib.loads(STATE.read_text()), fragment)
    base = _positions({}, fragment)  # right after apply, widgets sit where the theme put them
    try:
        saved = json.loads(GLUE.read_text())
        if saved["backup"] == bid:
            base |= {k: tuple(v) for k, v in saved["positions"].items() if k in base}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass

    def delta(i):
        return now[i][0] - base[i][0], now[i][1] - base[i][1]

    target = dict(now)
    for ids in groups.values():
        ids = [i for i in ids if i in now]
        moved = [i for i in ids if max(map(abs, delta(i))) > GLUE_TOLERANCE]
        if not moved or len(moved) == len(ids):
            continue  # untouched, or every member placed by hand: leave it
        dx, dy = delta(max(moved, key=lambda i: sum(map(abs, delta(i)))))
        for i in ids:
            if i not in moved:
                target[i] = (round(now[i][0] + dx, 1), round(now[i][1] + dy, 1))
    changed = sorted(i for i in target if target[i] != now[i])
    if changed:
        # ponytail: no lock with Noctalia; a save it makes between our read and replace wins (sub-second window)
        text = STATE.read_text()
        for i in changed:
            text = _set_position(text, i, *target[i])
        tomllib.loads(text)  # refuse to write anything Noctalia could not parse
        tmp = ensure_dir(DATA) / "glue.tmp.toml"
        tmp.write_text(text)
        _atomic_copy(tmp, STATE)
        tmp.unlink()
    GLUE.write_text(json.dumps({"backup": bid, "positions": target}))
    if changed:
        log.info("glued widget(s) back to their group: %s", ", ".join(changed))
        _reload()
    return changed


# What a setup backup copies whole: Noctalia's config, the installed themes and their fonts.
SETUP_DIRS = (("config", lambda: CONFIG), ("themes", lambda: INSTALLED), ("fonts", lambda: FONTS))


def save_setup():
    """Copy the whole Noctalia state as it is now (active theme, widget positions, everything)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bdir = ensure_dir(BACKUPS / stamp)
    for name, src in SETUP_DIRS:
        if src().is_dir():
            shutil.copytree(src(), bdir / name, symlinks=True)
    if STATE.exists():
        shutil.copy2(STATE, bdir / "settings.toml")
    active = current_theme()
    if active:  # the theme's way back must survive even if its backup is deleted later
        shutil.copytree(BACKUPS / active["id"], bdir / "theme-backup")
    label = (_("My setup, with “{name}”").format(name=active["theme"]) if active
             else _("My setup, without a theme"))
    manifest = {"kind": "setup", "theme": active["theme"] if active else None, "date": stamp, "label": label,
                "current": active["id"] if active else None, "state_existed": STATE.exists(), "files": {},
                "wallpapers": current_wallpapers()}
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log.info("saved setup %s", stamp)
    return stamp


def _swap_dir(src, dst):
    """Replace dst by a copy of src (or remove it), never leaving a half-copied folder in place."""
    old = dst.with_name(dst.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if src.is_dir():
        tmp = dst.with_name(dst.name + ".new")
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp, symlinks=True)
    if dst.exists():
        dst.replace(old)
    if src.is_dir():
        tmp.replace(dst)
    if old.exists():
        shutil.rmtree(old)


def _restore_setup(bdir, manifest):
    for name, dst in SETUP_DIRS:
        ensure_dir(dst().parent)
        _swap_dir(bdir / name, dst())
    if manifest["state_existed"]:
        ensure_dir(STATE.parent)
        _atomic_copy(bdir / "settings.toml", STATE)
    else:
        STATE.unlink(missing_ok=True)
    _remember(STATE.read_text() if STATE.exists() else "",
              tomllib.loads(FRAGMENT.read_text()) if FRAGMENT.exists() else None)
    cur = manifest["current"]
    if cur:
        if not (BACKUPS / cur).exists():
            shutil.copytree(bdir / "theme-backup", BACKUPS / cur)
        CURRENT.write_text(cur)
    else:
        CURRENT.unlink(missing_ok=True)
    GLUE.unlink(missing_ok=True)  # positions remembered from another session would misread who moved
    log.info("restored setup %s", bdir.name)
    _reload()
    _restore_wallpapers(manifest.get("wallpapers"))
    sync_greeter()


if __name__ == "__main__":
    cmd = sys.argv[1:2] or ["list"]
    if cmd == ["apply"]:
        print(apply(sys.argv[2]))
    elif cmd == ["refresh"]:
        refresh(sys.argv[2])
        print("refreshed", sys.argv[2])
    elif cmd == ["glue"]:
        print("moved:", ", ".join(glue_groups()) or "nothing")
    elif cmd == ["save"]:
        print(save_setup())
    elif cmd == ["rollback"]:
        rollback(sys.argv[2])
        print("restored", sys.argv[2])
    else:
        for b in list_backups():
            print(b["id"], b["label"])
