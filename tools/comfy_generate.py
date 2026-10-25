#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Queue ONE wallpaper on ComfyUI, wait, fetch it to a buffer dir outside the repo, free the cache.

  tools/comfy_generate.py --prompt-file p.txt --seed 20111209 --name test01 [--steps 24] [--size 1920x1088] [--dry-run]
Env: COMFY_URL (default http://192.168.1.2:8188), WALLPAPER_BUFFER (default ~/Images/noctalia-vaporwave-tampon).
Never interrupts or deletes a job: if the queue is busy, the job just waits its turn.
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://192.168.1.2:8188")
BUFFER = Path(os.environ.get("WALLPAPER_BUFFER", Path.home() / "Images/noctalia-vaporwave-tampon"))
WORKFLOW = Path(__file__).parent / "workflows/flux2_dev_wallpaper_api.json"


def get(path, timeout=30):
    return urllib.request.urlopen(COMFY + path, timeout=timeout).read()


def post(path, body, timeout=60):
    req = urllib.request.Request(COMFY + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def build(prompt, seed, steps, width, height, name):
    if width % 32 or height % 32:
        raise SystemExit(f"Flux.2 wants multiples of 32, got {width}x{height}")
    g = json.loads(WORKFLOW.read_text())
    # Guard: this workflow must stay LoRA-free (parasitic LoRAs were seen in other workflows on this PC).
    if any("lora" in n["class_type"].lower() for n in g.values()):
        raise SystemExit("LoRA node found in workflow: refusing")
    g["prompt"]["inputs"]["text"] = prompt
    g["noise"]["inputs"]["noise_seed"] = seed
    g["sched"]["inputs"].update(steps=steps, width=width, height=height)
    g["latent"]["inputs"].update(width=width, height=height)
    g["save"]["inputs"]["filename_prefix"] = f"noctalia-vaporwave/{name}_s{seed}"
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--name", required=True)
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--size", default="1920x1088")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    width, height = (int(v) for v in a.size.split("x"))
    prompt = a.prompt_file.read_text().strip()
    graph = build(prompt, a.seed, a.steps, width, height, a.name)
    if a.dry_run:
        print(json.dumps(graph, indent=1, ensure_ascii=False))
        return

    version = json.loads(get("/system_stats"))["system"].get("comfyui_version", "?")
    print(f"ComfyUI {version} — {queue_size()} job(s) already queued, ours waits its turn", flush=True)
    # extra_pnginfo.workflow is mandatory: without it comfyui_queue_manager hangs the worker forever.
    body = {"prompt": graph, "client_id": str(uuid.uuid4()),
            "extra_data": {"extra_pnginfo": {"workflow": {
                "id": str(uuid.uuid4()), "workflow_name": f"noctalia_vaporwave_{a.name}_claude",
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

    BUFFER.mkdir(parents=True, exist_ok=True)
    for out in entry["outputs"].values():
        for img in out.get("images", []):
            if img.get("type") != "output":
                continue  # skip previews/temp images
            q = urllib.parse.urlencode({k: img[k] for k in ("filename", "subfolder", "type")})
            dst = BUFFER / img["filename"]
            dst.write_bytes(get(f"/view?{q}", timeout=120))
            meta = {"prompt": prompt, "seed": a.seed, "steps": a.steps, "size": a.size, "comfyui": version,
                    "workflow": WORKFLOW.name, "prompt_id": pid}
            dst.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            print("saved", dst, flush=True)
    # Unload models between jobs: avoids stacking them in the 32 GB of RAM.
    post("/free", {"unload_models": True, "free_memory": True})
    print("cache freed", flush=True)


if __name__ == "__main__":
    main()
