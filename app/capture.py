# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a theme from the desktop as it looks now: palette, wallpaper, bar and dock looks, desktop widgets.

The theme is built in a temporary folder, packed, then imported like any package: it passes the same checks.
"""
import json
import re
import shutil
import tempfile
import tomllib
from datetime import date
from pathlib import Path

import installer
import package
import palette
from i18n import _
from paths import CONFIG, INSTALLED, LIBRARY, PALETTES, STATE, THEMES, ensure_dir

# Bar slots name widget instances configured in [widget], which a theme may not set.
BAR_LAYOUT = ("start", "center", "end", "capsule_group")
THEME_SOURCE = ("source", "custom_palette", "community_palette", "builtin", "wallpaper_scheme", "templates")
WALLPAPER_PLACE = ("directory", "default", "last", "monitors")  # where your own wallpapers are, not a look
WALL_TYPES = (".webp", ".png", ".jpg", ".jpeg")
PLUGIN = re.compile(r"([\w.-]+/[\w.-]+):[\w-]+")


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def current_config():
    """What you set in Noctalia, merged in its own order: config/*.toml alphabetically, then the state file."""
    merged = {}
    for f in [*sorted(CONFIG.glob("*.toml")), STATE]:
        try:
            _merge(merged, tomllib.loads(f.read_text()))
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return merged


def _key(k):
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # JSON string escapes are valid TOML basic strings
    if isinstance(v, list):
        return "[" + ", ".join(_value(i) for i in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot write {type(v).__name__} as TOML")


def dump(table, path=()):
    """TOML text for a table of tables, strings, numbers, booleans and lists (all a theme needs)."""
    out = [f"{_key(k)} = {_value(v)}" for k, v in table.items() if not isinstance(v, dict)]
    if out and path:
        out.insert(0, "[" + ".".join(_key(k) for k in path) + "]")
    for k, v in table.items():
        if isinstance(v, dict) and (sub := dump(v, path + (k,))):
            out += ["", sub] if out else [sub]
    return "\n".join(out)


def slug(name):
    return re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-_")[:64] or "my-theme"


class _Capture:
    def __init__(self, root):
        self.root, self.notes, self.copied = root, [], {}

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)

    def file(self, value):
        """@THEME_DIR@ path of a file the desktop uses, copied into the theme; None if it cannot come along."""
        src = Path(value).expanduser()
        if not src.is_absolute() or not src.exists():
            return None
        if src not in self.copied:
            try:  # from an installed theme: same place in the new one (stickers/x.png, a frame folder)
                rel = Path(*src.relative_to(INSTALLED).parts[1:])
            except ValueError:
                rel = Path("stickers") / src.name
            if not rel.parts or (src.is_dir() and INSTALLED not in src.parents):
                return None  # a folder from elsewhere could be your whole home: never copied
            if src.is_file() and src.suffix.lower() not in package.EXTENSIONS:
                return None
            dst, n = self.root / rel, 1
            while dst.exists():  # two stickers with one name, from different places
                n += 1
                dst = dst.with_name(f"{rel.stem}-{n}{rel.suffix}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=lambda d, names: [
                    x for x in names if (Path(d) / x).is_file() and Path(x).suffix.lower() not in package.EXTENSIONS])
            else:
                shutil.copy2(src, dst)
            self.copied[src] = dst.relative_to(self.root)
        return "@THEME_DIR@/" + self.copied[src].as_posix()

    def clean(self, value, label, plugins):
        """`value` with paths turned into theme files; None for what a theme may not carry (noted)."""
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                key = f"{label}.{k}" if label else k
                if package.UNSAFE_KEY.search(k):
                    self.note(_("{key}: can run a program, left out").format(key=key))
                elif (v := self.clean(v, key, plugins)) is not None:
                    out[k] = v
            return out
        if isinstance(value, list):
            items = [self.clean(i, label, plugins) for i in value]
            return None if None in items else items
        if isinstance(value, str) and "/" in value:
            plugin = PLUGIN.fullmatch(value)
            if plugin and plugin.group(1) in plugins:
                return value
            if new := self.file(value):
                return new
            self.note(_("{key}: points to a file that cannot come along, left out").format(key=label))
            return None
        return value


def _palette(cap, theme):
    source = theme.get("source", "builtin")
    found = {"custom": PALETTES / f"{theme.get('custom_palette')}.json",
             "community": STATE.parent / "community-palettes" / f"{theme.get('community_palette')}.json"}.get(source)
    try:
        if found and found.is_file() and not palette.check(found):
            return found
    except (OSError, ValueError, KeyError, TypeError):
        pass
    cap.note(_("Your palette ({source}) has no file to copy: the theme starts with Brume's colors. "
               "Edit palette.json to recolor it.").format(source=source))
    return THEMES / "brume" / "palette.json"


def _wallpaper(cap, cfg):
    shown = next(iter(installer.current_wallpapers().values()), None)
    shown = Path(shown or cfg.get("wallpaper", {}).get("default", {}).get("path", ""))
    if not shown.is_file() or shown.suffix.lower() not in WALL_TYPES:
        cap.note(_("The wallpaper on screen could not be copied (missing, or not WebP, PNG or JPEG)."))
        return None
    name = "wall_" + slug(shown.stem.removeprefix("wall_")) + shown.suffix.lower()
    shutil.copy2(shown, ensure_dir(cap.root / "wallpapers") / name)
    return name


def _fragment(cap, cfg, folder):
    plugins = package._plugin_ids()
    frag = {t: cfg[t] for t in sorted(package.TABLES) if isinstance(cfg.get(t), dict)}
    theme = frag.setdefault("theme", {})
    for k in THEME_SOURCE:
        theme.pop(k, None)
    theme.update(source="custom", custom_palette=folder)
    for k in WALLPAPER_PLACE:
        frag.get("wallpaper", {}).pop(k, None)
    if frag.get("dock", {}).pop("pinned", None):
        cap.note(_("Your pinned dock apps stay yours: not part of the theme."))
    for bar in frag.get("bar", {}).values():
        if isinstance(bar, dict) and [bar.pop(k) for k in BAR_LAYOUT if k in bar]:  # a list: pop them all
            cap.note(_("The bar's widget layout is left out (widgets are set up outside the theme); "
                       "its looks (size, font, colors) come along."))
    dw = frag.get("desktop_widgets", {})
    widgets = dw.get("widget", {})
    for wid, w in list(widgets.items()):
        kind = str(w.get("type", ""))
        if "/" in kind and kind.split(":")[0] not in plugins:
            del widgets[wid]
            cap.note(_("Widget {id} ({type}) comes from a third-party plugin: left out.").format(id=wid, type=kind))
        elif "output" in w:
            w["output"] = "@OUTPUT@"
    if "widget_order" in dw:
        dw["widget_order"] = [i for i in dw["widget_order"] if i in widgets]
    return cap.clean(frag, "", plugins)


def create(name, author, description, license_id="GPL-3.0-or-later"):
    """Capture the desktop into a new imported theme. Returns (theme folder, notes on what was left out)."""
    name, folder = name.strip(), slug(name)
    if not name:
        raise ValueError(_("Give the theme a name."))
    if (LIBRARY / folder).exists() or (THEMES / folder).exists():
        raise ValueError(_("A theme already uses the folder “{folder}”: choose another name.").format(folder=folder))
    cfg = current_config()
    ensure_dir(LIBRARY)
    with tempfile.TemporaryDirectory(dir=LIBRARY.parent, prefix=".capture-") as tmp:
        root = Path(tmp) / folder
        root.mkdir()
        cap = _Capture(root)
        shutil.copy(_palette(cap, cfg.get("theme", {})), root / "palette.json")
        wall = _wallpaper(cap, cfg)
        frag = _fragment(cap, cfg, folder)
        active = installer.active_dir()
        if active and (active / "fonts").is_dir() and "font_family" in json.dumps(frag.get("desktop_widgets", {})):
            shutil.copytree(active / "fonts", root / "fonts")  # the widgets may name the active theme's fonts
        meta = {"format": package.FORMAT, "name": name, "description": description.strip() or
                _("Captured from {author}'s desktop on {day}.").format(author=author, day=date.today().isoformat()),
                "author": author.strip() or "?", "version": "1.0.0", "license": license_id, "palette": folder}
        if wall:
            meta["login_wallpaper"] = wall
        (root / "theme.toml").write_text("# SPDX-License-Identifier: " + license_id + "\n" + dump(meta) + "\n")
        (root / "noctalia.toml").write_text("# Captured from the desktop by Noctalia Themes.\n" + dump(frag) + "\n")
        zipped = package.pack(root, Path(tmp) / "capture.zip")
        package.import_zip(zipped)
    installer.log.info("created theme %s from the desktop (%d notes)", folder, len(cap.notes))
    return LIBRARY / folder, cap.notes
