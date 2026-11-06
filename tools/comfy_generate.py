#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Queue ONE wallpaper on ComfyUI, wait, fetch it to a buffer dir outside the repo, free the cache.

  tools/comfy_generate.py --setup        # once: server address and model files, saved to the config file
  tools/comfy_generate.py --prompt-file p.txt --seed 20111209 --name test01 [--theme vaporwave]
      [--steps 24] [--size 1920x1088] [--dry-run]
Config: ~/.config/noctalia-themes/comfyui.toml (url, unet, clip, vae); COMFY_URL overrides the url.
Env: WALLPAPER_BUFFER (default <Pictures>/noctalia-<theme>-renders).
Never interrupts or deletes a job: if the queue is busy, the job just waits its turn.
"""
import argparse
import json
import os
import sys
import time
import tomllib
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import paths  # noqa: E402

WORKFLOW = Path(__file__).parent / "workflows/flux2_dev_wallpaper_api.json"
CONFIG = paths.SETTINGS.parent / "comfyui.toml"
# Flux.2 Dev files as ComfyUI names them; a copy in a subfolder (e.g. FLUX2/) is found by its file name.
DEFAULTS = {"url": "http://127.0.0.1:8188", "unet": "flux2_dev_fp8mixed.safetensors",
            "clip": "mistral_3_small_flux2_fp8.safetensors", "vae": "flux2-vae.safetensors"}
LOADERS = {"unet": ("UNETLoader", "unet_name"), "clip": ("CLIPLoader", "clip_name"), "vae": ("VAELoader", "vae_name")}
LABELS = {"unet": "Diffusion model (Flux.2 Dev)", "clip": "Text encoder (Mistral 3 Small for Flux.2)",
          "vae": "VAE (Flux.2)"}
COMFY = DEFAULTS["url"]  # set from the config in main()


def load_config():
    """Defaults, then the config file, then COMFY_URL."""
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        saved = tomllib.loads(CONFIG.read_text())
        cfg |= {k: v for k, v in saved.items() if k in DEFAULTS and isinstance(v, str) and v}
    cfg["url"] = (os.environ.get("COMFY_URL") or cfg["url"]).rstrip("/")
    return cfg


def save_config(cfg):
    paths.ensure_dir(CONFIG.parent)
    CONFIG.write_text("# ComfyUI settings for tools/comfy_generate.py (rewrite with --setup)\n"
                      + "".join(f"{k} = {json.dumps(cfg[k])}\n" for k in DEFAULTS))


def _basename(name):
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def models(key):
    """Model files the ComfyUI server offers for one loader."""
    cls, field = LOADERS[key]
    spec = json.loads(get(f"/object_info/{cls}"))[cls]["input"]["required"][field]
    return spec[0] if isinstance(spec[0], list) else spec[1].get("options", [])  # older vs COMBO format


def resolve(name, offered):
    """The server's name for a model: exact, else same file name in another folder; None if missing."""
    return name if name in offered else next((o for o in offered if _basename(o) == _basename(name)), None)


def setup():
    """Ask for the server, pick each model among the files it offers, save. Enter keeps the proposal."""
    cfg = load_config()
    ask = input if sys.stdin.isatty() else (lambda _prompt: "")
    global COMFY
    COMFY = (ask(f"ComfyUI address [{cfg['url']}]: ").strip() or cfg["url"]).rstrip("/")
    try:
        version = json.loads(get("/system_stats"))["system"].get("comfyui_version", "?")
    except (OSError, ValueError) as e:
        raise SystemExit(f"ComfyUI does not answer at {COMFY}: {e}") from e
    print(f"ComfyUI {version} at {COMFY}")
    cfg["url"] = COMFY
    for key in LOADERS:
        offered = models(key)
        if not offered:
            raise SystemExit(f"ComfyUI offers no {key} model: install the Flux.2 Dev files first")
        guess = resolve(cfg[key], offered) or next((o for o in offered if "flux2" in o.lower()), offered[0])
        print(LABELS[key])
        for i, o in enumerate(offered, 1):
            print(f"  {i:>2}. {o}")
        answer = ask(f"{LABELS[key]}, number or name [{guess}]: ").strip()
        cfg[key] = offered[int(answer) - 1] if answer.isdigit() and 0 < int(answer) <= len(offered) else (
            answer or guess)
    save_config(cfg)
    print(f"saved to {CONFIG}")


def get(path, timeout=30):
    return urllib.request.urlopen(COMFY + path, timeout=timeout).read()


