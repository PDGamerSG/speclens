"""Deterministic forge helpers for the gate tests: crop, outline, align, colour-match, diff, composite."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw

DEFECTS = {
    "hole": "a small round drilled hole in the shell, about 4% of the nut's width, dark inside, with a slightly rough rim",
    "crack": "a thin jagged crack in the shell: a dark hairline split with slightly lifted, broken edges, about a quarter of the nut's width long",
    "print": "a small patch of white printed ink characters stamped onto the shell surface, slightly smudged",
}
# outline ellipse half-axes (px, in a 512 crop) per defect type
OUTLINE = {"hole": (26, 26), "crack": (80, 22), "print": (70, 40)}


def prompt_text(defect: str) -> str:
    return (f"Edit this close-up photo of a hazelnut. Add {DEFECTS[defect]} exactly at the center of the image. "
            "Keep the same lighting, focus, texture and camera angle. Do not change anything else in the photo.")


def prompt_outline(defect: str) -> str:
    return (f"Edit this close-up photo of a hazelnut. Inside the red outline, paint {DEFECTS[defect]}. "
            "Then remove the red outline completely so that no red remains anywhere. "
            "Keep everything outside the outline exactly the same.")


def crop_around(img: Image.Image, cx: int, cy: int, size: int = 512) -> tuple[Image.Image, tuple[int, int]]:
    W, H = img.size
    x0 = int(np.clip(cx - size // 2, 0, W - size))
    y0 = int(np.clip(cy - size // 2, 0, H - size))
    return img.crop((x0, y0, x0 + size, y0 + size)), (x0, y0)


def draw_outline(crop: Image.Image, defect: str) -> Image.Image:
    out = crop.copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    ax, ay = OUTLINE[defect]
    d.ellipse((w // 2 - ax, h // 2 - ay, w // 2 + ax, h // 2 + ay), outline=(255, 0, 0), width=4)
    return out


def _gray(a: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0


def composite(orig_rgb: np.ndarray, edited_rgb: np.ndarray) -> dict:
    """Resize -> ECC affine align -> colour-match on unchanged pixels -> LAB diff -> central component -> feathered paste.

    Returns composite, defect mask, and drift diagnostics. Pixels outside the feathered mask are byte-identical to orig.
    """
    H, W = orig_rgb.shape[:2]
    ed = cv2.resize(edited_rgb, (W, H), interpolation=cv2.INTER_AREA)
    warp = np.eye(2, 3, dtype=np.float32)
    ecc_ok = True
    try:
        _, warp = cv2.findTransformECC(_gray(orig_rgb), _gray(ed), warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        ecc_ok = False
    shift_px = float(np.hypot(warp[0, 2], warp[1, 2]))
    al = cv2.warpAffine(ed, warp, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)

    lab_o = cv2.cvtColor(orig_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_a = cv2.cvtColor(al, cv2.COLOR_RGB2LAB).astype(np.float32)
    d0 = np.abs(lab_o - lab_a).max(axis=2)
    drift_before = float(np.abs(orig_rgb.astype(np.float32) - al.astype(np.float32)).mean())
    # colour-match: per-channel offset estimated on the least-changed half of pixels
    calm = d0 < np.percentile(d0, 50)
    offset = (lab_a[calm] - lab_o[calm]).mean(axis=0)
    lab_a2 = np.clip(lab_a - offset, 0, 255)
    al2 = cv2.cvtColor(lab_a2.astype(np.uint8), cv2.COLOR_LAB2RGB)

    diff = cv2.GaussianBlur(np.abs(lab_o - lab_a2).max(axis=2), (0, 0), 2)
    diff8 = np.clip(diff * 4, 0, 255).astype(np.uint8)
    _, m = cv2.threshold(diff8, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m)
    mask = np.zeros((H, W), np.uint8)
    comp_area = 0
    if n > 1:
        c = np.array([W / 2, H / 2])
        best, best_score = None, -1e9
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            dist = np.linalg.norm(cents[i] - c)
            if dist > 0.3 * W or area < 30:
                continue
            score = area - 4 * dist
            if score > best_score:
                best, best_score = i, score
        if best is not None:
            mask = (lab == best).astype(np.uint8) * 255
            comp_area = int(stats[best, cv2.CC_STAT_AREA])
    total_changed = float((m > 0).mean())
    alpha = cv2.GaussianBlur(cv2.dilate(mask, k, iterations=2).astype(np.float32) / 255.0, (0, 0), 2)[..., None]
    out = (alpha * al2 + (1 - alpha) * orig_rgb).round().astype(np.uint8)
    outside = alpha[..., 0] == 0
    identical_outside = bool((out[outside] == orig_rgb[outside]).all())
    red = (out[..., 0] > 180) & (out[..., 1] < 80) & (out[..., 2] < 80) & (alpha[..., 0] > 0.5)
    return {"composite": out, "aligned": al2, "mask": mask > 0, "shift_px": round(shift_px, 1), "ecc_ok": ecc_ok,
            "drift_mae_before": round(drift_before, 2), "changed_frac": round(total_changed, 4),
            "defect_area_frac": round(comp_area / (H * W), 4), "identical_outside": identical_outside,
            "red_residue_px": int(red.sum())}
