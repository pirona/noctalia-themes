#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Promote a validated render from the buffer: crop to screen, WebP, wall_ prefix, SOURCES.md, Noctalia folder.

  tools/promote_wallpaper.py ~/Images/noctalia-vaporwave-tampon/03-corridor-forest_s20111211_00001_.png corridor-forest
Env: WALLPAPER_DIR (default ~/Images/wallpapers/vaporwave, the folder Noctalia's picker browses).
Re-running with the same name replaces the image and its SOURCES.md entry.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = ROOT / "themes/vaporwave/wallpapers"
USER_DIR = Path(os.environ.get("WALLPAPER_DIR", Path.home() / "Images/wallpapers/vaporwave"))
TARGET = (1920, 1080)


def promote(src, name):
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise SystemExit("name must be lowercase [a-z0-9-]")
    src = Path(src).expanduser()
    meta = json.loads(src.with_suffix(".json").read_text())
    im = Image.open(src).convert("RGB")
    w, h = im.size
    tw, th = TARGET
    scale = max(tw / w, th / h)  # cover, then center crop
    im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((left, top, left + tw, top + th))

    REPO_DIR.mkdir(parents=True, exist_ok=True)
    out = REPO_DIR / f"wall_{name}.webp"
    im.save(out, "WEBP", quality=92, method=6)

    sources = REPO_DIR / "SOURCES.md"
    text = sources.read_text() if sources.exists() else (
        "# Fonds vaporwave — sources\n\nCréations originales générées localement avec ComfyUI "
        "(workflow `tools/workflows/flux2_dev_wallpaper_api.json`, Flux.2 Dev fp8mixed, sans LoRA, "
        "euler + Flux2Scheduler, FluxGuidance 2.0), puis rognées à 1920×1080 et converties en WebP.\n")
    text = re.sub(rf"\n## wall_{name}\.webp\n.*?(?=\n## |\Z)", "", text, flags=re.S)  # replace on re-run
    text += (f"\n## wall_{name}.webp\n\n- graine : `{meta['seed']}` — pas : {meta['steps']} — taille générée : "
             f"{meta['size']} — ComfyUI {meta['comfyui']}\n- rendu source : `{src.name}`\n\n"
             f"> {meta['prompt']}\n")
    sources.write_text(text)

    USER_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, USER_DIR / out.name)
    print(f"{out.relative_to(ROOT)} ({out.stat().st_size // 1024} Ko) -> {USER_DIR / out.name}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    promote(sys.argv[1], sys.argv[2])