def post(path, body, timeout=60):
    req = urllib.request.Request(COMFY + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def build(prompt, seed, steps, width, height, name, theme="vaporwave", files=None):
    if width % 32 or height % 32:
        raise SystemExit(f"Flux.2 wants multiples of 32, got {width}x{height}")
    g = json.loads(WORKFLOW.read_text())
    # Guard: the wallpaper style comes from the prompt alone; a LoRA slipped into the workflow would change it.
    if any("lora" in n["class_type"].lower() for n in g.values()):
        raise SystemExit("LoRA node found in workflow: refusing")
    for key, fname in (files or {}).items():
        cls, field = LOADERS[key]
        g[key]["inputs"][field] = fname
    g["prompt"]["inputs"]["text"] = prompt
    g["noise"]["inputs"]["noise_seed"] = seed
    g["sched"]["inputs"].update(steps=steps, width=width, height=height)
    g["latent"]["inputs"].update(width=width, height=height)
    g["save"]["inputs"]["filename_prefix"] = f"noctalia-{theme}/{name}_s{seed}"
    return g


def queue_size():
    q = json.loads(get("/queue"))
    n = len(q["queue_running"]) + len(q["queue_pending"])
    try:  # comfyui_queue_manager holds some jobs outside /queue
        held = json.loads(get("/queue_manager/queue"))
        n += len(held.get("pending", []))
    except (OSError, ValueError):
        pass
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help=f"set the ComfyUI address and model files ({CONFIG})")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--name")
    ap.add_argument("--theme", default="vaporwave")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--size", default="1920x1088")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.setup:
        return setup()
    if not a.prompt_file or a.seed is None or not a.name:
        ap.error("--prompt-file, --seed and --name are required (or --setup)")
    cfg = load_config()
    global COMFY
    COMFY = cfg["url"]
    files = {k: cfg[k] for k in LOADERS}
    width, height = (int(v) for v in a.size.split("x"))
    prompt = a.prompt_file.read_text().strip()
    if a.dry_run:
        print(json.dumps(build(prompt, a.seed, a.steps, width, height, a.name, a.theme, files),
                         indent=1, ensure_ascii=False))
        return

    hint = f"run tools/comfy_generate.py --setup (config: {CONFIG})"
    try:
        version = json.loads(get("/system_stats"))["system"].get("comfyui_version", "?")
    except (OSError, ValueError) as e:
        raise SystemExit(f"ComfyUI does not answer at {COMFY}: {e}\n{hint}") from e
    for key in LOADERS:
        found = resolve(files[key], models(key))
        if not found:
            raise SystemExit(f"{key} model {files[key]} not found on ComfyUI at {COMFY}: {hint}")
        files[key] = found
    graph = build(prompt, a.seed, a.steps, width, height, a.name, a.theme, files)
    print(f"ComfyUI {version} — {queue_size()} job(s) already queued, ours waits its turn", flush=True)
    # extra_pnginfo.workflow is mandatory: without it comfyui_queue_manager hangs the worker forever.
    body = {"prompt": graph, "client_id": str(uuid.uuid4()),
            "extra_data": {"extra_pnginfo": {"workflow": {
                "id": str(uuid.uuid4()), "workflow_name": f"noctalia_{a.theme}_{a.name}",
                "nodes": [], "links": []}}}}
    pid = json.loads(post("/prompt", body))["prompt_id"]
    print("queued", pid, flush=True)

    start = time.monotonic()
    while True:
        try:
            hist = json.loads(get(f"/history/{pid}", timeout=60))
            if pid in hist:
                break
        except OSError:
            pass  # ComfyUI answers slowly while sampling: retry
        time.sleep(15)
        print(f"  waiting… {int(time.monotonic() - start)} s", flush=True)
    entry = hist[pid]
    print("status:", entry["status"]["status_str"], f"({int(time.monotonic() - start)} s)", flush=True)

    buffer = Path(os.environ.get("WALLPAPER_BUFFER", paths.pictures() / f"noctalia-{a.theme}-renders"))
    buffer.mkdir(parents=True, exist_ok=True)
    for out in entry["outputs"].values():
        for img in out.get("images", []):
            if img.get("type") != "output":
                continue  # skip previews/temp images
            q = urllib.parse.urlencode({k: img[k] for k in ("filename", "subfolder", "type")})
            dst = buffer / img["filename"]
            dst.write_bytes(get(f"/view?{q}", timeout=120))
            meta = {"prompt": prompt, "seed": a.seed, "steps": a.steps, "size": a.size, "comfyui": version,
                    "workflow": WORKFLOW.name, "prompt_id": pid}
            dst.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            print("saved", dst, flush=True)
    # Unload models between jobs: keeps RAM free on the ComfyUI host.
    post("/free", {"unload_models": True, "free_memory": True})
    print("cache freed", flush=True)


if __name__ == "__main__":
    main()
