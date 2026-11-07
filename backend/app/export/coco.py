"""Export accepted samples as a COCO-format zip: images, masks, annotations (uncompressed RLE) and provenance."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


def rle(mask: np.ndarray) -> dict:
    """COCO uncompressed RLE (column-major counts, starting with zeros)."""
    flat = mask.astype(np.uint8).flatten(order="F")
    counts, prev, run = [], 0, 0
    for v in flat:
        if v != prev:
            counts.append(run)
            run, prev = 0, v
        run += 1
    counts.append(run)
    return {"size": [int(mask.shape[0]), int(mask.shape[1])], "counts": counts}


def _find(dirs: list[Path], sid: str, suffixes: tuple[str, ...]) -> Path | None:
    for d in dirs:
        for suf in suffixes:
            p = d / f"{sid}{suf}"
            if p.exists():
                return p
    return None


def export_run(run_dir: Path, run: dict, extra_dirs: list[Path] | None = None) -> bytes:
    """extra_dirs: where else to look for sample files (a demo replay's artifacts live in fixtures/demo_run/samples)."""
    dirs = [run_dir / "samples", *(extra_dirs or [])]
    cats = [{"id": i + 1, "name": d["defect_type"], "supercategory": "defect", "spec_clause": d["clause"]}
            for i, d in enumerate(run["taxonomy"]["defects"])]
    cat_id = {c["name"]: c["id"] for c in cats}
    images, anns = [], []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, s in enumerate(x for x in run["samples"] if x["status"] == "accepted"):
            img_p = _find(dirs, s["id"], ("_composite.png", "_composite.jpg"))
            mask_p = _find(dirs, s["id"], ("_mask.png",))
            prov_p = _find(dirs, s["id"], ("_provenance.json",))
            if img_p is None or mask_p is None:
                continue
            m = np.array(Image.open(mask_p)) > 0
            h, w = m.shape
            ext = img_p.suffix
            images.append({"id": n + 1, "file_name": f"images/{s['id']}{ext}", "width": w, "height": h})
            x0, y0, x1, y1 = s["bbox"]
            anns.append({"id": n + 1, "image_id": n + 1, "category_id": cat_id.get(s["defect_type"], 0),
                         "bbox": [x0, y0, x1 - x0, y1 - y0], "area": int(m.sum()), "iscrowd": 1, "segmentation": rle(m),
                         "attributes": {"size_mm": s["size_mm"], "sam_iou": s["sam_iou"], "critic_realism": (s["critic"] or {}).get("realism"),
                                        "synthetic": True, "generator": "muse-image-1.0"}})
            z.write(img_p, f"images/{s['id']}{ext}")
            z.write(mask_p, f"masks/{s['id']}.png")
            if prov_p is not None:
                z.write(prov_p, f"provenance/{s['id']}.json")
        coco = {"info": {"description": "Chief Skill synthetic defect test suite", "run_id": run["id"],
                         "intended_use": "evaluation, benchmarking and quality assessment of inspection systems; not for training models that compete with Meta's"},
                "images": images, "annotations": anns, "categories": cats}
        z.writestr("annotations.json", json.dumps(coco))
        z.writestr("taxonomy.json", json.dumps(run["taxonomy"], indent=1))
        z.writestr("spec.txt", run["spec_text"])
        if run.get("curves"):
            z.writestr("stress_curves.json", json.dumps(run["curves"], indent=1))
    return buf.getvalue()
