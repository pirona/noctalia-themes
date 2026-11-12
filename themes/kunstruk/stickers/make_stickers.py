#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the Kunstruk stickers (original artwork): python3 make_stickers.py [kunstruk|kunstruk-papier]"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from slice_frame import slice_frame  # noqa: E402

S = 2  # 2x for crisp rendering at fractional scale
INKS = {"kunstruk": ("#E5453A", "#E9E2D4", "#4A4744"), "kunstruk-papier": ("#B42A1F", "#1B1814", "#9A8B6E")}
RED, BONE, GREY = INKS["kunstruk"]
OUT = HERE


def title():
    """KUNSTRUK read upward, standing on a red square: the poster's spine."""
    f = ImageFont.truetype(str(HERE.parent / "fonts/Jost-300-Light.ttf"), 30 * S)
    word = "KUNSTRUK"
    lay = Image.new("RGBA", (1400 * S, 60 * S))
    d, x = ImageDraw.Draw(lay), 0
    for ch in word:
        d.text((x, 0), ch, font=f, fill=BONE)
        x += f.getlength(ch) + 16 * S
    lay = lay.crop(lay.getbbox()).rotate(90, expand=True)
    im = Image.new("RGBA", (lay.width, lay.height + 2 * lay.width))
    im.alpha_composite(lay, (0, 0))
    ImageDraw.Draw(im).rectangle((0, lay.height + lay.width, lay.width - 1, im.height - 1), fill=RED)
    im.save(OUT / "title.png")
    print("title", im.width // S, "x", im.height // S, "logical")


def player_frame():
    """Hairline box with a heavy red bar on the left; interior left transparent for the palette fill."""
    w, h = 380, 112
    im = Image.new("RGBA", (w * S, h * S))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w * S - 1, h * S - 1), outline=GREY, width=S)
    d.rectangle((0, 0, 12 * S - 1, h * S - 1), fill=RED)
    im.save(OUT / "player_frame.png")
    slice_frame(OUT / "player_frame.png", S)  # bands for the theme-widgets plugin


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else "kunstruk"
    RED, BONE, GREY = INKS[theme]
    OUT = HERE.parents[1] / theme / "stickers"
    title()
    player_frame()
