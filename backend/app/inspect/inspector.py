"""Muse Spark visual inspector + SAM 3.1 mask behind every claimed defect (sanitizer: no mask -> 'uncertain')."""
from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image

from ..meta.client import data_url, sam_segment, spark_json, to_jpeg


def inspect_schema(types: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": ["defect", "type", "has_box", "x0", "y0", "x1", "y1", "confidence", "rationale"],
            "properties": {"defect": {"type": "boolean"},
                           "type": {"type": "string", "enum": ["good", *types]},
                           "has_box": {"type": "boolean"}, "x0": {"type": "integer"}, "y0": {"type": "integer"},
                           "x1": {"type": "integer"}, "y1": {"type": "integer"},
                           "confidence": {"type": "number"}, "rationale": {"type": "string"}}}


def system_prompt(spec_text: str) -> str:
    return ("You are the visual quality inspector described by this specification. Inspect the final image only. "
            "Report defect=true for any REJECT class in the spec, with its type and a bounding box around it on a 0-1000 grid "
            "(x0,y0 top-left; x1,y1 bottom-right). If the part is acceptable, set defect=false, type 'good', has_box=false "
            "and all coordinates 0. confidence is 0-1.\n\nSPECIFICATION:\n" + spec_text)


def _img_part(img: Image.Image, side: int = 768) -> dict:
    return {"type": "image_url", "image_url": {"url": data_url(to_jpeg(img, 90, side))}}


def inspect(img: Image.Image, spec_text: str, types: list[str], *, exemplars: list[tuple[str, Image.Image]] | None = None,
            run_id: str | None = None, cache_key: str | None = None, with_mask: bool = True) -> dict:
    content: list = []
    for label, ex in exemplars or []:
        content += [{"type": "text", "text": f"Reference example: {label}."}, _img_part(ex)]
    content += [{"type": "text", "text": "Inspect this part."}, _img_part(img)]
    msgs = [{"role": "system", "content": system_prompt(spec_text)}, {"role": "user", "content": content}]
    r = spark_json(msgs, inspect_schema(types), "inspect", effort="low", run_id=run_id,
                   cache_key=cache_key or f"inspect-{hashlib.sha256(spec_text.encode()).hexdigest()[:8]}-{len(exemplars or [])}")
    out = r["data"]
    W, H = img.size
    box = None
    if out["defect"] and out["has_box"]:
        x0, y0, x1, y1 = [int(np.clip(v, 0, 1000) / 1000 * s) for v, s in zip((out["x0"], out["y0"], out["x1"], out["y1"]), (W, H, W, H))]
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            box = (x0, y0, min(W, x1), min(H, y1))
    mask = None
    cost = r["cost_usd"]
    if with_mask and box is not None:
        s = sam_segment(img, boxes=[box], run_id=run_id, op="inspect_mask")
        cost += s["cost_usd"]
        mask = next((o["mask"] for o in s["objects"] if o["mask"] is not None and o["mask"].any()), None)
    if not out["defect"]:
        verdict = "good"
    elif with_mask and mask is None:
        verdict = "uncertain"
    else:
        verdict = "defect"
    return {"verdict": verdict, "defect": out["defect"], "type": out["type"], "confidence": out["confidence"],
            "rationale": out["rationale"], "box_px": list(box) if box else None, "mask": mask,
            "ms": round(r["ms"]), "cost_usd": cost}
