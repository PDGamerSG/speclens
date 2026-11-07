"""Find the part (Muse Spark box -> SAM 3.1 mask, with point-prompt and Otsu fallbacks) and sample defect locations on it."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..config import CROP, MAX_SIDE
from ..meta.client import data_url, sam_segment, spark_json, to_jpeg

LOCATE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["has_box", "x0", "y0", "x1", "y1"],
                 "properties": {"has_box": {"type": "boolean"}, "x0": {"type": "integer"}, "y0": {"type": "integer"},
                                "x1": {"type": "integer"}, "y1": {"type": "integer"}}}


def load_image(path) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return img


def border_frac(mask: np.ndarray) -> float:
    return float(np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]]).mean())


def otsu_mask(img: Image.Image) -> np.ndarray:
    g = cv2.GaussianBlur(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY), (5, 5), 0)
    _, o = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    bright = o > 0
    # the background owns the frame border, so the part is whichever class touches it least:
    # this handles a bright part on black paper and a dark part on a light desk
    fg = bright if border_frac(bright) <= border_frac(~bright) else ~bright
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8))
    if n <= 1:
        return np.ones(o.shape, bool)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    filled = np.zeros(o.shape, np.uint8)   # fill highlights inside the part
    contours, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled > 0


def _usable(m: np.ndarray | None) -> bool:
    """A mask that owns the frame border, or is nearly empty, is not the part."""
    return m is not None and m.mean() > 0.005 and border_frac(m) < 0.5


def spark_box(img: Image.Image, run_id: str | None = None) -> tuple[int, int, int, int] | None:
    """Muse Spark finds the object under inspection, ignoring the paper, desk or mat it rests on."""
    msgs = [{"role": "system", "content": (
                "You locate the single main object being inspected in a photo. Ignore the surface it rests on (paper, desk, "
                "mat, conveyor), shadows and everything else. Return a tight bounding box on a 0-1000 grid (x0,y0 top-left; "
                "x1,y1 bottom-right). If no distinct object is visible, set has_box false and all coordinates 0.")},
            {"role": "user", "content": [{"type": "text", "text": "Locate the object."},
                                         {"type": "image_url", "image_url": {"url": data_url(to_jpeg(img, 90, 768))}}]}]
    d = spark_json(msgs, LOCATE_SCHEMA, "locate", effort="low", run_id=run_id)["data"]
    if not d["has_box"]:
        return None
    W, H = img.size
    x0, y0, x1, y1 = [int(np.clip(v, 0, 1000) / 1000 * s) for v, s in zip((d["x0"], d["y0"], d["x1"], d["y1"]), (W, H, W, H))]
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return (x0, y0, x1, y1) if x1 - x0 >= 8 and y1 - y0 >= 8 else None


def part_mask(img: Image.Image, run_id: str | None = None) -> tuple[np.ndarray, str]:
    """Muse Spark box -> SAM 3.1 mask. Thresholding alone can't separate a nut from a sheet of paper or a grid mat, and
    SAM concept prompts return empty on studio scans (gate T3). Falls back to a point prompt, then to Otsu."""
    try:
        box = spark_box(img, run_id)
        if box:
            r = sam_segment(img, boxes=[box], run_id=run_id, op="part_mask")
            m = next((ob["mask"] for ob in r["objects"] if ob["mask"] is not None), None)
            if _usable(m):
                return m, "muse-spark-1.3 box + sam-3.1"
    except Exception:
        pass
    o = otsu_mask(img)
    ys, xs = np.nonzero(o)
    cx, cy = (int(xs.mean()), int(ys.mean())) if len(xs) else (img.size[0] // 2, img.size[1] // 2)
    try:
        r = sam_segment(img, points=[[(cx, cy)]], run_id=run_id, op="part_mask")
        m = next((ob["mask"] for ob in r["objects"] if ob["mask"] is not None), None)
        if _usable(m):
            return m, "sam-3.1 point prompt"
    except Exception:
        pass
    return o, "otsu fallback"


def crop_size(img: Image.Image, part_width_px: float | None = None) -> int:
    """512 px, or tighter when the part is small in the frame, so the crop stays a close-up of the part."""
    size = min(CROP, min(img.size))
    if part_width_px:
        size = min(size, max(192, part_width_px))
    return int(size)


def part_width(mask: np.ndarray) -> float:
    xs = np.nonzero(mask.any(axis=0))[0]
    return float(xs.max() - xs.min()) if len(xs) else 0.0


def sample_centres(mask: np.ndarray, n: int, crop: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    """Defect centres well inside the part, spread out, and far enough from the border for a full crop."""
    H, W = mask.shape
    # keep centres in the inner part of the object, away from tips and edges where edits turn into slices
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    er = dist >= 0.45 * dist.max()
    ys, xs = np.nonzero(er)
    if len(xs) == 0:
        ys, xs = np.nonzero(mask)
    pts: list[tuple[int, int]] = []
    for _ in range(n * 40):
        if len(pts) >= n:
            break
        i = rng.integers(len(xs))
        p = (int(xs[i]), int(ys[i]))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (0.12 * W) ** 2 for q in pts):
            pts.append(p)
    while len(pts) < n:
        i = rng.integers(len(xs))
        pts.append((int(xs[i]), int(ys[i])))
    return pts


def crop_box(img_size: tuple[int, int], cx: int, cy: int, crop: int) -> tuple[int, int, int, int]:
    W, H = img_size
    x0 = int(np.clip(cx - crop // 2, 0, W - crop))
    y0 = int(np.clip(cy - crop // 2, 0, H - crop))
    return x0, y0, x0 + crop, y0 + crop
