# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_installer.py  (sandboxed in a temp dir, never touches the real session)"""
import hashlib
import os
import shutil
import stat
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="noctalia-themes-test-"))
for var in ("NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_THEMES_HOME", "NOCTALIA_THEMES_CONFIG",
            "NOCTALIA_THEMES_FONTS", "NOCTALIA_DATA_HOME"):
    os.environ[var] = str(SANDBOX / var)
os.environ["NOCTALIA_THEMES_OUTPUT"] = "CRT-1985"
os.environ["PATH"] = ""  # no noctalia binary: config-reload becomes a no-op
sys.path.insert(0, str(ROOT / "app"))
import installer  # noqa: E402
import options  # noqa: E402

INK = ROOT / "tests/fixtures/ink-test"  # full-featured theme: plugin widgets, font, groups

STATE_SAMPLE = '''config_version = 15

[bar.default]
end = [
    "status",
    "tray"
]

[desktop_widgets]
enabled = false
widget_order = [ "w1" ]

    [desktop_widgets.widget.w1]
    type = "clock"

[theme]
builtin = "Noctalia"
mode = "light"
source = "wallpaper"

    [theme.templates]
    builtin_ids = [ "niri" ]

[wallpaper]
directory = "/home/someone/Images"
'''


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_strip():
    frag = tomllib.loads((ROOT / "themes/vaporwave/noctalia.toml").read_text())
    out = tomllib.loads(installer.strip_overrides(STATE_SAMPLE, frag))
    assert "desktop_widgets" not in out
    assert "source" not in out["theme"] and "mode" not in out["theme"]
    assert out["theme"]["builtin"] == "Noctalia"
    assert out["theme"]["templates"]["builtin_ids"] == ["niri"]  # niri color sync kept
    assert out["bar"]["default"]["end"] == ["status", "tray"]
    assert out["wallpaper"]["directory"] == "/home/someone/Images"


def test_apply_rollback_roundtrip():
    installer.STATE.parent.mkdir(parents=True)
    installer.STATE.write_text(STATE_SAMPLE)
    before = sha(installer.STATE)
    installer.apply(ROOT / "themes/vaporwave")
    bid = installer.apply(ROOT / "themes/vaporwave")  # re-apply must not snapshot a themed state
    merged = tomllib.loads(installer.STATE.read_text()) | tomllib.loads(installer.FRAGMENT.read_text())
    assert merged["theme"]["source"] == "custom"
    assert "@THEME_DIR@" not in installer.FRAGMENT.read_text()
    assert (installer.CONFIG / "palettes/vaporwave.json").exists()
    installer.rollback(bid)
    assert installer.current() is None
    assert sha(installer.STATE) == before
    assert not installer.FRAGMENT.exists()
    assert not (installer.CONFIG / "palettes/vaporwave.json").exists()


def test_invalid_theme_touches_nothing():
    bad = SANDBOX / "bad-theme"
    shutil.copytree(ROOT / "themes/vaporwave", bad)
    (bad / "palette.json").write_text((bad / "palette.json").read_text().replace("#FF71CE", "#F7C", 1))
    before = sha(installer.STATE)
    try:
        installer.apply(bad)
        raise AssertionError("invalid palette was accepted")
    except ValueError as e:
        assert "mPrimary" in str(e)
    assert sha(installer.STATE) == before and not installer.FRAGMENT.exists()


def test_palette_name_cannot_escape():
    evil = SANDBOX / "evil-theme"
    shutil.copytree(ROOT / "themes/vaporwave", evil)
    (evil / "theme.toml").write_text('name = "Trojan Horse Wave"\npalette = "../../../etc/oups"\n')
    try:
        installer.validate(evil)
        raise AssertionError("path traversal accepted")
    except ValueError as e:
        assert "palette" in str(e)


def test_failure_mid_apply_rolls_back():
    before = sha(installer.STATE)
    real_copy = installer._atomic_copy

    def flaky(src, dst):
        if "stripped" in str(src):
            raise OSError("disque plein, comme le frigo un dimanche soir")
        real_copy(src, dst)

    installer._atomic_copy = flaky
    try:
        installer.apply(ROOT / "themes/vaporwave")
        raise AssertionError("failure was swallowed")
    except OSError:
        pass
    finally:
        installer._atomic_copy = real_copy
    assert sha(installer.STATE) == before
    assert not installer.FRAGMENT.exists() and installer.current() is None


