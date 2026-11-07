"""Deterministic compositing: no model is called here.

Muse Image edits come back at a different size, slightly shifted, with small global colour drift. We resize,
ECC-align, colour-match on unchanged pixels, diff in LAB, keep the changed region(s) near the crop centre, and
paste only those pixels back with a feathered alpha. Pixels with alpha 0 are byte-identical to the original.
"""
from __future__ import annotations

import cv2
import numpy as np


def _gray(a: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0


def align(orig: np.ndarray, edited: np.ndarray) -> tuple[np.ndarray, float, bool]:
    H, W = orig.shape[:2]
    ed = cv2.resize(edited, (W, H), interpolation=cv2.INTER_AREA)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)

    def plausible(w: np.ndarray) -> bool:
        # edits only shift a few px; a big scale change or shift means ECC locked onto the edit itself
        return abs(np.linalg.det(w[:, :2]) - 1) < 0.04 and np.hypot(w[0, 2], w[1, 2]) < 40

    warp = np.eye(2, 3, dtype=np.float32)
    ok = True
    try:
        _, warp = cv2.findTransformECC(_gray(orig), _gray(ed), warp, cv2.MOTION_AFFINE, crit, None, 5)
    except cv2.error:
        ok = False
    if not ok or not plausible(warp):
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(_gray(orig), _gray(ed), warp, cv2.MOTION_TRANSLATION, crit, None, 5)
            ok = plausible(warp)
        except cv2.error:
            ok = False
        if not ok:
            warp = np.eye(2, 3, dtype=np.float32)
    al = cv2.warpAffine(ed, warp, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
    return al, float(np.hypot(warp[0, 2], warp[1, 2])), ok


def composite(orig: np.ndarray, edited: np.ndarray, *, central_frac: float = 0.3) -> dict:
    """orig, edited: RGB uint8. Returns composite, defect mask (bool), alpha, and diagnostics."""
    H, W = orig.shape[:2]
    al, shift_px, ecc_ok = align(orig, edited)
    lab_o = cv2.cvtColor(orig, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_a = cv2.cvtColor(al, cv2.COLOR_RGB2LAB).astype(np.float32)
    d0 = np.abs(lab_o - lab_a).max(axis=2)
    drift = float(np.abs(orig.astype(np.float32) - al.astype(np.float32)).mean())
    calm = d0 <= np.percentile(d0, 50)          # <= so an unchanged edit still has calm pixels
    lab_a = np.clip(lab_a - (lab_a[calm] - lab_o[calm]).mean(axis=0), 0, 255)
    al2 = cv2.cvtColor(lab_a.astype(np.uint8), cv2.COLOR_LAB2RGB)

    diff = cv2.GaussianBlur(np.abs(lab_o - lab_a).max(axis=2), (0, 0), 2)
    diff8 = np.clip(diff * 4, 0, 255).astype(np.uint8)
    _, m = cv2.threshold(diff8, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m)
    centre = np.array([W / 2, H / 2])
    keep = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 30:
            continue
        if np.linalg.norm(cents[i] - centre) <= central_frac * W:
            keep.append(i)
    mask = np.isin(lab, keep) if keep else np.zeros((H, W), bool)
    alpha = cv2.GaussianBlur(cv2.dilate(mask.astype(np.uint8) * 255, k, iterations=2).astype(np.float32) / 255.0, (0, 0), 2)
    alpha = alpha[..., None]
    out = (alpha * al2 + (1 - alpha) * orig).round().astype(np.uint8)
    outside = alpha[..., 0] == 0
    return {
        "composite": out, "mask": mask, "alpha": alpha[..., 0], "aligned": al2,
        "shift_px": round(shift_px, 2), "ecc_ok": ecc_ok, "drift_mae": round(drift, 2),
        "changed_frac": round(float((m > 0).mean()), 5), "components": len(keep),
        "identical_outside": bool((out[outside] == orig[outside]).all()),
    }


def overlay(img: np.ndarray, mask: np.ndarray, color=(255, 140, 0)) -> np.ndarray:
    """Draw the mask outline (and a faint fill) on an RGB image."""
    out = img.copy()
    m8 = mask.astype(np.uint8) * 255
    fill = out.astype(np.float32)
    fill[mask] = 0.75 * fill[mask] + 0.25 * np.array(color, np.float32)
    out = fill.astype(np.uint8)
    contours, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(out, contours, -1, color, thickness=max(2, img.shape[1] // 400), lineType=cv2.LINE_AA)
    return out


def dhash(img: np.ndarray, size: int = 8) -> int:
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0
