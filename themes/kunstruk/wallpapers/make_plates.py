#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the Kunstruk plates (original artwork): point, line, plane, type, tension, rest.

  python3 make_plates.py [kunstruk|kunstruk-papier]   # writes into that theme's wallpapers/ (default: kunstruk)
The left ~38 % stays empty: the clock, the title and the player sit there on every plate.
"""
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONTS = HERE.parent / "fonts"
W, H, S = 1920, 1080, 2  # drawn at 2x, downsampled: clean edges without antialias tricks
# ground, red, figure, rule: on paper the bone figures become ink, the black ground becomes yellowed paper
INKS = {"kunstruk": ("#0E0E0E", "#E5453A", "#E9E2D4", "#4A4744"),
        "kunstruk-papier": ("#E6D9BC", "#B42A1F", "#1B1814", "#9A8B6E")}
INK, RED, BONE, GREY = INKS["kunstruk"]


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Jost-{weight}.ttf"), size * S)


def p(*xy):
    """Logical coordinates to drawing pixels."""
    return [v * S for v in xy]


def poly_rot(cx, cy, w, h, deg):
    """Corners of a w x h rectangle centred on (cx, cy), turned by deg."""
    a = math.radians(deg)
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    c, s = math.cos(a), math.sin(a)
    return [((cx + x * c - y * s) * S, (cy + x * s + y * c) * S) for x, y in pts]


def text(im, xy, s, f, fill, deg=0, spacing=0, anchor="la"):
    """Letter-spaced text, optionally turned (deg counter-clockwise) around its anchor corner."""
    lay = Image.new("RGBA", (len(s) * f.size * 2 + 10, f.size * 2), (0, 0, 0, 0))
    d, x = ImageDraw.Draw(lay), 0
    for ch in s:
        d.text((x, 0), ch, font=f, fill=fill)
        x += f.getlength(ch) + spacing * S
    lay = lay.crop(lay.getbbox())
    if deg:
        lay = lay.rotate(deg, expand=True, resample=Image.BICUBIC)
    x0, y0 = xy[0] * S, xy[1] * S
    if anchor == "rb":
        x0, y0 = x0 - lay.width, y0 - lay.height
    im.alpha_composite(lay, (int(x0), int(y0)))


def caption(im, n, word):
    """Plate number bottom right: the only constant of the series."""
    f = font("500-Medium", 17)
    text(im, (W - 124, H - 60), f"N° {n:02d}   {word}", f, BONE, spacing=4, anchor="rb")
    ImageDraw.Draw(im).rectangle(p(W - 124 - 300, H - 52, W - 124, H - 50), fill=GREY)


def plate_point(im, d):
    d.ellipse(p(1330 - 330, 520 - 330, 1330 + 330, 520 + 330), fill=RED)
    d.ellipse(p(1712 - 14, 186 - 14, 1712 + 14, 186 + 14), fill=BONE)  # the point answers the plane
    d.rectangle(p(760, 905, W, 908), fill=BONE)
    caption(im, 1, "PUNKT")


def plate_line(im, d):
    d.polygon(poly_rot(1290, 560, 1500, 64, -28), fill=RED)
    d.polygon(poly_rot(1420, 470, 900, 14, 34), fill=BONE)
    d.polygon(poly_rot(1560, 300, 380, 6, -28), fill=BONE)  # echo of the red, thinner, farther
    caption(im, 2, "LINIE")


def plate_plane(im, d):
    d.rectangle(p(980, 170, 1560, 750), fill=RED)
    d.rectangle(p(1360, 520, 1760, 920), fill=BONE)
    d.rectangle(p(1360, 520, 1560, 750), fill=INK)  # the overlap is cut out, not mixed
    caption(im, 3, "FLÄCHE")


def plate_type(im, d):
    text(im, (1010, 500), "B", font("900-Black", 1000), RED)  # cut by the bottom edge: the letter as a plane
    text(im, (1830, 960), "BAUHAUS   1919", font("300-Light", 40), BONE, deg=90, spacing=22, anchor="rb")
    d.ellipse(p(1690 - 34, 200 - 34, 1690 + 34, 200 + 34), fill=BONE)
    caption(im, 4, "SCHRIFT")


def plate_tension(im, d):
    d.ellipse(p(1340 - 220, 760 - 220, 1340 + 220, 760 + 220), fill=BONE)
    d.polygon(p(1340, 540, 1150, 120, 1610, 200), fill=RED)  # a triangle balanced on its tip
    caption(im, 5, "SPANNUNG")


def plate_rest(im, d):
    gold = H / 1.618
    d.rectangle(p(900, gold - 40, W, gold + 40), fill=RED)
    d.rectangle(p(1520, 120, 1523, H - 120), fill=BONE)
    caption(im, 6, "RUHE")


def plate_rhythm(im, d):
    a, e = 140, 70  # module side, oblique extrusion
    for row in range(3):
        for col in range(4):
            x, y = 900 + col * 230, 150 + row * 260
            d.polygon(p(x, y + a, x + a, y + a, x + a - e, y + a + e, x - e, y + a + e, x - e, y + e, x, y), fill=RED)
            hole = (row, col) == (1, 2)  # one module breaks the series
            d.rectangle(p(x, y, x + a, y + a), fill=INK if hole else BONE, outline=BONE if hole else None,
                        width=3 * S)
    caption(im, 7, "RHYTHMUS")


def plate_interference(im, d):
    cx, cy, r = 1320, 520, 330
    bars = Image.new("L", im.size)
    db = ImageDraw.Draw(bars)
    for x in range(820, 1830, 56):
        db.rectangle(p(x, 110, x + 26, 950), fill=255)
    disc = Image.new("L", im.size)
    ImageDraw.Draw(disc).ellipse(p(cx - r, cy - r, cx + r, cy + r), fill=255)
    im.paste(BONE, mask=ImageChops.subtract(bars, disc))  # bars outside the disc
    im.paste(RED, mask=ImageChops.subtract(disc, bars))  # the disc shows between the bars, which go dark over it
    caption(im, 8, "INTERFERENZ")


def plate_balance(im, d):
    cx = 1330
    d.ellipse(p(cx - 80, 140, cx + 80, 300), fill=BONE)
    for r in range(24, 204, 14):  # a bowl of concentric half rings
        d.arc(p(cx - r, 310 - r, cx + r, 310 + r), 0, 180, fill=RED, width=3 * S)
    d.pieslice(p(cx - 220, 540, cx + 220, 980), 180, 360, fill=BONE)
    for r in range(12, 84, 12):
        d.ellipse(p(cx - r, 860 - r, cx + r, 860 + r), outline=RED, width=3 * S)
    caption(im, 9, "GLEICHGEWICHT")


def plate_eye(im, d):
    cx, cy, w, h = 1330, 600, 540, 210
    rr = (w * w / 4 + h * h / 4) / h  # radius of the two arcs that make the almond
    lo, hi = cy + rr - h / 2, cy - rr + h / 2  # centre of the upper lid's circle (below), of the lower lid's (above)
    lens, other = Image.new("L", im.size), Image.new("L", im.size)
    ImageDraw.Draw(lens).ellipse(p(cx - rr, lo - rr, cx + rr, lo + rr), fill=255)
    ImageDraw.Draw(other).ellipse(p(cx - rr, hi - rr, cx + rr, hi + rr), fill=255)
    im.paste(BONE, mask=ImageChops.multiply(lens, other))
    for x in range(cx - 210, cx + 210, 36):  # lashes stop short of the upper lid
        y = lo - math.sqrt(rr * rr - (x + 8 - cx) ** 2)
        d.rectangle(p(x, 300, x + 16, y - 16), fill=BONE)
    d.ellipse(p(cx - 82, cy - 82, cx + 82, cy + 82), fill=RED)
    d.ellipse(p(cx - 36, cy - 36, cx + 36, cy + 36), fill=INK)
    caption(im, 10, "AUGE")


PLATES = {"punkt": plate_point, "linie": plate_line, "flaeche": plate_plane,
          "schrift": plate_type, "spannung": plate_tension, "ruhe": plate_rest,
          "rhythmus": plate_rhythm, "interferenz": plate_interference, "gleichgewicht": plate_balance,
          "auge": plate_eye}


def grain(im):
    """Fixed paper grain, so a re-run gives the same file."""
    rnd = random.Random(1919)  # Bauhaus founding year
    tile = Image.frombytes("L", (256, 256), rnd.randbytes(256 * 256)).point(lambda v: 128 + (v - 128) // 18)
    noise = Image.new("L", im.size)
    for y in range(0, im.height, 256):
        for x in range(0, im.width, 256):
            noise.paste(tile, (x, y))
    return ImageChops.overlay(im, Image.merge("RGB", [noise] * 3))  # grey 128 = no change


def age(im):
    """Old paper: the edges yellow and darken, the centre stays pale."""
    r = Image.radial_gradient("L").resize(im.size, Image.BICUBIC).point(lambda v: max(0, v - 90) * 255 // 165)
    return Image.composite(ImageChops.multiply(im, Image.new("RGB", im.size, "#D9C28E")), im, r)


def main(theme):
    global INK, RED, BONE, GREY
    INK, RED, BONE, GREY = INKS[theme]
    out = HERE.parents[1] / theme / "wallpapers"
    for name, draw in PLATES.items():
        im = Image.new("RGBA", (W * S, H * S), INK)
        draw(im, ImageDraw.Draw(im))
        flat = im.convert("RGB").resize((W, H), Image.LANCZOS)
        flat = grain(age(flat) if theme == "kunstruk-papier" else flat)
        flat.save(out / f"wall_{name}.webp", quality=92, method=6)
        print(out / f"wall_{name}.webp")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kunstruk")
