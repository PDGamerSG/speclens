"""Revalidation runs from the EVAL.md addendum: located detection over 3 passes, unedited controls, white-print
attribution, real-benchmark stability, and a size-matched real-vs-forged comparison.

usage: python eval/revalidate.py [--stage all|stress|white|c0|report]
Resumable: each pass is cached in docs/results/raw/. Writes docs/results/revalidation.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

import run_eval as E  # noqa: E402  (also puts backend/ on sys.path)

from app.config import RESULTS  # noqa: E402
from app.forge import severity as sev  # noqa: E402
from app.forge.locate import load_image, otsu_mask, part_width  # noqa: E402
from app.forge.spec import DEFAULT_SPEC  # noqa: E402
from app.inspect.inspector import inspect  # noqa: E402
from app.meta import ledger  # noqa: E402
from app.runs import RUNS, manager  # noqa: E402

D, RAW, TYPES = E.D, E.RAW, E.TYPES
PASSES = 3
WORKERS = 12


def soft(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ledger.BudgetExceeded:
        raise
    except Exception:
        traceback.print_exc()
        return None


def forge_run():
    rid = json.loads((RAW / "forge_run.json").read_text())["run_id"]
    return manager.get(rid)


# ---------------------------------------------------------------- R1

def stress_pass(n: int) -> dict:
    run = forge_run()
    acc = [s for s in run.data["samples"] if s["status"] == "accepted"]
    jobs = [(s, k, lv) for s in acc for k, lv in sev.LEVELS]
    parts = sorted({s["part_id"] for s in acc})
    with ThreadPoolExecutor(WORKERS) as ex:
        pts = list(ex.map(lambda j: soft(manager.stress_point, run, *j, save=False, cache_key="reval-stress"), jobs))
        ctrl = list(ex.map(lambda p: soft(manager.control_point, run, p, cache_key="reval-stress"), parts))
    print(f"stress pass {n}: {sum(p is not None for p in pts)}/{len(jobs)} points, spent ${ledger.spent():.2f}", flush=True)
    return {"points": [p for p in pts if p], "controls": [c for c in ctrl if c]}


def summarize_stress(passes: list[dict]) -> dict:
    keyed: dict[tuple, list[dict]] = {}
    for p in passes:
        for pt in p["points"]:
            keyed.setdefault((pt["sample_id"], pt["kind"], pt["level"]), []).append(pt)
    majority = []
    unanimous = 0
    for pts in keyed.values():
        det = sum(p["detected"] for p in pts)
        unanimous += det in (0, len(pts))
        majority.append({**pts[0], "detected": det * 2 > len(pts), "flagged": sum(p["flagged"] for p in pts) * 2 > len(pts)})
    curves = sev.curves(majority)
    for c in curves:
        for cell in c["cells"]:
            cell["per_pass"] = [sum(pt["detected"] for pt in p["points"] if pt["defect_type"] == c["defect_type"]
                                    and pt["kind"] == cell["kind"] and pt["level"] == cell["level"]) for p in passes]
    ctrl = [c for p in passes for c in p["controls"]]
    return {"curves": curves, "variants": len(keyed), "unanimous": unanimous, "unanimous_rate": round(unanimous / max(1, len(keyed)), 3),
            "controls": {"n": len(ctrl), "flagged": sum(c["flagged"] for c in ctrl),
                         "parts": len({c["part_id"] for c in ctrl}), "ci": sev.wilson(sum(c["flagged"] for c in ctrl), len(ctrl))},
            "flagged_elsewhere": sum(1 for m in majority if m["flagged"] and not m["detected"])}


# ---------------------------------------------------------------- R2

def white_sets() -> dict:
    rid = json.loads((RAW / "blind_spot_run.json").read_text())["run_id"]
    run = manager.get(rid)
    sd = RUNS / rid / "samples"
    white = [("DEFECT, type print", load_image(sd / f"{s['id']}_composite.jpg"))
             for s in run.data["samples"] if s["status"] == "accepted"][:2]
    good = [("GOOD part", load_image(D / "train" / "good" / f"{i:03d}.png")) for i in (0, 1)]
    return {"W0": [], "W1": good, "W2": white, "W3": good + white}


def white_pass(cond: str, ex: list, n: int) -> list[dict]:
    items = [("print", p) for p in sorted((D / "test" / "print").glob("*.png"))]
    items += [("good", p) for p in sorted((D / "test" / "good").glob("*.png"))]

    def one(it):
        t, p = it
        r = inspect(load_image(p), DEFAULT_SPEC, TYPES, exemplars=ex or None, with_mask=False, cache_key=f"white-{cond}")
        return {"truth": t, "file": p.name, "defect": r["defect"], "type": r["type"]}

    with ThreadPoolExecutor(WORKERS) as pool:
        rows = [r for r in pool.map(lambda it: soft(one, it), items) if r]
    print(f"{cond} pass {n}: print {sum(r['defect'] for r in rows if r['truth'] == 'print')}/17, "
          f"false alarms {sum(r['defect'] for r in rows if r['truth'] == 'good')}/40, spent ${ledger.spent():.2f}", flush=True)
    return rows


def summarize_white(passes: dict) -> dict:
    conds = {}
    majority = {}
    for c, reps in passes.items():
        by: dict[tuple, list[bool]] = {}
        for rows in reps:
            for r in rows:
                by.setdefault((r["truth"], r["file"]), []).append(r["defect"])
        maj = {k: sum(v) * 2 > len(v) for k, v in by.items()}
        majority[c] = maj
        prints = [k for k in maj if k[0] == "print"]
        goods = [k for k in maj if k[0] == "good"]
        conds[c] = {"print_per_pass": [sum(r["defect"] for r in rows if r["truth"] == "print") for rows in reps],
                    "good_flagged_per_pass": [sum(r["defect"] for r in rows if r["truth"] == "good") for rows in reps],
                    "print_majority": sum(maj[k] for k in prints), "n_print": len(prints),
                    "false_alarms_majority": sum(maj[k] for k in goods), "n_good": len(goods),
                    "missed_majority": sorted(k[1] for k in prints if not maj[k])}
    keys = sorted(k for k in majority["W0"] if k[0] == "print")
    p_w2_w0 = E.mcnemar_exact([majority["W0"][k] for k in keys], [majority["W2"][k] for k in keys])
    w2_beats = conds["W2"]["print_majority"] > conds["W0"]["print_majority"] and p_w2_w0 < 0.05
    w3_ok = (conds["W3"]["print_majority"] >= conds["W1"]["print_majority"]
             and conds["W3"]["false_alarms_majority"] <= conds["W1"]["false_alarms_majority"])
    return {"conditions": conds, "p_w2_vs_w0": p_w2_w0, "w2_beats_w0": bool(w2_beats), "w3_at_least_w1": bool(w3_ok),
            "forged_examples_get_credit": bool(w2_beats and w3_ok)}


# ---------------------------------------------------------------- R3 + R4

def c0_passes() -> list[list[dict]]:
    return [E.cached("cond_C0", lambda: None)] + [E.cached(f"cond_C0_rep{n}", lambda: E.run_condition("C0", [])) for n in (2, 3)]


def summarize_c0(reps: list[list[dict]]) -> dict:
    sc = [E.score(r) for r in reps]
    return {"recall_per_pass": [s["recall"] for s in sc], "specificity_per_pass": [s["specificity"] for s in sc],
            "print_per_pass": [s["by_type"]["print"]["detected"] for s in sc], "n_print": sc[0]["by_type"]["print"]["n"]}


def real_sizes(reps: list[list[dict]]) -> list[dict]:
    outcome: dict[tuple, list[bool]] = {}
    for rows in reps:
        for r in rows:
            if r["truth"] != "good":
                outcome.setdefault((r["truth"], r["id"]), []).append(bool(r["defect"] and r.get("box_hit")))
    out = []
    for (t, i), v in outcome.items():
        img = load_image(D / "test" / t / f"{i:03d}.png")
        m = np.array(Image.open(D / "ground_truth" / t / f"{i:03d}_mask.png")) > 0
        out.append({"type": t, "id": i, "size_mm": round(2 * math.sqrt(m.sum() / math.pi) * 20 / part_width(otsu_mask(img)), 2),
                    "caught": sum(v) * 2 > len(v)})
    return out


def size_match(real: list[dict], stress: list[dict]) -> list[dict]:
    keyed: dict[tuple, list[dict]] = {}
    for p in stress:
        for pt in p["points"]:
            if pt["kind"] == "size" or pt["level"] == 1.0:
                keyed.setdefault((pt["sample_id"], pt["kind"], pt["level"]), []).append(pt)
    forged = [{"type": v[0]["defect_type"], "size_mm": v[0]["size_mm"], "caught": sum(x["detected"] for x in v) * 2 > len(v)}
              for v in keyed.values() if v[0]["size_mm"]]
    rows = []
    for t in TYPES:
        r = [x for x in real if x["type"] == t]
        f = [x for x in forged if x["type"] == t]
        lo, hi = max(min(x["size_mm"] for x in r), min(x["size_mm"] for x in f)), min(max(x["size_mm"] for x in r), max(x["size_mm"] for x in f))
        rb = [x for x in r if lo <= x["size_mm"] <= hi]
        fb = [x for x in f if lo <= x["size_mm"] <= hi]
        rows.append({"type": t, "real_median_mm": round(float(np.median([x["size_mm"] for x in r])), 1),
                     "real_min_mm": min(x["size_mm"] for x in r), "forged_max_mm": max(x["size_mm"] for x in f),
                     "band_mm": [lo, hi] if lo <= hi else None, "real_in_band": f"{sum(x['caught'] for x in rb)}/{len(rb)}",
                     "forged_in_band": f"{sum(x['caught'] for x in fb)}/{len(fb)}",
                     "real_all": f"{sum(x['caught'] for x in r)}/{len(r)}"})
    return rows


def faint_check(stress: list[dict]) -> dict:
    """The first faint-defect drop compared one spec-only pass with one forged-examples pass. Re-score it against each new
    spec-only pass, on the same images. 'flagged' matches how the original comparison counted."""
    faint = json.loads((RAW / "faint_lift.json").read_text())
    keys = [(r["sample_id"], r["kind"], r["level"]) for r in faint]
    rows = []
    for p in stress:
        by = {(x["sample_id"], x["kind"], x["level"]): x["flagged"] for x in p["points"]}
        z = [by[k] for k in keys if k in by]
        w = [r["with_forged"] for r, k in zip(faint, keys) if k in by]
        rows.append({"spec_only": sum(z), "with_forged": sum(w), "n": len(z), "p": E.mcnemar_exact(z, w)})
    return {"passes": rows, "original_spec_only": sum(r["zero_shot"] for r in faint), "with_forged": sum(r["with_forged"] for r in faint)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "stress", "white", "c0", "report"])
    a = ap.parse_args()
    s0 = ledger.spent()
    run_all = a.stage == "all"
    if run_all or a.stage == "stress":
        for n in range(1, PASSES + 1):
            E.cached(f"stress_v2_pass{n}", lambda n=n: stress_pass(n))
    if run_all or a.stage == "white":
        sets = white_sets()
        for c, ex in sets.items():
            for n in range(1, PASSES + 1):
                E.cached(f"white_{c}_pass{n}", lambda c=c, ex=ex, n=n: white_pass(c, ex, n))
    if run_all or a.stage == "c0":
        c0_passes()
    print(f"this stage spent ${ledger.spent() - s0:.2f}", flush=True)
    needed = [RAW / f"stress_v2_pass{n}.json" for n in range(1, PASSES + 1)] + [RAW / "cond_C0_rep3.json"]
    needed += [RAW / f"white_{c}_pass{n}.json" for c in ("W0", "W1", "W2", "W3") for n in range(1, PASSES + 1)]
    if not all(p.exists() for p in needed):
        print("not all passes done yet; skipping the report")
        return
    stress = [json.loads((RAW / f"stress_v2_pass{n}.json").read_text()) for n in range(1, PASSES + 1)]
    white = {c: [json.loads((RAW / f"white_{c}_pass{n}.json").read_text()) for n in range(1, PASSES + 1)] for c in ("W0", "W1", "W2", "W3")}
    c0 = c0_passes()
    out = {"stress": summarize_stress(stress), "white": summarize_white(white), "c0": summarize_c0(c0),
           "size_match": size_match(real_sizes(c0), stress), "faint": faint_check(stress)}
    (RESULTS / "revalidation.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out["stress"].items() if k != "curves"}, indent=1))
    for c in out["stress"]["curves"]:
        print(c["threshold_note"], [(x["kind"][:3], x["level"], x["detected"], x["n"], x["per_pass"]) for x in c["cells"]])
    print(json.dumps(out["white"], indent=1))
    print(json.dumps(out["c0"]))
    print(json.dumps(out["faint"]))
    for r in out["size_match"]:
        print(r)


if __name__ == "__main__":
    main()
