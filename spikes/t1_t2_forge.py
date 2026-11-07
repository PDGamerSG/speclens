"""T1 (settings grid) and T2 (3 defect types x 5 samples x 2 prompt styles + whole-image control).

usage: python spikes/t1_t2_forge.py t1 | t2
"""
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from forge_lib import composite, crop_around, draw_outline, prompt_outline, prompt_text
from metaapi import ROOT, RUNS, image_edit, load_rgb, to_bytes

D = ROOT / "data/gate/hazelnut"


def part_center(img: Image.Image) -> tuple[int, int]:
    g = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    _, o = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    ys, xs = np.nonzero(o)
    return int(xs.mean()), int(ys.mean())


def forge_one(src: Path, defect: str, style: str, strength="low", tools=False, offset=(0, 0), tag=""):
    img = load_rgb(src)
    cx, cy = part_center(img)
    crop, _ = crop_around(img, cx + offset[0], cy + offset[1])
    send = draw_outline(crop, defect) if style == "outline" else crop
    prompt = prompt_outline(defect) if style == "outline" else prompt_text(defect)
    r = image_edit(to_bytes(send, "PNG"), prompt, strength=strength, tools=tools)
    row = {"src": src.name, "defect": defect, "style": style, "strength": strength, "tools": tools,
           "status": r["status"], "ms": round(r["ms"]), "error": (r["error"] or "")[:200], "tag": tag}
    if r["status"] != 200:
        return row
    raw = Image.open(io.BytesIO(r["images"][0])).convert("RGB")
    row["returned_size"] = raw.size
    c = composite(np.array(crop), np.array(raw))
    row.update({k: v for k, v in c.items() if k not in ("composite", "aligned", "mask")})
    out_dir = RUNS / "forge"
    out_dir.mkdir(exist_ok=True)
    name = f"{tag}{defect}_{style}_{strength}_{'tools' if tools else 'notools'}_{src.stem}"
    panel = np.concatenate([np.array(crop), np.array(raw.resize(crop.size)), c["composite"],
                            np.stack([c["mask"] * 255] * 3, -1).astype(np.uint8)], axis=1)
    Image.fromarray(panel).save(out_dir / f"{name}_panel.jpg", quality=88)
    Image.fromarray(c["composite"]).save(out_dir / f"{name}_composite.png")
    row["file"] = name
    return row


def t1():
    src = D / "train/good/000.png"
    jobs = [("low", False), ("low", True), ("high", False), ("high", True)]
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(lambda a: forge_one(src, "hole", "text", a[0], a[1], tag="t1_"), jobs))
    for r in rows:
        print(json.dumps(r))
    (RUNS / "t1_results.json").write_text(json.dumps(rows, indent=1))


def t2(strength="low", tools=False):
    srcs = [D / f"train/good/{i:03d}.png" for i in range(1, 6)]
    offsets = [(0, 0), (-60, 40), (50, -50), (40, 60), (-50, -40)]
    jobs = [(s, d, st, off) for d in ("hole", "crack", "print") for st in ("text", "outline")
            for s, off in zip(srcs, offsets)]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda a: forge_one(a[0], a[1], a[2], strength, tools, a[3], tag="t2_"), jobs))
    # whole-image control: edit the full 1024 image, no crop
    img = load_rgb(D / "train/good/006.png")
    r = image_edit(to_bytes(img, "PNG"), prompt_text("hole").replace("close-up ", ""), strength=strength, tools=tools)
    ctrl = {"control": "whole_image", "status": r["status"], "ms": round(r["ms"])}
    if r["status"] == 200:
        raw = Image.open(io.BytesIO(r["images"][0])).convert("RGB")
        c = composite(np.array(img), np.array(raw))
        ctrl.update({"returned_size": raw.size, **{k: v for k, v in c.items() if k not in ("composite", "aligned", "mask")}})
        Image.fromarray(np.concatenate([np.array(img), np.array(raw.resize(img.size)), c["composite"]], 1)).resize((1536, 512)).save(RUNS / "forge/t2_control_whole_panel.jpg", quality=88)
    rows.append(ctrl)
    for r in rows:
        print(json.dumps(r))
    (RUNS / "t2_results.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    {"t1": t1, "t2": t2}[sys.argv[1]]()
