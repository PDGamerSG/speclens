"""Turn a defect mask into millimetres and check it against the clause's size limit.

Scale comes from the specification's part width and the part's width in pixels, which the model reports as a
box. It is an estimate: it assumes a top-down photo with the part's width across the frame.
"""
from __future__ import annotations

import cv2
import numpy as np


def measure(mask: np.ndarray | None, part_box_px: list[int] | None, part_width_mm: float | None,
            limit_mm: float | None) -> dict | None:
    if mask is None or not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    (_, _), (w, h), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    length_px, width_px = max(w, h) + 1, min(w, h) + 1
    area_px = int(mask.sum())
    result = {'length_px': round(float(length_px), 1), 'width_px': round(float(width_px), 1), 'area_px': area_px,
              'mm_per_px': None, 'length_mm': None, 'width_mm': None, 'area_mm2': None,
              'limit_mm': limit_mm, 'within_limit': None}
    part_px = (part_box_px[2] - part_box_px[0]) if part_box_px else 0
    if part_width_mm and part_px >= 8:
        scale = part_width_mm / part_px
        result.update(mm_per_px=round(scale, 5), length_mm=round(length_px * scale, 2),
                      width_mm=round(width_px * scale, 2), area_mm2=round(area_px * scale * scale, 2))
        if limit_mm is not None:
            result['within_limit'] = result['length_mm'] <= limit_mm
    return result
