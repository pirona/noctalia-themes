# SPDX-License-Identifier: GPL-3.0-or-later
"""Grain promotion: colour goes, brightness stays, grain is visible but light, and the same name gives the same file."""
import sys
from pathlib import Path

from PIL import Image, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from promote_wallpaper import grain  # noqa: E402

fog = Image.new("RGB", (400, 300), (170, 180, 200))  # bluish fog, grey ~179
out = grain(fog, "hazy-peak")
rgb = out.tobytes()
assert all(rgb[i] == rgb[i + 1] == rgb[i + 2] for i in range(0, len(rgb), 3))  # no hue left
st = ImageStat.Stat(out.convert("L"))
assert abs(st.mean[0] - 178) < 3, st.mean  # grain adds texture, not light
assert 3 < st.stddev[0] < 15, st.stddev  # seen up close, not snow
assert grain(fog, "hazy-peak").tobytes() == rgb  # re-running a promotion rewrites the same file
assert grain(fog, "other").tobytes() != rgb
print("OK")
