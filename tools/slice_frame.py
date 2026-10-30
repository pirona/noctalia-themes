#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cut a drawn frame into four bands around its flat interior, for the now-playing plugin.

  tools/slice_frame.py themes/vaporwave/stickers/player_frame.png
Writes <frame>/top.png, bottom.png, left.png, right.png and frame.json next to the image (folder named after it).
Plugin UIs cannot stack an image under content, so the bands are laid around it and the interior is a flat fill.
--scale is image pixels per logical pixel (stickers are drawn at 2x).
"""
import argparse
import json
from pathlib import Path

from PIL import Image


def interior(im, tol=12):
    """Largest uniform rectangle grown from the centre, then shrunk until no stroke pixel is left inside."""
    w, h = im.size
    px = im.load()
    cx, cy = w // 2, h * 3 // 5  # below a title band
    fill = px[cx, cy]

    def same(x, y):
        return max(abs(a - b) for a, b in zip(px[x, y], fill, strict=False)) < tol

    x0, r, t, b = cx, cx, cy, cy
    while x0 > 0 and same(x0 - 1, cy):
        x0 -= 1
    while r < w - 1 and same(r + 1, cy):
        r += 1
    while t > 0 and same(cx, t - 1):
        t -= 1
    while b < h - 1 and same(cx, b + 1):
        b += 1
    moved = True
    while moved and x0 < r and t < b:
        moved = False
        if not all(same(x0, y) for y in range(t, b + 1)):
            x0, moved = x0 + 1, True
        if not all(same(r, y) for y in range(t, b + 1)):
            r, moved = r - 1, True
        if not all(same(x, t) for x in range(x0, r + 1)):
            t, moved = t + 1, True
        if not all(same(x, b) for x in range(x0, r + 1)):
            b, moved = b - 1, True
    return (x0, t, r, b), fill


def slice_frame(src, scale=2):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    (x0, t, r, b), fill = interior(im)
    out = src.with_suffix("")
    out.mkdir(exist_ok=True)
    bands = {"top": (0, 0, w, t), "bottom": (0, b + 1, w, h), "left": (0, t, x0, b + 1), "right": (r + 1, t, w, b + 1)}
    for name, box in bands.items():
        im.crop(box).save(out / f"{name}.png")
    meta = {
        "scale": scale,
        "width": w,
        "height": h,
        "inset": [x0, t, w - 1 - r, h - 1 - b],  # left, top, right, bottom in image pixels
        "fill": None if fill[3] == 0 else "#{:02x}{:02x}{:02x}".format(*fill[:3]),  # None: theme colour shows through
    }
    (out / "frame.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("frame", type=Path)
    ap.add_argument("--scale", type=float, default=2)
    a = ap.parse_args()
    print(json.dumps(slice_frame(a.frame, a.scale)))
