#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate theme palettes: Noctalia silently ignores bad colors, so catch them here."""
import json
import re
import sys
from pathlib import Path

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ROLES = ["Primary", "Secondary", "Tertiary", "Error", "Surface", "SurfaceVariant", "Hover"]
EXTRA = ["mOutline", "mShadow"]
TERM = ["foreground", "background", "selectionFg", "selectionBg", "cursorText", "cursor"]
ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


def luminance(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check(path):
    errors = []
    data = json.loads(Path(path).read_text())
    for mode, v in data.items():
        colors = {f"m{r}": v.get(f"m{r}") for r in ROLES}
        colors |= {f"mOn{r}": v.get(f"mOn{r}") for r in ROLES}
        colors |= {k: v.get(k) for k in EXTRA}
        t = v.get("terminal", {})
        colors |= {f"terminal.{k}": t.get(k) for k in TERM}
        for grp in ("normal", "bright"):
            colors |= {f"terminal.{grp}.{k}": t.get(grp, {}).get(k) for k in ANSI}
        for k, c in colors.items():
            if not isinstance(c, str) or not HEX.match(c):
                errors.append(f"{mode}.{k}: invalid {c!r}")
        pairs = [(f"m{r}", f"mOn{r}") for r in ROLES]
        pairs.append(("terminal.background", "terminal.foreground"))
        for a, b in pairs:
            if HEX.match(str(colors[a])) and HEX.match(str(colors[b])):
                r = contrast(colors[a], colors[b])
                if r < 4.5:
                    errors.append(f"{mode}: {a}/{b} contrast {r:.2f} < 4.5")
    return errors


if __name__ == "__main__":
    assert round(contrast("#000000", "#FFFFFF"), 1) == 21.0
    paths = sys.argv[1:] or sorted(str(p) for p in Path(__file__).resolve().parent.parent.glob("themes/*/palette.json"))
    bad = 0
    for p in paths:
        errs = check(p)
        bad += len(errs)
        print(f"{p}: {'OK' if not errs else ''}")
        for e in errs:
            print("  " + e)
    sys.exit(1 if bad else 0)