def test_restore_older_backup_while_themed():
    before = sha(installer.STATE)
    older = installer.apply(ROOT / "themes/vaporwave")
    installer.apply(ROOT / "themes/vaporwave")
    installer.rollback(older)
    assert installer.current() is None and not installer.FRAGMENT.exists()
    assert sha(installer.STATE) == before


def test_output_is_substituted():
    installer.apply(ROOT / "themes/vaporwave")
    frag = installer.FRAGMENT.read_text()
    assert 'output = "CRT-1985"' in frag and "@OUTPUT@" not in frag
    installer.rollback(installer.current())


def test_output_cannot_inject():
    os.environ["NOCTALIA_THEMES_OUTPUT"] = 'X"\nenabled = false\n#'
    try:
        installer.apply(ROOT / "themes/vaporwave")
        widgets = tomllib.loads(installer.FRAGMENT.read_text())["desktop_widgets"]["widget"]
        assert widgets["vw-clock"]["output"] == 'X"\nenabled = false\n#'
        assert "enabled" not in widgets["vw-clock"]
        installer.rollback(installer.current())
    finally:
        os.environ["NOCTALIA_THEMES_OUTPUT"] = "CRT-1985"


def test_changes_since_apply():
    bid = installer.apply(ROOT / "themes/vaporwave")
    assert installer.changes_since_apply() == [] and installer.kept_since_apply() == []
    state = installer.STATE.read_text()
    state = state.replace('builtin = "Noctalia"', 'builtin = "Synthwave du dimanche"')
    state += '\n[wallpaper.last]\npath = "/tmp/rotation.png"\n'  # Noctalia's own noise
    installer.STATE.write_text(state)
    assert installer.kept_since_apply() == ["theme.builtin"] and installer.changes_since_apply() == []
    echoed = state + '\n[desktop_widgets]\nenabled = true\n'  # theme value written back by Noctalia
    echoed += '\n[wallpaper.monitors.eDP-1]\npath = "/tmp/choix-perso.png"\n'  # a real user choice
    installer.STATE.write_text(echoed)
    assert installer.kept_since_apply() == ["theme.builtin", "wallpaper.monitors.eDP-1.path"]
    assert installer.changes_since_apply() == []
    moved = echoed.replace("enabled = true", "enabled = true\nwidget_order = [ \"vw-clock\" ]")
    installer.STATE.write_text(moved)  # a theme widget rearranged: belongs to the theme, leaves with it
    assert installer.changes_since_apply() == ["desktop_widgets.widget_order"]
    installer.STATE.write_text(echoed + "[[[ pas du toml")
    assert installer.changes_since_apply() == [installer.UNREADABLE]
    installer.STATE.write_text(state)
    try:
        installer.delete_backup(bid)
        raise AssertionError("active theme backup was deleted")
    except ValueError:
        pass
    installer.rollback(bid)
    assert installer.changes_since_apply() == []
    installer.STATE.write_text(STATE_SAMPLE)  # back to the sample for the next tests
    installer.delete_backup(bid)
    assert bid not in [b["id"] for b in installer.list_backups()]


def test_user_settings_survive_removal_and_switch():
    installer.STATE.write_text(STATE_SAMPLE)
    bid = installer.apply(ROOT / "themes/vaporwave")
    st = tomllib.loads(installer.STATE.read_text())
    # What a user does while the theme is on: bar to the bottom, dock to the left, a status widget dropped.
    user = installer.STATE.read_text().replace('"status",\n    ', "")
    user += '\n[dock]\nposition = "left"\n'
    user = user.replace("[bar.default]\n", '[bar.default]\nposition = "bottom"\n')
    theme_wall = installer.DATA / "themes" / "vaporwave" / "wallpapers" / "wall_x.webp"
    user += f'\n[wallpaper.monitors.eDP-1]\npath = "{theme_wall}"\n'  # a theme wallpaper: leaves with it
    installer.STATE.write_text(user)
    assert st["bar"]["default"]["end"] == ["status", "tray"]
    installer.apply(INK)  # switch: removes vaporwave first
    after = tomllib.loads(installer.STATE.read_text())
    assert after["bar"]["default"]["position"] == "bottom" and after["dock"]["position"] == "left"
    assert after["bar"]["default"]["end"] == ["tray"]
    assert "monitors" not in after.get("wallpaper", {})
    assert installer.current_theme()["theme"] == "Ink Test"
    installer.rollback(installer.current())  # removal: still there, theme gone
    gone = tomllib.loads(installer.STATE.read_text())
    assert gone["bar"]["default"]["position"] == "bottom" and gone["dock"]["position"] == "left"
    assert gone["theme"]["source"] == "wallpaper"  # the theme's own keys are back to yours
    assert installer.current() is None and bid
    installer.STATE.write_text(STATE_SAMPLE)


