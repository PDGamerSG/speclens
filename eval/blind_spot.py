"""Targeted blind-spot experiment (run after eval/run_eval.py).

On the real MVTec benchmark the spec-only inspector's only misses were WHITE print, read as "specular gloss".
1. Forge white print with SpecLens (spec-driven, zero real defects) and measure detection -> does forging
   reproduce the blind spot that real data revealed?
2. Amend the spec with one clarifying clause and re-measure on the forged set AND on all real print defects
   -> does the fix found with forged data transfer to real parts?
Outputs docs/results/blind_spot.json.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from app import parts as parts_mod  # noqa: E402
from app.config import RESULTS  # noqa: E402
from app.forge.locate import load_image  # noqa: E402
from app.forge.severity import wilson  # noqa: E402
from app.forge.spec import DEFAULT_SPEC  # noqa: E402
from app.inspect.inspector import inspect  # noqa: E402
from app.meta import ledger  # noqa: E402
from app.runs import RUNS, manager  # noqa: E402

D = ROOT / "data" / "mvtec" / "hazelnut"
TYPES = ["hole", "crack", "cut", "print"]
RAW = RESULTS / "raw"
WHITE = {"part_name": "whole in-shell hazelnut", "part_width_mm": 20, "defects": [{
    "defect_type": "print", "clause": "4.4",
    "description": "a patch of bright white printed ink characters stamped onto the brown shell, slightly smudged and uneven, "
                   "about a quarter of the part width across",
    "severity_note": "any ink, stamp, printed characters or marking on the shell, any size or colour"}]}
AMEND = ("\n4.5 Clarification: bright white or light-coloured characters, letters, digits or ink smudges on the shell are "
         "PRINT (4.4) and must be rejected. Do not dismiss them as gloss or specular highlights: natural gloss is a smooth "
         "soft highlight that follows the shell curvature and never forms characters or sharp-edged marks.")


def detect(paths, spec):
    def one(p):
        r = inspect(load_image(p), spec, TYPES, with_mask=False, cache_key=f"blind-{hash(spec) & 0xffff:x}")
        return {"file": str(p.name), "defect": r["defect"], "type": r["type"], "rationale": r["rationale"][:140]}
    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(one, paths))


def rate(rows):
    k = sum(r["defect"] for r in rows)
    return {"detected": k, "n": len(rows), "rate": round(k / max(1, len(rows)), 3), "ci": wilson(k, len(rows))}


def exemplar_condition(rid: str) -> dict:
    """Step 3: show the ORIGINAL-spec inspector 2 good parts + 2 forged WHITE prints, then score all real test images."""
    sd = RUNS / rid / "samples"
    run = manager.get(rid)
    wp = [s for s in run.data["samples"] if s["status"] == "accepted"][:2]
    ex = [("GOOD part", load_image(D / "train" / "good" / f"{i:03d}.png")) for i in (0, 1)]
    ex += [("DEFECT, type print", load_image(sd / f"{s['id']}_composite.jpg")) for s in wp]
    items = [("good", p) for p in sorted((D / "test" / "good").glob("*.png"))]
    items += [(t, p) for t in TYPES for p in sorted((D / "test" / t).glob("*.png"))]

    def one(it):
        t, p = it
        r = inspect(load_image(p), DEFAULT_SPEC, TYPES, exemplars=ex, with_mask=False, cache_key="blind-whiteex-v1")
        return {"truth": t, "file": p.name, "defect": r["defect"], "type": r["type"]}

    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(one, items))
    pos = [r for r in rows if r["truth"] != "good"]
    neg = [r for r in rows if r["truth"] == "good"]
    prints = [r for r in pos if r["truth"] == "print"]
    return {"exemplars": "2 good + 2 forged white print", "recall_all": rate([{"defect": r["defect"]} for r in pos]),
            "real_print": rate([{"defect": r["defect"]} for r in prints]),
            "false_alarms_good": rate([{"defect": r["defect"]} for r in neg]),
            "errors": [(r["truth"], r["file"]) for r in rows if (r["truth"] != "good") != r["defect"]]}


def main():
    if "--exemplars" in sys.argv:
        out = json.loads((RESULTS / "blind_spot.json").read_text())
        s0 = ledger.spent()
        out["forged_white_exemplars"] = exemplar_condition(out["forge"]["run_id"])
        out["cost_usd"] = round(out["cost_usd"] + ledger.spent() - s0, 3)
        (RESULTS / "blind_spot.json").write_text(json.dumps(out, indent=1))
        print(json.dumps(out["forged_white_exemplars"], indent=1))
        return
    t0, s0 = time.time(), ledger.spent()
    p = RAW / "blind_spot_run.json"
    rid = json.loads(p.read_text())["run_id"] if p.exists() else None
    run = manager.get(rid) if rid else None
    if run is None or run.data["status"] != "completed":
        pids = [pid for pid in parts_mod.all_parts() if pid.startswith("mvtec-hazelnut-")][:12]
        rid = manager.create(DEFAULT_SPEC, WHITE, pids, per_type=12, stress=False)
        p.write_text(json.dumps({"run_id": rid}))
        run = manager.get(rid)
        while run.data["status"] == "running":
            time.sleep(3)
    sd = RUNS / rid / "samples"
    forged = [sd / f"{s['id']}_composite.jpg" for s in run.data["samples"] if s["status"] == "accepted"]
    real_print = sorted((D / "test" / "print").glob("*.png"))
    real_good = sorted((D / "test" / "good").glob("*.png"))
    out = {"forge": {"accepted": len(forged), "attempted": len(run.data["samples"]), "run_id": rid}}
    for name, spec in (("original_spec", DEFAULT_SPEC), ("amended_spec", DEFAULT_SPEC + AMEND)):
        fr, rp, rg = detect(forged, spec), detect(real_print, spec), detect(real_good, spec)
        out[name] = {"forged_white_print": rate(fr), "real_print": rate(rp),
                     "real_good_false_alarms": rate(rg), "misses_real": [r for r in rp if not r["defect"]]}
        print(name, "forged white print", out[name]["forged_white_print"], "| real print", out[name]["real_print"],
              "| false alarms on good", out[name]["real_good_false_alarms"])
    out["amendment"] = AMEND.strip()
    out["cost_usd"] = round(ledger.spent() - s0, 3)
    out["seconds"] = round(time.time() - t0)
    (RESULTS / "blind_spot.json").write_text(json.dumps(out, indent=1))
    print("cost", out["cost_usd"])


if __name__ == "__main__":
    main()
