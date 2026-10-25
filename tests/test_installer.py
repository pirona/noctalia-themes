# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_installer.py  (sandboxed in a temp dir, never touches the real session)"""
import hashlib
import os
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="noctalia-themes-test-"))
for var in ("NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_THEMES_HOME"):
    os.environ[var] = str(SANDBOX / var)
os.environ["NOCTALIA_THEMES_OUTPUT"] = "CRT-1985"
os.environ["PATH"] = ""  # no noctalia binary: config-reload becomes a no-op
sys.path.insert(0, str(ROOT / "app"))
import installer  # noqa: E402

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
    assert installer.changes_since_apply() == []
    state = installer.STATE.read_text()
    state = state.replace('builtin = "Noctalia"', 'builtin = "Synthwave du dimanche"')
    state += '\n[wallpaper.last]\npath = "/tmp/rotation.png"\n'  # Noctalia's own noise
    installer.STATE.write_text(state)
    assert installer.changes_since_apply() == ["theme.builtin"]
    echoed = state + '\n[desktop_widgets]\nenabled = true\n'  # theme value written back by Noctalia
    echoed += '\n[wallpaper.monitors.eDP-1]\npath = "/tmp/choix-perso.png"\n'  # a real user choice
    installer.STATE.write_text(echoed)
    assert installer.changes_since_apply() == ["theme.builtin", "wallpaper.monitors.eDP-1.path"]
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
    installer.delete_backup(bid)
    assert bid not in [b["id"] for b in installer.list_backups()]


def test_real_settings_parse():
    real = Path.home() / ".local/state/noctalia/settings.toml"
    if real.exists():
        frag = tomllib.loads((ROOT / "themes/vaporwave/noctalia.toml").read_text())
        out = tomllib.loads(installer.strip_overrides(real.read_text(), frag))
        assert "desktop_widgets" not in out and "lockscreen_widgets" in out


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
    test_real_settings_parse()
    print("OK", SANDBOX)
