# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_installer.py  (sandboxed in a temp dir, never touches the real session)"""
import hashlib
import os
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="noctalia-themes-test-"))
for var in ("NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_THEMES_HOME"):
    os.environ[var] = str(SANDBOX / var)
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


def test_real_settings_parse():
    real = Path.home() / ".local/state/noctalia/settings.toml"
    if real.exists():
        frag = tomllib.loads((ROOT / "themes/vaporwave/noctalia.toml").read_text())
        out = tomllib.loads(installer.strip_overrides(real.read_text(), frag))
        assert "desktop_widgets" not in out and "lockscreen_widgets" in out


if __name__ == "__main__":
    test_strip()
    test_apply_rollback_roundtrip()
    test_real_settings_parse()
    print("OK", SANDBOX)
