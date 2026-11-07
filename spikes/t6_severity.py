"""T6 (extra): does a deterministic severity ladder over forged defects produce a detection curve for the inspector?

Each T2 text-style forgery is re-rendered at lower opacity and smaller size with OpenCV only, pasted back into
its full image, and inspected zero-shot (spec text only). A useful headline needs recall to fall off somewhere.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from forge_lib import crop_around
from metaapi import ROOT, RUNS, load_rgb, spark_json
from t1_t2_forge import part_center
from t4_t5_spark import INSPECT, OFFSETS, SPEC, jpg_url

D = ROOT / "data/gate/hazelnut"
F = RUNS / "forge"
OUT = RUNS / "severity"
OUT.mkdir(exist_ok=True)
LEVELS = [("opacity", 1.0), ("opacity", 0.5), ("opacity", 0.25), ("opacity", 0.12), ("size", 0.6), ("size", 0.35), ("size", 0.2)]


def variant(defect, idx, kind, level):
    src = load_rgb(D / f"train/good/{idx:03d}.png")
    cx, cy = part_center(src)
    crop, (x0, y0) = crop_around(src, cx + OFFSETS[idx][0], cy + OFFSETS[idx][1])
    orig = np.array(crop).astype(np.float32)
    comp = np.array(Image.open(F / f"t2_{defect}_text_low_notools_{idx:03d}_composite.png").convert("RGB")).astype(np.float32)
    mask = (np.abs(comp - orig).max(axis=2) > 0).astype(np.float32)
    if kind == "opacity":
        a = mask[..., None] * level
        out = orig + a * (comp - orig)
        area = float(mask.mean())
    else:
        ys, xs = np.nonzero(mask)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        delta = (comp - orig)[by0:by1, bx0:bx1]
        m = mask[by0:by1, bx0:bx1]
        nw, nh = max(2, int((bx1 - bx0) * level)), max(2, int((by1 - by0) * level))
        delta_s = cv2.resize(delta, (nw, nh), interpolation=cv2.INTER_AREA)
        m_s = cv2.resize(m, (nw, nh), interpolation=cv2.INTER_AREA)
        ccx, ccy = (bx0 + bx1) // 2, (by0 + by1) // 2
        px, py = ccx - nw // 2, ccy - nh // 2
        out = orig.copy()
        out[py:py + nh, px:px + nw] += m_s[..., None] * delta_s
        area = float((m_s > 0.5).sum() / mask.size)
    full = src.copy()
    full.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), (x0, y0))
    full.save(OUT / f"{defect}_{idx}_{kind}_{level}.jpg", quality=92)
    return full, area


def run(job):
    defect, idx, kind, level = job
    img, area = variant(defect, idx, kind, level)
    msgs = [{"role": "system", "content": SPEC},
            {"role": "user", "content": [{"type": "text", "text": "Inspect this part."},
                                         {"type": "image_url", "image_url": {"url": jpg_url(img)}}]}]
    r = spark_json(msgs, INSPECT, "inspection", cache_key="hazelnut-gate-C0-v1")["data"]
    return {"defect": defect, "idx": idx, "kind": kind, "level": level, "crop_area_frac": round(area, 4),
            "detected": r["defect"], "pred_type": r["type"], "conf": r["confidence"]}


if __name__ == "__main__":
    jobs = [(d, i, k, l) for d in ("hole", "crack", "print") for i in range(1, 6) for k, l in LEVELS]
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(run, jobs))
    (RUNS / "t6_severity.json").write_text(json.dumps(rows, indent=1))
    print(f"{'defect':6s} " + " ".join(f"{k[:3]}{l:<5}" for k, l in LEVELS))
    for d in ("hole", "crack", "print"):
        cells = []
        for k, l in LEVELS:
            rs = [r for r in rows if r["defect"] == d and r["kind"] == k and r["level"] == l]
            cells.append(f"{sum(r['detected'] for r in rs)}/{len(rs)}".ljust(8))
        print(f"{d:6s} " + " ".join(cells))
    typed = sum(r["pred_type"] == r["defect"] for r in rows if r["detected"])
    print("type correct when detected:", typed, "/", sum(r["detected"] for r in rows))