def test_setup_backup_restores_everything():
    installer.STATE.write_text(STATE_SAMPLE)
    installer.apply(INK)
    installer.STATE.write_text(installer.STATE.read_text() + '\n[dock]\nposition = "left"\n')
    files = {p: sha(p) for p in [installer.STATE, installer.FRAGMENT, *installer.CONFIG.rglob("*.*")]}
    font = installer.FONTS / "Kalam-Regular.ttf"
    sid = installer.save_setup()
    theme_bid = installer.current()
    installer.apply(ROOT / "themes/vaporwave")  # wander off: other theme, another setting
    installer.STATE.write_text(installer.STATE.read_text() + '\n[idle]\nenabled = false\n')
    assert sid not in installer.excess_backups(0)  # pruning never takes a saved setup
    installer.rollback(sid)
    assert {p: sha(p) for p in files} == files  # byte for byte, theme fragment and widgets included
    assert installer.current() == theme_bid and installer.current_theme()["theme"] == "Ink Test"
    assert font.exists() and not (installer.CONFIG / "palettes/vaporwave.json").exists()
    installer.rollback(theme_bid)  # the theme still comes off cleanly afterwards
    assert installer.current() is None
    installer.STATE.write_text(STATE_SAMPLE)


def test_refresh_keeps_user_changes():
    bid = installer.apply(ROOT / "themes/vaporwave")
    user = installer.STATE.read_text() + '\n[wallpaper.monitors.eDP-1]\npath = "/tmp/mon-fond-a-moi.webp"\n'
    installer.STATE.write_text(user)
    installer.FRAGMENT.write_text("# stale fragment from long ago\n")
    installer.refresh(ROOT / "themes/vaporwave")
    assert installer.STATE.read_text() == user  # state untouched
    assert "vw-player" in installer.FRAGMENT.read_text()
    assert installer.current() == bid
    installer.rollback(bid)


def test_preferences_fragment():
    options.save({**options.DEFAULTS, "hidden_widgets": ["vw-dialog"], "clock_seconds": True, "theme_mode": "light"})
    bid = installer.apply(ROOT / "themes/vaporwave")
    opts = tomllib.loads(installer.OPTIONS.read_text())
    assert "vw-dialog" not in opts["desktop_widgets"]["widget_order"]
    assert opts["desktop_widgets"]["widget"]["vw-clock"]["settings"]["format"] == "{:%H:%M:%S}"
    installer.STATE.write_text(installer.STATE.read_text() + '\n[theme]\nmode = "auto"\n'
                               if "[theme]" not in installer.STATE.read_text()
                               else installer.STATE.read_text().replace("[theme]", '[theme]\nmode = "auto"', 1))
    assert "theme.mode" in installer.overridden_by_state()
    options.save(dict(options.DEFAULTS))
    installer.write_options()
    assert not installer.OPTIONS.exists()  # nothing to override: no file
    options.save({**options.DEFAULTS, "clock_12h": True})
    installer.write_options()
    installer.rollback(bid)
    assert not installer.OPTIONS.exists()
    options.save(dict(options.DEFAULTS))


def test_echoed_preference_is_not_a_user_change():
    options.save({**options.DEFAULTS, "theme_mode": "light"})
    bid = installer.apply(ROOT / "themes/vaporwave")
    echoed = installer.STATE.read_text().replace("[theme]", '[theme]\nmode = "light"', 1)
    installer.STATE.write_text(echoed)  # Noctalia writing the preference back
    assert "theme.mode" not in installer.changes_since_apply()
    installer.rollback(bid)
    options.save(dict(options.DEFAULTS))


def test_excess_backups_spare_active():
    for _ in range(4):
        installer.apply(ROOT / "themes/vaporwave")
    active = installer.current()
    doomed = installer.excess_backups(2)
    assert active not in doomed
    themed = [b for b in installer.list_backups() if b.get("kind") != "setup"]  # saved setups are never pruned
    assert len([b for b in themed if b["id"] not in doomed]) == 2
    installer.rollback(active)


