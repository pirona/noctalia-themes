# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_capture.py  (a fake desktop in a temp dir, never touches the real session)"""
import json
import os
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="noctalia-themes-capture-"))
for var in ("NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_THEMES_HOME", "NOCTALIA_THEMES_CONFIG",
            "NOCTALIA_THEMES_FONTS", "NOCTALIA_DATA_HOME"):
    os.environ[var] = str(SANDBOX / var)
os.environ["PATH"] = ""  # no Noctalia IPC: the wallpaper comes from the config
os.environ["NOCTALIA_THEMES_OUTPUT"] = "CRT-1985"
os.environ["LANGUAGE"] = "en"
sys.path.insert(0, str(ROOT / "app"))
import capture  # noqa: E402
import installer  # noqa: E402
import package  # noqa: E402
from paths import CONFIG, INSTALLED, LIBRARY, PALETTES, STATE  # noqa: E402

# A fake desktop: custom palette, a sticker from ~/Pictures, a frame from the active theme, a spy plugin.
pics = SANDBOX / "Pictures"
pics.mkdir()
(pics / "cat.png").write_bytes(b"\x89PNG not really a cat")
(pics / "My Beach.jpg").write_bytes(b"\xff\xd8 sand everywhere")
(pics / "diary.txt").write_text("dear diary, today I themed")  # private text: must never be copied
frame = INSTALLED / "old-theme" / "stickers" / "frame"
frame.mkdir(parents=True)
(frame / "top.png").write_bytes(b"\x89PNG")
(frame / "steal-cookies.sh").write_text("echo nope")
PALETTES.mkdir(parents=True)
shutil.copy(ROOT / "themes" / "brume" / "palette.json", PALETTES / "night.json")
(CONFIG / "zz-theme.toml").write_text(f'''
[theme]
source = "custom"
custom_palette = "night"
mode = "dark"
[desktop_widgets]
enabled = true
widget_order = ["cat", "player", "spy"]
[desktop_widgets.widget.cat]
type = "sticker"
output = "eDP-1"
cx = 100.0
[desktop_widgets.widget.cat.settings]
image_path = "{pics / "cat.png"}"
[desktop_widgets.widget.player]
type = "billisdead/theme-widgets:player"
output = "eDP-1"
[desktop_widgets.widget.player.settings]
frame = "{frame}"
[desktop_widgets.widget.note]
type = "sticker"
[desktop_widgets.widget.note.settings]
image_path = "{pics / "diary.txt"}"
[desktop_widgets.widget.sneaky]
type = "sticker"
[desktop_widgets.widget.sneaky.settings]
image_path = "{INSTALLED / "old-theme" / ".." / ".." / ".." / ".." / "Pictures" / "cat.png"}"
[desktop_widgets.widget.spy]
type = "someone/keylogger:widget"
''')
STATE.parent.mkdir(parents=True)
STATE.write_text(f'''
[bar.default]
font_scale = 0.8
start = ["launcher", "widget_2"]
center = ["clock"]
middle_click_command = "rm -rf ~"
[dock]
icon_size = 48
pinned = ["org.gnome.Ptyxis"]
[wallpaper]
transition = ["fade"]
directory = "{pics}"
[wallpaper.default]
path = "{pics / "My Beach.jpg"}"
[session]
lock_command = "swaylock"
''')

