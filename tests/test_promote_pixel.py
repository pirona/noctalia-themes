# SPDX-License-Identifier: GPL-3.0-or-later
"""Pixel promotion: only the six greys, 2 px pixels, brightness kept on average, a gradient uses every grey."""
import sys
from pathlib import Path

from PIL import Image, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from promote_wallpaper import pixel  # noqa: E402

fog = Image.new("RGB", (400, 300), (170, 180, 200))  # bluish fog, grey ~179
out = pixel(fog)
rgb = out.tobytes()
assert all(rgb[i] == rgb[i + 1] == rgb[i + 2] for i in range(0, len(rgb), 3))  # no hue left
assert abs(ImageStat.Stat(out.convert("L")).mean[0] - 178) < 6  # the dither averages back to the input
g = out.convert("L")
assert all(g.getpixel((x, y)) == g.getpixel((x | 1, y | 1)) for x in range(0, 400, 7) for y in range(0, 300, 5))  # 2x2 pixels
ramp = Image.linear_gradient("L").resize((512, 256)).convert("RGB")  # dark to light
used = {v for v, n in enumerate(pixel(ramp).convert("L").histogram()) if n}
assert len(used) == 6 and min(used) == 0x1C and max(used) == 0xE6, sorted(used)
print("OK")
