#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the vaporwave stickers (original artwork). Run from anywhere: python3 make_stickers.py"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from slice_frame import slice_frame  # noqa: E402

CJK = "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"
S = 2  # 2x for crisp rendering at fractional scale
PINK, CYAN = (255, 113, 206), (1, 205, 254)
TITLE_H = 26  # title bar bottom, in logical px


def font(size, bold=False):
    f = ImageFont.truetype(CJK, size * S, index=0)  # index 0 = JP
    f.set_variation_by_name("Bold" if bold else "Regular")
    return f


def blend(t):
    """Pink-to-cyan gradient color at t in [0, 1]."""
    return tuple(int(a + (b - a) * t) for a, b in zip(PINK, CYAN, strict=True))


def bevel(d, box, raised=True, fill="#C0C0C0"):
    x0, y0, x1, y1 = box
    hi, lo = ("#FFFFFF", "#404040") if raised else ("#404040", "#FFFFFF")
    if fill:
        d.rectangle(box, fill=fill)
    d.line([(x0, y1), (x0, y0), (x1, y0)], fill=hi, width=S * 2)
    d.line([(x0, y1), (x1, y1), (x1, y0)], fill=lo, width=S * 2)


def window(w, h, title):
    """Win95-style frame with a pink-to-cyan title bar and a centered close button."""
    im = Image.new("RGBA", (w * S, h * S))
    d = ImageDraw.Draw(im)
    bevel(d, (0, 0, w * S - 1, h * S - 1))
    for x in range(4 * S, (w - 4) * S):
        d.line([(x, 4 * S), (x, TITLE_H * S)], fill=blend(x / (w * S)))
    d.text((10 * S, 15 * S), title, font=font(13, True), fill="#FFFFFF", anchor="lm")
    bx0, by0, bx1, by1 = (w - 24) * S, 7 * S, (w - 8) * S, 23 * S
    bevel(d, (bx0, by0, bx1, by1))
    cx, cy, r = (bx0 + bx1) // 2, (by0 + by1) // 2, 4 * S  # cross drawn, not typed: exact centering
    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill="#000000", width=2 * S)
    d.line([(cx - r, cy + r), (cx + r, cy - r)], fill="#000000", width=2 * S)
    return im, d


def dialog():
    w, h = 380, 170
    im, d = window(w, h, "ＡＥＳＴＨＥＴＩＣＳ．ＥＸＥ")
    d.text((20 * S, 46 * S), "あの夏の午後を読み込んでいます…", font=font(14), fill="#000000")
    # progress bar stuck at 99 %
    x0, y0, x1, y1 = 20 * S, 76 * S, (w - 20) * S, 96 * S
    bevel(d, (x0, y0, x1, y1), raised=False, fill="#FFFFFF")
    block, gap, end = 10 * S, 3 * S, x0 + int((x1 - x0 - 6 * S) * 0.99)
    x = x0 + 3 * S
    while x + block <= end:
        d.rectangle((x, y0 + 4 * S, x + block, y1 - 4 * S), fill=blend((x - x0) / (x1 - x0)))
        x += block + gap
    d.text((20 * S, 104 * S), "残り時間：永遠", font=font(12), fill="#000000")
    bx = w // 2 - 50
    bevel(d, (bx * S, 128 * S, (bx + 100) * S, 156 * S))
    d.text(((bx + 50) * S, 142 * S), "キャンセル", font=font(12), fill="#000000", anchor="mm")
    im.save(HERE / "dialog-loading.png")


def player_frame():
    """Window chrome around Noctalia's media_player widget: the content area is transparent."""
    w, h = 340, 150
    im, d = window(w, h, "♪ ＣＤプレーヤー")
    d.rectangle((6 * S, (TITLE_H + 4) * S, (w - 6) * S, (h - 6) * S), fill=(0, 0, 0, 0))
    bevel(d, (6 * S, (TITLE_H + 4) * S, (w - 6) * S, (h - 6) * S), raised=False, fill=None)
    im.save(HERE / "player_frame.png")


if __name__ == "__main__":
    dialog()
    player_frame()
    slice_frame(HERE / "player_frame.png", S)  # bands for the theme-widgets plugin
    assert Image.open(HERE / "dialog-loading.png").size == (380 * S, 170 * S)
    assert Image.open(HERE / "player_frame.png").getpixel((170 * S, 90 * S))[3] == 0  # hole is transparent
