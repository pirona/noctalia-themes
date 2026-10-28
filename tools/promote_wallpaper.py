#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Promote a validated render from the buffer: crop to screen, WebP, wall_ prefix, SOURCES.md, Noctalia folder.

  tools/promote_wallpaper.py ~/Pictures/noctalia-vaporwave-renders/03-corridor-forest_s20111211_00001_.png corridor
  tools/promote_wallpaper.py --theme batman <render.png> <name>
Env: WALLPAPER_DIR (default <Pictures>/wallpapers/<theme>, a folder Noctalia's picker can browse).
Re-running with the same name replaces the image and its SOURCES.md entry.
A comic-panel frame drawn by the model (light margin + border line) is trimmed off automatically.
A theme with `ink = "black-and-white"` in theme.toml gets its wallpapers thresholded to pure ink and paper.
"""
import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import paths  # noqa: E402

TARGET = (1920, 1080)


def frame_inset(gray, side, limit=0.08):
    """Width of a drawn frame on one side: uniform lines from the edge, kept only if the outermost one is light.

    Requiring a light margin keeps a legitimately flat black night sky from being cut.
    """
    w, h = gray.size
    n = round((w if side in "lr" else h) * limit)
    line = {"t": lambda i: (0, i, w, i + 1), "b": lambda i: (0, h - 1 - i, w, h - i),
            "l": lambda i: (i, 0, i + 1, h), "r": lambda i: (w - 1 - i, 0, w - i, h)}[side]
    first = ImageStat.Stat(gray.crop(line(0)))
    if first.mean[0] < 200:
        return 0
    def flat(i):
        return ImageStat.Stat(gray.crop(line(i))).stddev[0] < 14

    i = 0
    while i < n and flat(i) and ImageStat.Stat(gray.crop(line(i))).mean[0] >= 200:
        i += 1  # light paper margin
    if i >= n:
        return 0
    border = i + 10  # then the inked border line, never more: a black scene behind it looks just as flat
    while i < border and flat(i):
        i += 1
    return i + 2  # the antialiased edge of the line


def trim_frame(im):
    g = im.convert("L")
    t, b, left, r = (frame_inset(g, s) for s in "tblr")
    return im.crop((left, t, im.width - r, im.height - b)) if any((t, b, left, r)) else im


def despeckle(hard, area):
    """Flip every black or white island smaller than `area` px: texture left over by the threshold, not drawing."""
    w, h = hard.size
    px = bytearray(hard.tobytes())
    seen = bytearray(w * h)
    for start in range(w * h):
        if seen[start]:
            continue
        color, comp, stack = px[start], [], [start]
        seen[start] = 1
        while stack:
            i = stack.pop()
            comp.append(i)
            x = i % w
            for j in (i - w, i + w, i - 1 if x else -1, i + 1 if x < w - 1 else -1):
                if 0 <= j < w * h and not seen[j] and px[j] == color:
                    seen[j] = 1
                    stack.append(j)
        if len(comp) < area:
            for i in comp:
                px[i] = 255 - color
    return Image.frombytes("L", (w, h), bytes(px))


def black_and_white(im, speck=60):
    """Flux slips greys in: snap to ink or paper, drop specks, keep a 1-2 px soft edge so lines don't jag."""
    hard = im.convert("L").filter(ImageFilter.GaussianBlur(0.7)).point(lambda v: 0 if v < 128 else 255)
    if speck:
        hard = despeckle(hard, speck)
    g = hard.filter(ImageFilter.GaussianBlur(0.7))
    return g.point(lambda v: 0 if v < 112 else 255 if v > 144 else (v - 112) * 255 // 32).convert("RGB")


def promote(src, name, theme="vaporwave"):
    if not re.fullmatch(r"[a-z0-9-]+", name) or not re.fullmatch(r"[a-z0-9-]+", theme):
        raise SystemExit("name and theme must be lowercase [a-z0-9-]")  # both become paths
    src = Path(src).expanduser()
    meta = json.loads(src.with_suffix(".json").read_text())
    repo_dir = ROOT / "themes" / theme / "wallpapers"
    user_dir = Path(os.environ.get("WALLPAPER_DIR", paths.pictures() / "wallpapers" / theme))
    im = trim_frame(Image.open(src).convert("RGB"))
    w, h = im.size
    tw, th = TARGET
    scale = max(tw / w, th / h)  # cover, then center crop
    im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((left, top, left + tw, top + th))
    if tomllib.loads((ROOT / "themes" / theme / "theme.toml").read_text()).get("ink") == "black-and-white":
        im = black_and_white(im)

    repo_dir.mkdir(parents=True, exist_ok=True)
    out = repo_dir / f"wall_{name}.webp"
    im.save(out, "WEBP", quality=92, method=6)

    sources = repo_dir / "SOURCES.md"
    text = sources.read_text() if sources.exists() else (
        f"# {theme} wallpapers — sources\n\nOriginal artwork generated locally with ComfyUI "
        "(workflow `tools/workflows/flux2_dev_wallpaper_api.json`, Flux.2 Dev fp8mixed, no LoRA, "
        "euler + Flux2Scheduler, FluxGuidance 2.0), then cropped to 1920×1080 and converted to WebP.\n")
    text = re.sub(rf"\n## wall_{name}\.webp\n.*?(?=\n## |\Z)", "", text, flags=re.S)  # replace on re-run
    text += (f"\n## wall_{name}.webp\n\n- seed: `{meta['seed']}` — steps: {meta['steps']} — generated size: "
             f"{meta['size']} — ComfyUI {meta['comfyui']}\n- source render: `{src.name}`\n\n"
             f"> {meta['prompt']}\n")
    sources.write_text(text)

    user_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, user_dir / out.name)
    print(f"{out.relative_to(ROOT)} ({out.stat().st_size // 1024} KiB) -> {user_dir / out.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    theme = "vaporwave"
    if args[:1] == ["--theme"]:
        theme, args = args[1], args[2:]
    if len(args) != 2:
        raise SystemExit(__doc__)
    promote(args[0], args[1], theme)
