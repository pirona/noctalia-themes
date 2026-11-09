# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_install.py  (install.sh into a temp HOME, never touches the real one)"""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="noctalia-themes-install-"))
SHARE = HOME / ".local/share"
APP_ID = "com.billisdead.NoctaliaThemes"
env = {**os.environ, "HOME": str(HOME), "XDG_DATA_HOME": str(SHARE), "LANGUAGE": "en"}


def run(*args):
    return subprocess.run([str(ROOT / "install.sh"), *args], env=env, capture_output=True, text=True, check=True).stdout


grudge = SHARE / "noctalia-themes/library/kept-like-a-grudge/theme.toml"  # an imported theme: must outlive uninstall
grudge.parent.mkdir(parents=True)
grudge.write_text('name = "Grudge"\n')

for _ in range(2):  # idempotent: a second run updates in place
    run()
dest = SHARE / "noctalia-themes/app"
files = [HOME / ".local/bin/noctalia-themes", SHARE / f"applications/{APP_ID}.desktop",
         SHARE / f"icons/hicolor/scalable/apps/{APP_ID}.svg", SHARE / f"metainfo/{APP_ID}.metainfo.xml"]
assert all(f.is_file() for f in files), [f for f in files if not f.is_file()]
assert str(dest / "app/main.py") in files[0].read_text() and os.access(files[0], os.X_OK)
assert not list(dest.rglob("__pycache__")) and not list(dest.parent.glob("app.*"))  # no build or swap leftovers
assert (dest.parent.stat().st_mode & 0o777) == 0o700
# The copy finds its own themes and plugins, not the repository's.
out = subprocess.run(["python3", "-c", "import paths; print(paths.THEMES, paths.PLUGINS)"], cwd=dest / "app",
                     env=env, capture_output=True, text=True, check=True).stdout.split()
assert out == [str(dest / "themes"), str(dest / "plugins")] and (dest / "themes/brume/theme.toml").is_file()

run("--uninstall")
assert not any(f.exists() for f in files) and not dest.exists()
assert grudge.is_file()
print("ok")
