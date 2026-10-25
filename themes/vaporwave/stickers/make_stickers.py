#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the vaporwave stickers (original artwork). Run from anywhere: python3 make_stickers.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
CJK = "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"
S = 2  # 2x for crisp rendering at fractional scale


def font(size, bold=False):
    f = ImageFont.truetype(CJK, size * S, index=0)  # index 0 = JP
    f.set_variation_by_name("Bold" if bold else "Regular")
    return f


def bevel(d, box, raised=True):
    x0, y0, x1, y1 = box
    hi, lo = ("#FFFFFF", "#404040") if raised else ("#404040", "#FFFFFF")
    d.rectangle(box, fill="#C0C0C0")
    d.line([(x0, y1), (x0, y0), (x1, y0)], fill=hi, width=S * 2)
    d.line([(x0, y1), (x1, y1), (x1, y0)], fill=lo, width=S * 2)


def dialog():
    w, h = 380 * S, 170 * S
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    bevel(d, (0, 0, w - 1, h - 1))
    # title bar: pink to cyan instead of the stock navy
    for x in range(4 * S, w - 4 * S):
        t = x / w
        c = tuple(int(a + (b - a) * t) for a, b in zip((255, 113, 206), (1, 205, 254)))
        d.line([(x, 4 * S), (x, 26 * S)], fill=c)
    d.text((10 * S, 6 * S), "ＡＥＳＴＨＥＴＩＣＳ．ＥＸＥ", font=font(13, True), fill="#FFFFFF")
    bevel(d, (w - 24 * S, 7 * S, w - 8 * S, 23 * S))
    d.text((w - 20 * S, 4 * S), "×", font=font(14, True), fill="#000000")
    # info icon
    d.ellipse((16 * S, 42 * S, 52 * S, 78 * S), fill="#01CDFE", outline="#000000", width=S)
    d.text((29 * S, 44 * S), "i", font=font(22, True), fill="#FFFFFF")
    d.text((66 * S, 40 * S), "Voulez-vous vraiment être nostalgique\nd'une époque que vous n'avez pas vécue ?",
           font=font(12), fill="#000000", spacing=6 * S)
    for i, label in enumerate(("Oui", "はい")):
        x = w // 2 - 110 * S + i * 120 * S
        bevel(d, (x, 120 * S, x + 100 * S, 150 * S))
        tw = d.textlength(label, font=font(12))
        d.text((x + 50 * S - tw / 2, 125 * S), label, font=font(12), fill="#000000")
    im.save(HERE / "dialog.png")


if __name__ == "__main__":
    dialog()
    assert Image.open(HERE / "dialog.png").size == (380 * S, 170 * S)
