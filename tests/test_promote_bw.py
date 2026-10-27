# SPDX-License-Identifier: GPL-3.0-or-later
"""Black-and-white promotion: greys and colours snap to ink or paper; only a thin edge stays soft."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from promote_wallpaper import black_and_white  # noqa: E402

im = Image.new("RGB", (200, 100), (200, 190, 160))  # warm paper-ish
ImageDraw.Draw(im).rectangle((100, 0, 199, 99), fill=(40, 60, 90))  # bluish ink
out = black_and_white(im)
px = out.load()
assert px[20, 50] == (255, 255, 255) and px[180, 50] == (0, 0, 0)
rgb = out.tobytes()
assert all(rgb[i] == rgb[i + 1] == rgb[i + 2] for i in range(0, len(rgb), 3))  # no hue left
soft = sum(1 for v in rgb[::3] if 0 < v < 255)
assert soft <= 4 * 100, soft  # edge only: a few px wide along the 100 px boundary
# A 3x3 speck of paper inside the ink is texture, not drawing: it goes; a real window (20x20) stays.
im2 = Image.new("RGB", (120, 60), (0, 0, 0))
d = ImageDraw.Draw(im2)
d.rectangle((10, 10, 12, 12), fill=(255, 255, 255))
d.rectangle((60, 20, 79, 39), fill=(255, 255, 255))
out2 = black_and_white(im2).load()
assert out2[11, 11] == (0, 0, 0) and out2[70, 30] == (255, 255, 255)
print("OK")
