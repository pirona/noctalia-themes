#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme packages: a .zip holding one theme folder. Check, import into the library, pack, scaffold.

  python3 app/package.py new <folder>      create a commented theme skeleton
  python3 app/package.py check <folder>    run the same checks as an import
  python3 app/package.py pack <folder> [out_dir]   write <name>-<version>.zip
An imported theme comes from anywhere: its Noctalia fragment is held to an allowlist (see docs/THEMES.md).
"""
import re
import shutil
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import installer  # noqa: E402
from i18n import _  # noqa: E402
from paths import LIBRARY, PLUGINS, THEMES, ensure_dir  # noqa: E402

FORMAT = 1  # theme.toml `format` this app reads
FOLDER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
EXTENSIONS = {".toml", ".json", ".md", ".txt", ".webp", ".png", ".jpg", ".jpeg", ".svg", ".ttf", ".otf"}
REQUIRED = ("theme.toml", "palette.json", "noctalia.toml")
MAX_FILES, MAX_FILE, MAX_TOTAL = 500, 32 << 20, 128 << 20
# Noctalia tables a theme may set: looks only. Anything else (session, hooks, launcher, network...) is refused.
TABLES = {"theme", "wallpaper", "bar", "desktop_widgets", "dock"}
# Keys that run programs or reach the network, wherever they sit (bar widgets have *_command keys).
UNSAFE_KEY = re.compile(r"(^|_)(commands?|exec|scripts?|hooks?|cmd|urls?)($|_)", re.I)


def _authoring(rel):
    """Authoring scripts: never packed, never run (installer._render does not copy them)."""
    return any(p == "__pycache__" or p.endswith((".py", ".pyc")) for p in rel.parts)


def _plugin_ids():
    return {tomllib.loads(m.read_text())["id"] for m in PLUGINS.glob("*/plugin.toml")}


def _walk(table, prefix=""):
    for k, v in table.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _walk(v, key + ".")
        elif isinstance(v, list):
            for i, item in enumerate(v):
                yield from (_walk(item, f"{key}[{i}].") if isinstance(item, dict) else [(f"{key}[{i}]", item)])
        else:
            yield key, v


def check_fragment(text):
    """Errors for an imported theme's Noctalia fragment: allowlisted tables, no command keys, local files only."""
    try:
        frag = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f"noctalia.toml: {e}"]
    errors = [f"noctalia.toml: [{t}] is not allowed in a theme" for t in frag if t not in TABLES]
    plugins = _plugin_ids()
    for key, value in _walk({t: frag[t] for t in frag if t in TABLES}):
        if any(UNSAFE_KEY.search(part.split("[")[0]) for part in key.split(".")):  # tables too: [bar.hooks]
            errors.append(f"noctalia.toml: '{key}' can run a program, not allowed in a theme")
        if isinstance(value, str) and "/" in value:
            local = value.startswith("@THEME_DIR@/") and ".." not in value.split("/")
            plugin = re.fullmatch(r"([\w.-]+/[\w.-]+):[\w-]+", value)
            if not local and not (plugin and plugin.group(1) in plugins):
                errors.append(f"noctalia.toml: '{key}' must point inside the theme (@THEME_DIR@/...) "
                              "or to a plugin shipped with the app")
    return errors


def check(theme_dir, imported=True):
    """Every error of a theme folder, empty if it is fine. `imported` adds the allowlist checks."""
    d = Path(theme_dir)
    errors = [f"missing {f}" for f in REQUIRED if not (d / f).is_file()]
    if errors:
        return errors
    try:
        meta = tomllib.loads((d / "theme.toml").read_text())
    except tomllib.TOMLDecodeError as e:
        return [f"theme.toml: {e}"]
    if not FOLDER.fullmatch(d.name):
        errors.append(f"folder name '{d.name}' must match {FOLDER.pattern}")
    if not isinstance(meta.get("format", FORMAT), int) or meta.get("format", FORMAT) > FORMAT:
        errors.append(f"theme.toml: format {meta['format']!r} needs a newer version of the app")
    for key in ("name", "description", "author", "version", "license"):
        if not str(meta.get(key, "")).strip():
            errors.append(f"theme.toml: missing '{key}'")
    login = meta.get("login_wallpaper")
    if login is not None and not (str(login) == Path(str(login)).name and (d / "wallpapers" / str(login)).is_file()):
        errors.append(f"theme.toml: login_wallpaper '{login}' is not a file of wallpapers/")
    try:
        installer.validate(d)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        errors.extend(str(e).splitlines())
    for f in d.rglob("*"):
        if _authoring(f.relative_to(d)):
            continue
        if f.is_symlink() or (f.is_file() and f.suffix.lower() not in EXTENSIONS):
            errors.append(f"{f.relative_to(d)}: file type not allowed")
    if imported:
        if meta.get("palette") != d.name:  # palettes/<name>.json is shared by all themes: one name per folder
            errors.append(f"theme.toml: 'palette' must be the folder name '{d.name}'")
        errors += check_fragment((d / "noctalia.toml").read_text())
    return errors