def test_fonts_installed_and_removed():
    font = installer.FONTS / "Kalam-Regular.ttf"
    bid = installer.apply(INK)
    assert sha(font) == sha(INK / "fonts/Kalam-Regular.ttf")
    installer.rollback(bid)
    assert not font.exists()  # created by the theme: gone on rollback


def test_real_settings_parse():
    real = Path.home() / ".local/state/noctalia/settings.toml"
    if real.exists():
        frag = tomllib.loads((ROOT / "themes/vaporwave/noctalia.toml").read_text())
        out = tomllib.loads(installer.strip_overrides(real.read_text(), frag))
        assert "desktop_widgets" not in out and "lockscreen_widgets" in out


FAKE_NOCTALIA = f"""#!{sys.executable}
import json, sys
from pathlib import Path
db = Path(__file__).with_name("wallpaper.json")
args = sys.argv[2:]
with db.with_name("calls.log").open("a") as log:
    log.write(" ".join(args) + "\\n")
if args[0] == "wallpaper-get":
    print(json.loads(db.read_text()) if db.exists() else "")
elif args[0] == "wallpaper-set":
    db.write_text(json.dumps(args[-1]))
"""


def test_wallpaper_follows_backups():
    fake = SANDBOX / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "noctalia").write_text(FAKE_NOCTALIA)
    (fake / "noctalia").chmod(0o755)
    os.environ["PATH"] = str(fake)
    try:
        mine = SANDBOX / "chat-qui-dort.webp"  # the user's own wallpaper, a cat asleep on the keyboard
        mine.write_bytes(b"zzz")
        installer.set_wallpaper(mine)
        installer.apply(ROOT / "themes/vaporwave")
        themed = installer.wallpapers(ROOT / "themes/vaporwave")[0]
        installer.set_wallpaper(themed)
        setup = installer.save_setup()
        installer.rollback(installer.current())  # the theme's wallpaper leaves with it
        assert installer.current_wallpapers() == {"": str(mine)}
        installer.rollback(setup)  # a setup brings its wallpaper back
        assert installer.current_wallpapers() == {"": str(themed)}
        other = SANDBOX / "fond-perso.webp"
        other.write_bytes(b"!")
        installer.set_wallpaper(other)  # picked by hand while themed: kept on removal
        installer.rollback(installer.current())
        assert installer.current_wallpapers() == {"": str(other)}
    finally:
        os.environ["PATH"] = ""


def test_theme_wallpaper_remembered():
    fake = SANDBOX / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "noctalia").write_text(FAKE_NOCTALIA)
    (fake / "noctalia").chmod(0o755)
    os.environ["PATH"] = str(fake)
    try:
        installer.apply(ROOT / "themes/vaporwave")
        walls = installer.wallpapers(ROOT / "themes/vaporwave")
        assert installer.current_wallpapers() == {"": str(walls[0])}  # first visit: the theme's first wallpaper
        installer.set_wallpaper(walls[-1])  # a sunset picked over breakfast
        installer.apply(ROOT / "themes/brume")  # its fragment never names its folder: the manifest does
        fog = installer.wallpapers(ROOT / "themes/brume")
        assert installer.current_wallpapers() == {"": str(fog[0])}
        installer.set_wallpaper(fog[-1])
        installer.apply(ROOT / "themes/vaporwave")
        assert installer.current_wallpapers() == {"": str(walls[-1])}  # back to the one left there
        installer.apply(ROOT / "themes/brume")
        assert installer.current_wallpapers() == {"": str(fog[-1])}
        installer.rollback(installer.current())
    finally:
        os.environ["PATH"] = ""


def test_plugin_installed_and_enabled():
    fake = SANDBOX / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "noctalia").write_text(FAKE_NOCTALIA)
    (fake / "noctalia").chmod(0o755)
    os.environ["PATH"] = str(fake)
    try:
        bid = installer.apply(INK)  # its player and clock are theme-widgets plugin widgets
        dst = installer.NOCTALIA_PLUGINS / "theme-widgets"
        assert sha(dst / "player.luau") == sha(ROOT / "plugins/theme-widgets/player.luau")
        assert "plugins enable billisdead/theme-widgets" in (fake / "calls.log").read_text()
        (dst / "player.luau").write_text("-- stale copy, older than a VHS of the first test run")
        installer.refresh(INK)  # refresh brings the plugin up to date too
        assert sha(dst / "player.luau") == sha(ROOT / "plugins/theme-widgets/player.luau")
        calls = (fake / "calls.log").read_text().splitlines()
        # enabling makes Noctalia save its settings from memory: only once it has reloaded what we wrote
        assert calls[-2:] == ["config-reload", "plugins enable billisdead/theme-widgets"]
        assert not any("disable" in c for c in calls)
        installer.rollback(bid)
    finally:
        os.environ["PATH"] = ""