tdir, notes = capture.create("Night Swim", "billisdead", "")
assert tdir == LIBRARY / "night-swim" and package.check(tdir) == [], package.check(tdir)
meta = tomllib.loads((tdir / "theme.toml").read_text())
assert meta["author"] == "billisdead" and meta["login_wallpaper"] == "wall_my-beach.jpg" and meta["description"]
assert (tdir / "wallpapers" / "wall_my-beach.jpg").is_file()
frag = tomllib.loads((tdir / "noctalia.toml").read_text())
assert set(frag) == {"theme", "desktop_widgets", "bar", "dock", "wallpaper"}, frag.keys()  # no [session]
assert frag["theme"] == {"source": "custom", "custom_palette": "night-swim", "mode": "dark"}
w = frag["desktop_widgets"]["widget"]
assert w["cat"]["settings"]["image_path"] == "@THEME_DIR@/stickers/cat.png" and w["cat"]["output"] == "@OUTPUT@"
assert w["player"]["settings"]["frame"] == "@THEME_DIR@/stickers/frame"
copied = tdir / "stickers" / "frame"
assert (copied / "top.png").is_file() and not (copied / "steal-cookies.sh").exists()  # only allowed types
assert "image_path" not in w["note"].get("settings", {}) and not list(tdir.rglob("diary.txt"))
assert w["sneaky"]["settings"]["image_path"] == "@THEME_DIR@/stickers/cat.png"  # resolved: same cat, no escape
assert "spy" not in w and frag["desktop_widgets"]["widget_order"] == ["cat", "player"]
assert frag["bar"]["default"] == {"font_scale": 0.8}  # layout and command gone, looks kept
assert frag["dock"] == {"icon_size": 48} and frag["wallpaper"] == {"transition": ["fade"]}
joined = "\n".join(notes)
for needle in ("keylogger", "can run a program", "pinned dock apps", "widget layout"):
    assert needle in joined, (needle, notes)

# The name is taken now, and a built-in name never works.
for name, needle in (("Night Swim", "already uses the folder"), ("Brume", "already uses the folder"), ("  ", "name")):
    try:
        capture.create(name, "billisdead", "")
    except ValueError as e:
        assert needle in str(e), e
    else:
        raise AssertionError(f"{name!r} was created")

# A community palette that fails the contrast rule: Brume's colors, and the note says why.
murky = json.loads((ROOT / "themes" / "brume" / "palette.json").read_text())
murky["dark"]["mOnPrimary"] = murky["dark"]["mPrimary"]  # text the color of its background
(STATE.parent / "community-palettes").mkdir()
(STATE.parent / "community-palettes" / "Murky.json").write_text(json.dumps(murky))
(CONFIG / "zz-theme.toml").write_text('[theme]\nsource = "community"\ncommunity_palette = "Murky"\n')
tdir, notes = capture.create("Murky Waters", "billisdead", "Swamp chic.")
assert package.check(tdir) == [] and any("Murky" in n and "contrast" in n for n in notes), notes

# A built-in palette has no file: the theme starts from Brume's colors, and says so.
(CONFIG / "zz-theme.toml").write_text('[theme]\nsource = "builtin"\nbuiltin = "Noctalia"\n')
tdir, notes = capture.create("Plain Toast", "billisdead", "Bread, but themed.")
assert package.check(tdir) == [] and any("Brume's colors" in n for n in notes), notes
assert (tdir / "palette.json").read_text() == (ROOT / "themes" / "brume" / "palette.json").read_text()

# A real theme with widgets, applied then captured: frame folder, sticker, plugin widget, fonts all come along.
(CONFIG / "zz-theme.toml").unlink()
STATE.write_text("")
installer.apply(ROOT / "themes" / "vaporwave")
tdir, notes = capture.create("Vapor Copy", "billisdead", "")
assert package.check(tdir) == [], package.check(tdir)
w = tomllib.loads((tdir / "noctalia.toml").read_text())["desktop_widgets"]["widget"]
assert w["vw-dialog"]["settings"]["image_path"] == "@THEME_DIR@/stickers/dialog-loading.png"
assert w["vw-player"]["settings"]["frame"] == "@THEME_DIR@/stickers/player_frame"
assert w["vw-clock"]["output"] == "@OUTPUT@"
assert (tdir / "stickers" / "dialog-loading.png").is_file() and any((tdir / "stickers" / "player_frame").iterdir())
assert (tdir / "palette.json").read_text() == (ROOT / "themes" / "vaporwave" / "palette.json").read_text(), notes

# The TOML writer round-trips what a theme holds, odd keys included.
sample = {"a": {"my.widget": {"x": 1.5, "on": True, "s": 'quote " and é', "l": [1, [2, "b"]], "t": [{"k": 1}]}}}
assert tomllib.loads(capture.dump(sample)) == sample
print("ok")