def read_zip(zip_path):
    """(folder name, theme.toml metadata) of a package, after the archive checks. Raises ValueError."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile):
        raise ValueError(_("This file is not a .zip archive.")) from None
    with zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_FILES:
            raise ValueError(_("The archive is empty or holds too many files."))
        tops = set()
        total = 0
        for i in infos:
            parts = Path(i.filename).parts
            if i.filename.startswith("/") or ".." in parts or "\\" in i.filename or not parts:
                raise ValueError(_("Unsafe path in the archive: {name}").format(name=i.filename))
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(_("Symbolic links are not allowed: {name}").format(name=i.filename))
            if i.file_size > MAX_FILE:
                raise ValueError(_("File too large: {name}").format(name=i.filename))
            total += i.file_size
            tops.add(parts[0])
        if total > MAX_TOTAL:
            raise ValueError(_("The archive is too large once unpacked."))
        if len(tops) != 1 or f"{next(iter(tops))}/theme.toml" not in zf.namelist():
            raise ValueError(_("The archive must hold one theme folder."))
        folder = tops.pop()
        try:
            meta = tomllib.loads(zf.read(f"{folder}/theme.toml").decode())
        except (KeyError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            raise ValueError(_("theme.toml is missing or unreadable.")) from None
    return folder, meta


def existing(folder):
    """Metadata of the library theme in `folder`, or None."""
    toml = LIBRARY / folder / "theme.toml"
    return tomllib.loads(toml.read_text()) if toml.is_file() else None


def import_zip(zip_path):
    """Check a package and install it into the library (replacing a theme of the same folder). Returns metadata."""
    folder, meta = read_zip(zip_path)
    if (THEMES / folder).exists() or any(t["name"] == meta.get("name") for t in installer.list_themes(THEMES)):
        raise ValueError(_("“{name}” is a built-in theme and cannot be replaced.").format(
            name=meta.get("name", folder)))
    # The active theme is found by name: two imported themes must not share one.
    if any(t["name"] == meta.get("name") and t["dir"].name != folder for t in installer.list_themes(LIBRARY)):
        raise ValueError(_("Another imported theme is already named “{name}”.").format(name=meta.get("name")))
    ensure_dir(LIBRARY)
    with tempfile.TemporaryDirectory(dir=LIBRARY.parent, prefix=".import-") as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)  # names already checked by read_zip: nothing lands outside tmp
        staged = Path(tmp) / folder
        errors = check(staged)
        if errors:
            raise ValueError(_("This theme cannot be imported:") + "\n• " + "\n• ".join(errors))
        target = LIBRARY / folder
        old = Path(tmp) / ".old"
        if target.exists():
            target.rename(old)  # ponytail: two renames, not atomic together; a crash between leaves no theme
        staged.rename(target)
    installer.log.info("imported theme %s %s from %s", meta["name"], meta.get("version"), Path(zip_path).name)
    return meta


def remove(folder):
    """Delete an imported theme from the library (never a built-in one)."""
    target = LIBRARY / folder
    if not FOLDER.fullmatch(folder) or not target.is_dir():
        raise ValueError(_("No imported theme “{name}”.").format(name=folder))
    shutil.rmtree(target)
    installer.log.info("removed imported theme %s", folder)


def pack(theme_dir, out_dir="."):
    """Check a theme folder, then zip it as <folder>-<version>.zip. Returns the archive path."""
    d = Path(theme_dir).resolve()
    errors = check(d)
    if errors:
        raise ValueError("\n".join(errors))
    meta = tomllib.loads((d / "theme.toml").read_text())
    out = Path(out_dir) / f"{d.name}-{meta['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(d.rglob("*")):
            if f.is_file() and not _authoring(f.relative_to(d)):
                zf.write(f, f"{d.name}/{f.relative_to(d)}")
    return out


SKELETON = '''# SPDX-License-Identifier: GPL-3.0-or-later
format = 1
name = "{title}"
description = "One or two sentences: what the theme looks like."
author = "Your name"
version = "1.0.0"
license = "GPL-3.0-or-later"  # SPDX id; artwork you did not make needs its own license, see docs/THEMES.md
palette = "{folder}"
# preview = "preview.webp"              # 16:9 image shown in the app
# login_wallpaper = "wall_example.webp" # file of wallpapers/, shown on the Noctalia Greeter login screen
'''
FRAGMENT = '''# SPDX-License-Identifier: GPL-3.0-or-later
# Noctalia config fragment. Allowed tables: theme, wallpaper, bar, desktop_widgets, dock.
# Files are referenced as "@THEME_DIR@/stickers/x.png"; "@OUTPUT@" is the target screen.

[theme]
source = "custom"
custom_palette = "{folder}"
mode = "dark"

[wallpaper]
transition = ["fade"]
'''


def new(theme_dir):
    """Create a theme skeleton that passes `check` once palette.json is filled in."""
    d = Path(theme_dir)
    if d.exists():
        raise ValueError(f"{d} already exists")
    if not FOLDER.fullmatch(d.name):
        raise ValueError(f"folder name must match {FOLDER.pattern}")
    (d / "wallpapers").mkdir(parents=True)
    (d / "stickers").mkdir()
    title = d.name.replace("-", " ").replace("_", " ").title()
    (d / "theme.toml").write_text(SKELETON.format(title=title, folder=d.name))
    (d / "noctalia.toml").write_text(FRAGMENT.format(folder=d.name))
    shutil.copy(THEMES / "brume" / "palette.json", d / "palette.json")  # a valid start, to recolour
    return d


def main(argv):
    if len(argv) < 2 or argv[0] not in ("new", "check", "pack"):
        print(__doc__.split("\n\n")[0].split("\n", 1)[1], file=sys.stderr)
        return 2
    try:
        if argv[0] == "new":
            print(f"created {new(argv[1])}: edit theme.toml and palette.json, then run check")
        elif argv[0] == "check":
            errors = check(argv[1])
            print("\n".join(errors) or "ok")
            return 1 if errors else 0
        else:
            print(pack(argv[1], argv[2] if len(argv) > 2 else "."))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
