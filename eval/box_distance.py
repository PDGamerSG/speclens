"""Post-hoc sensitivity check on the located curves: when the inspector flags a defect but its box misses the mask,
how far off is it? No API calls; reads the stored boxes from the revalidation passes.

Writes docs/results/box_distance.json. A flagged variant counts as "near" when the box comes within TOL_MM of the defect.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import parts as parts_mod  # noqa: E402
from app.config import RESULTS  # noqa: E402
from app.forge import severity as sev  # noqa: E402
from app.forge.locate import load_image, part_width  # noqa: E402
from app.runs import RUNS  # noqa: E402

RAW = RESULTS / "raw"
TOL_MM = 1.0
PASSES = 3


def box_gap_px(box, mask) -> float:
    """Distance from the box to the nearest defect pixel (0 if they overlap)."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return float("inf")
    x0, y0, x1, y1 = box
    dx = np.maximum(np.maximum(x0 - xs, xs - x1), 0)
    dy = np.maximum(np.maximum(y0 - ys, ys - y1), 0)
    return float(np.sqrt(dx * dx + dy * dy).min())


def main():
    rid = json.loads((RAW / "forge_run.json").read_text())["run_id"]
    run = json.loads((RUNS / rid / "run.json").read_text())
    sd = RUNS / rid / "samples"
    acc = {s["id"]: s for s in run["samples"] if s["status"] == "accepted"}
    passes = [json.loads((RAW / f"stress_v2_pass{n}.json").read_text()) for n in range(1, PASSES + 1)]
    cache: dict = {}

    def variant_mask(sid, kind, level):
        k = (sid, kind, level)
        if k not in cache:
            s = acc[sid]
            prov = json.loads((sd / f"{sid}_provenance.json").read_text())
            x0, y0, x1, y1 = prov["crop_box"]
            fmask = np.array(Image.open(sd / f"{sid}_mask.png")) > 0
            full = np.array(Image.open(sd / f"{sid}_composite.png").convert("RGB"))[y0:y1, x0:x1]
            base = load_image(parts_mod.all_parts()[s["part_id"]]["path"])
            orig = np.array(base.crop((x0, y0, x1, y1)))
            _, vm = sev.variant(orig, full, fmask[y0:y1, x0:x1], kind, level)
            m = np.zeros(fmask.shape, bool)
            m[y0:y1, x0:x1] = vm
            cache[k] = (m, 20.0 / part_width(parts_mod.get_mask(s["part_id"])))
        return cache[k]

    rows: dict = {}
    for p in passes:
        for pt in p["points"]:
            key = (pt["defect_type"], pt["kind"], pt["level"], pt["sample_id"])
            gap = None
            if pt["flagged"] and pt["box_px"]:
                m, mm_per_px = variant_mask(pt["sample_id"], pt["kind"], pt["level"])
                gap = box_gap_px(pt["box_px"], m) * mm_per_px
            rows.setdefault(key, []).append(gap)
    cells: dict = {}
    for (t, kind, level, _sid), gaps in rows.items():
        near = sum(g is not None and g <= TOL_MM for g in gaps) * 2 > len(gaps)
        hit = sum(g == 0 for g in gaps if g is not None) * 2 > len(gaps)
        c = cells.setdefault((t, kind, level), {"type": t, "kind": kind, "level": level, "n": 0, "overlap": 0, "near": 0, "gaps_mm": []})
        c["n"] += 1
        c["overlap"] += hit
        c["near"] += near
        c["gaps_mm"] += [g for g in gaps if g]
    out = []
    for c in cells.values():
        g = c.pop("gaps_mm")
        c["median_miss_mm"] = round(float(np.median(g)), 2) if g else None
        out.append(c)
    out.sort(key=lambda c: (c["type"], c["kind"], -c["level"]))
    (RESULTS / "box_distance.json").write_text(json.dumps({"tol_mm": TOL_MM, "cells": out}, indent=1))
    for c in out:
        print(c)


if __name__ == "__main__":
    main()
