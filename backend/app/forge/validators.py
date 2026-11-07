"""Eight deterministic validators for every forged sample. None of them calls a model."""
from __future__ import annotations

import numpy as np

from .composite import hamming


def run_validators(*, comp: dict, defect_mask_full: np.ndarray, part_mask: np.ndarray, crop_area: int,
                   sam_iou: float | None, defect_type: str, critic: dict | None, dhash_val: int,
                   accepted_hashes: list[int], provenance: dict) -> list[dict]:
    v = []

    def add(i, name, passed, detail, hard=True):
        v.append({"id": f"V{i}", "name": name, "passed": bool(passed), "detail": detail, "hard": hard})

    add(1, "Pixels outside the defect are byte-identical", comp["identical_outside"],
        "every pixel with alpha 0 equals the original" if comp["identical_outside"] else "pixels changed outside the mask")
    area = int(defect_mask_full.sum())
    inside = float((defect_mask_full & part_mask).sum() / area) if area else 0.0
    add(2, "Defect lies on the part", inside >= 0.9, f"{inside:.0%} of defect pixels inside the part mask")
    frac = area / max(1, crop_area)
    add(3, "Defect size is plausible", 0.0008 <= frac <= 0.12, f"{frac:.2%} of the crop")
    if sam_iou is None:
        add(4, "SAM 3.1 agrees with the diff mask", False, "no SAM mask", hard=False)
    else:
        thin = defect_type in ("crack", "scratch", "cut")
        ok = sam_iou >= (0.15 if thin else 0.3)
        add(4, "SAM 3.1 agrees with the diff mask", ok, f"IoU {sam_iou:.2f}" + (" (thin defect: lower bar)" if thin else ""), hard=False)
    add(5, "Edit stayed local", comp["components"] <= 6 and comp["changed_frac"] <= 0.15,
        f"{comp['components']} region(s); {comp['changed_frac']:.1%} of crop changed before masking")
    if critic is None:
        add(6, "Muse Spark critic accepts realism", False, "critic not run")
    else:
        add(6, "Muse Spark critic accepts realism", critic["verdict"] == "accept" and critic["realism"] >= 4 and critic["matches_type"],
            f"realism {critic['realism']}/5, type {'matches' if critic['matches_type'] else 'mismatch'}")
    dmin = min((hamming(dhash_val, h) for h in accepted_hashes), default=64)
    add(7, "Not a near-duplicate", dmin >= 4, f"min dHash distance {dmin}")
    need = ("prompt", "prompt_sha256", "models", "source_image", "crop_box")
    missing = [k for k in need if not provenance.get(k)]
    add(8, "Provenance complete", not missing, "all fields present" if not missing else f"missing {missing}")
    return v


def accepted(validators: list[dict]) -> bool:
    return all(x["passed"] for x in validators if x["hard"])