STALE = """
[desktop_widgets]
enabled = false
widget_order = ["desktop-widget-0000000000000001"]

[desktop_widgets.widget.desktop-widget-0000000000000001]
type = "media_player"
"""


def test_heal_stale_rewrite():
    import json
    import time
    for b in installer.list_backups():  # start theme-free
        if b["id"] == installer.current():
            installer.rollback(b["id"])
    clean = installer.STATE.read_text()
    bid = installer.apply(INK)
    themed = installer.STATE.read_text()
    # Noctalia saves from memory before reloading: the pre-theme widgets come back, the theme's are hidden
    installer.STATE.write_text(themed + STALE)
    assert installer.heal() is True
    assert "desktop_widgets" not in tomllib.loads(installer.STATE.read_text())
    # a layout saved by the editor keeps the theme's ids: left alone
    installer.STATE.write_text(themed + '\n[desktop_widgets.widget.bw-player]\ntype = "x"\ncx = 1.0\n')
    assert installer.heal() is False
    # after the window, nothing is undone (the user may have rebuilt everything by hand)
    exp = json.loads(installer.EXPECT.read_text())
    installer.EXPECT.write_text(json.dumps(exp | {"time": time.time() - installer.HEAL_WINDOW - 1}))
    installer.STATE.write_text(themed + STALE)
    assert installer.heal() is False
    # removing the theme: a stale save would bring the theme's widgets back over the restored desktop
    installer.STATE.write_text(themed)
    installer.rollback(bid)
    stale = tomllib.loads(installer.STATE.read_text())
    stale["desktop_widgets"] = {"widget_order": ["bw-player"], "widget": {"bw-player": {"type": "media_player"}}}
    installer.STATE.write_text(options.dump(stale))
    assert installer.heal() is True
    assert tomllib.loads(installer.STATE.read_text()).get("desktop_widgets") == tomllib.loads(clean).get(
        "desktop_widgets")


def test_plugin_enabled_later():
    import json
    bid = installer.apply(INK)  # Noctalia off (no binary): enabling is postponed
    assert json.loads(installer.EXPECT.read_text())["pending"] == ["billisdead/theme-widgets"]
    fake = SANDBOX / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "noctalia").write_text(FAKE_NOCTALIA)
    (fake / "noctalia").chmod(0o755)
    os.environ["PATH"] = str(fake)
    try:
        installer.heal()  # what the app runs when settings.toml changes or it gets the focus
        assert (fake / "calls.log").read_text().splitlines()[-1] == "plugins enable billisdead/theme-widgets"
        assert json.loads(installer.EXPECT.read_text())["pending"] == []
    finally:
        os.environ["PATH"] = ""
    installer.rollback(bid)


def test_glue_moves_group_together():
    for b in installer.list_backups():  # start theme-free
        if b["id"] == installer.current():
            installer.rollback(b["id"])
    # The shipped themes draw each unit as one widget; the glue still serves themes that group several.
    theme = SANDBOX / "themes" / "glue-test"
    shutil.copytree(INK, theme, dirs_exist_ok=True)
    meta = (theme / "theme.toml").read_text()
    (theme / "theme.toml").write_text(meta.replace('"Quote" = ["bw-quote"]', '"Quote" = ["bw-clock", "bw-quote"]'))
    installer.apply(theme)
    # Noctalia saves a dragged widget as a full table; the quote (same group) was never dragged
    installer.STATE.write_text(installer.STATE.read_text() + """
[desktop_widgets.widget.bw-clock]
type = "billisdead/theme-widgets:clock"
cx = 350.0
cy = 100.0
""")
    assert installer.glue_groups() == ["bw-quote"]
    state, frag = (tomllib.loads(f.read_text()) for f in (installer.STATE, installer.FRAGMENT))
    pos = installer._positions(state, frag)
    qx, qy = (frag["desktop_widgets"]["widget"]["bw-quote"][k] for k in ("cx", "cy"))
    assert pos["bw-quote"] == (qx + 100.0, qy - 50.0)  # clock moved (+100, -50) from (250, 150): same for the quote
    assert pos["bw-player"] == (240.0, 700.0)  # other groups untouched
    assert installer.glue_groups() == []  # idempotent: nothing moves twice
    # now the quote is dragged: the clock follows
    installer.STATE.write_text(installer._set_position(installer.STATE.read_text(), "bw-quote", qx, qy))
    assert installer.glue_groups() == ["bw-clock"]
    state = tomllib.loads(installer.STATE.read_text())["desktop_widgets"]["widget"]
    assert (state["bw-clock"]["cx"], state["bw-clock"]["cy"]) == (250.0, 150.0)
    assert state["bw-clock"]["type"] == "billisdead/theme-widgets:clock"  # the rest of Noctalia's table is kept
    installer.rollback(installer.current())


