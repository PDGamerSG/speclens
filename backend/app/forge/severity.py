"""Severity ladder: deterministic fades and shrinks of a forged defect, and detection-threshold curves.

The defect "delta" (forged minus original, inside the mask) is scaled in opacity or in size with OpenCV and pasted
back. Ground truth is known by construction, so the inspector's detection rate per level is a non-circular measure.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

LEVELS = [("opacity", 1.0), ("opacity", 0.5), ("opacity", 0.25), ("opacity", 0.12),
          ("size", 0.6), ("size", 0.35), ("size", 0.2)]


def variant(orig_crop: np.ndarray, comp_crop: np.ndarray, mask: np.ndarray, kind: str, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Returns (variant crop RGB uint8, variant mask bool)."""
    o = orig_crop.astype(np.float32)
    c = comp_crop.astype(np.float32)
    m = mask.astype(np.float32)
    if kind == "opacity":
        out = o + (m[..., None] * level) * (c - o)
        return np.clip(out, 0, 255).astype(np.uint8), mask.copy()
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return orig_crop.copy(), mask.copy()
    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    delta = (c - o)[by0:by1, bx0:bx1] * m[by0:by1, bx0:bx1, None]
    mm = m[by0:by1, bx0:bx1]
    nw, nh = max(2, int((bx1 - bx0) * level)), max(2, int((by1 - by0) * level))
    d_s = cv2.resize(delta, (nw, nh), interpolation=cv2.INTER_AREA)
    m_s = cv2.resize(mm, (nw, nh), interpolation=cv2.INTER_AREA)
    cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
    px, py = cx - nw // 2, cy - nh // 2
    out = o.copy()
    out[py:py + nh, px:px + nw] += d_s * (m_s[..., None] > 0)
    vm = np.zeros_like(mask)
    vm[py:py + nh, px:px + nw] = m_s > 0.5
    return np.clip(out, 0, 255).astype(np.uint8), vm


def box_hits(box: list | None, mask: np.ndarray) -> bool:
    """True when the inspector's pixel box overlaps the defect mask."""
    if not box:
        return False
    x0, y0, x1, y1 = box
    return bool(mask[y0:y1, x0:x1].any())


def equiv_diameter_mm(area_px: float, part_width_px: float, part_width_mm: float) -> float | None:
    if not part_width_mm or not part_width_px or area_px <= 0:
        return None
    return round(2 * math.sqrt(area_px / math.pi) * part_width_mm / part_width_px, 2)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def curves(points: list[dict]) -> list[dict]:
    out = []
    for t in sorted({p["defect_type"] for p in points}):
        cells = []
        for kind, level in LEVELS:
            ps = [p for p in points if p["defect_type"] == t and p["kind"] == kind and p["level"] == level]
            if not ps:
                continue
            k = sum(p["detected"] for p in ps)
            lo, hi = wilson(k, len(ps))
            sizes = [p["size_mm"] for p in ps if p.get("size_mm")]
            cells.append({"kind": kind, "level": level, "n": len(ps), "detected": k,
                          "flagged": sum(p.get("flagged", p["detected"]) for p in ps), "rate": round(k / len(ps), 3),
                          "ci_low": lo, "ci_high": hi, "mean_size_mm": round(float(np.mean(sizes)), 2) if sizes else None})
        out.append({"defect_type": t, "cells": cells, "threshold_note": threshold_note(t, cells)})
    return out


def series(cells: list[dict], kind: str) -> list[dict]:
    """Full-strength cell first, then the given kind from strongest to faintest/smallest."""
    full = [c for c in cells if c["kind"] == "opacity" and c["level"] == 1.0]
    rest = sorted((c for c in cells if c["kind"] == kind and not (c["kind"] == "opacity" and c["level"] == 1.0)),
                  key=lambda c: -c["level"])
    return full + rest


def threshold_note(t: str, cells: list[dict]) -> str:
    notes = []
    for kind, label in (("size", "size"), ("opacity", "contrast")):
        cs = series(cells, kind)
        if len(cs) < 2:
            continue
        held = None
        for c in cs:
            if c["rate"] >= 0.8:
                held = c
            else:
                break
        miss = next((c for c in cs if c["rate"] < 0.5), None)

        def lvl(c):
            mm = f" (~{c['mean_size_mm']} mm)" if kind == "size" and c.get("mean_size_mm") else ""
            return f"{c['level']:g}x{mm}"

        if miss is None:
            notes.append(f"caught at every {label} tested (down to {lvl(cs[-1])})")
        else:
            lead = f"holds to {lvl(held)}, " if held and held is not miss else ""
            notes.append(f"{label}: {lead}missed at {lvl(miss)} ({miss['detected']}/{miss['n']})")
    return f"{t}: " + "; ".join(notes)
