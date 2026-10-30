# SPDX-License-Identifier: GPL-3.0-or-later
"""Every shipped player frame is rebuilt pixel for pixel from its four bands and flat interior."""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from slice_frame import interior, snap  # noqa: E402

for src in sorted(ROOT.glob("themes/*/stickers/*/frame.json")):
    d = src.parent
    m = json.loads(src.read_text())
    x0, t, r, b = m["inset"]
    w, h = m["width"], m["height"]
    orig = Image.open(d.with_suffix(".png")).convert("RGBA")
    assert snap(interior(orig, m["tol"])[0], (w, h), m["scale"]) == (x0, t, w - 1 - r, h - 1 - b), f"{d}: stale bands"
    assert all(v % m["scale"] == 0 for v in m["inset"]), f"{d}: half-pixel band"
    fill = (*bytes.fromhex(m["fill"][1:]), 255) if m["fill"] else (0, 0, 0, 0)
    canvas = Image.new("RGBA", (w, h), fill)
    o = m["overlap"]
    for name, xy in (("top", (0, 0)), ("bottom", (0, h - b - o)), ("left", (0, t)), ("right", (w - r - o, t))):
        canvas.paste(Image.open(d / m["bands"][name]), xy)
    diff = ImageChops.difference(canvas, orig).convert("RGB").getextrema()
    assert max(hi for _lo, hi in diff) <= m["tol"], d  # exact, but for a grain flattened in the interior
    print("ok", d.relative_to(ROOT))
print("OK")