def test_private_dirs():
    import paths
    paths.DATA.chmod(0o755)  # as an older version left it
    installer.save_setup()
    assert paths.DATA.stat().st_mode & 0o777 == 0o700  # backups hold copies of settings.toml
    options.save(options.load())
    assert paths.SETTINGS.parent.stat().st_mode & 0o777 == 0o700


def test_login_wallpaper_synced():
    fake = SANDBOX / "bin"
    fake.mkdir(exist_ok=True)
    for tool, script in (("noctalia", FAKE_NOCTALIA), ("noctalia-greeter", "#!/bin/sh\n")):
        (fake / tool).write_text(script)
        (fake / tool).chmod(0o755)
    os.environ["PATH"] = str(fake)
    calls, popen = [], installer.subprocess.Popen

    def record(cmd, **kw):  # greeter syncs are only recorded: no Polkit prompt in a test
        if cmd[0] == "pkexec" or cmd[1:] == ["msg", "greeter-sync"]:
            return calls.append(cmd)
        return popen(cmd, **kw)
    installer.subprocess.Popen = record
    installer.GREETER_STAGING = SANDBOX / "greeter-sync"
    try:
        theme = ROOT / "themes/vaporwave"
        installer.apply(theme)
        assert tomllib.loads(installer.OPTIONS.read_text())["shell"]["greeter_sync"]["auto_sync"] is False
        assert calls[-1] == ["pkexec", installer.GREETER_HELPER, "--sync", str(installer.GREETER_STAGING)]
        sync = tomllib.loads((installer.GREETER_STAGING / "sync.toml").read_text())["appearance"]
        assert sync["wallpaper"]["path"] == "/var/lib/noctalia-greeter/wallpaper.webp"
        assert sha(installer.GREETER_STAGING / "wallpaper.webp") == sha(theme / "wallpapers/wall_elevator-sky.webp")
        assert len(sync["palette"]) == 16 and sync["palette"]["on_surface_variant"].startswith("#")
        assert stat.S_IMODE(installer.GREETER_STAGING.stat().st_mode) == 0o700
        installer.rollback(installer.current())  # theme gone: Noctalia's own sync takes the login screen back
        assert calls[-1] == ["noctalia", "msg", "greeter-sync"]
        before = len(calls)
        installer.apply(INK)  # no login wallpaper: auto_sync follows the desktop, as before
        assert tomllib.loads(installer.OPTIONS.read_text())["shell"]["greeter_sync"]["auto_sync"] is True
        assert calls[before:] == []  # Noctalia syncs on its own, the app stays out of it
        installer.rollback(installer.current())
    finally:
        installer.subprocess.Popen = popen
        os.environ["PATH"] = ""


if __name__ == "__main__":
    test_strip()
    test_apply_rollback_roundtrip()
    test_invalid_theme_touches_nothing()
    test_palette_name_cannot_escape()
    test_failure_mid_apply_rolls_back()
    test_restore_older_backup_while_themed()
    test_output_is_substituted()
    test_output_cannot_inject()
    test_changes_since_apply()
    test_user_settings_survive_removal_and_switch()
    test_setup_backup_restores_everything()
    test_refresh_keeps_user_changes()
    test_preferences_fragment()
    test_echoed_preference_is_not_a_user_change()
    test_excess_backups_spare_active()
    test_fonts_installed_and_removed()
    test_real_settings_parse()
    test_wallpaper_follows_backups()
    test_theme_wallpaper_remembered()
    test_plugin_installed_and_enabled()
    test_heal_stale_rewrite()
    test_plugin_enabled_later()
    test_login_wallpaper_synced()
    test_glue_moves_group_together()
    test_private_dirs()
    print("OK", SANDBOX)
