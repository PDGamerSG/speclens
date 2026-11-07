"""Run the pre-registered evaluation in EVAL.md. Resumable: every stage caches raw results in docs/results/raw/.

usage: python eval/run_eval.py [--per-type 15] [--parts 16]
Requires MODEL_API_KEY in .env and the hazelnut data (python eval/download_mvtec.py).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import parts as parts_mod  # noqa: E402
from app.config import RESULTS  # noqa: E402
from app.forge import severity as sev  # noqa: E402
from app.forge.composite import iou  # noqa: E402
from app.forge.locate import load_image  # noqa: E402
from app.forge.spec import DEFAULT_SPEC, taxonomy  # noqa: E402
from app.inspect.inspector import inspect  # noqa: E402
from app.meta import ledger  # noqa: E402
from app.meta.client import sam_segment  # noqa: E402
from app.runs import RUNS, manager  # noqa: E402

D = ROOT / "data" / "mvtec" / "hazelnut"
RAW = RESULTS / "raw"
RAW.mkdir(parents=True, exist_ok=True)
TYPES = ["crack", "cut", "hole", "print"]
ORACLE = {"crack": 17, "cut": 16, "hole": 17, "print": 16}
HARD = [("opacity", 0.25), ("opacity", 0.12), ("size", 0.2)]


def cached(name: str, fn):
    p = RAW / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    out = fn()
    p.write_text(json.dumps(out, indent=1))
    return out


def pmap(fn, items, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))


# ---------------------------------------------------------------- 1. forge batch (+ stress) on train/good

def forge_batch(per_type: int, n_parts: int) -> dict:
    p = RAW / "forge_run.json"
    if p.exists():
        rid = json.loads(p.read_text())["run_id"]
        r = manager.get(rid)
        if r and r.data["status"] == "completed":
            return r.data
    tax = cached("taxonomy", lambda: taxonomy(DEFAULT_SPEC))
    pids = [pid for pid in parts_mod.all_parts() if pid.startswith("mvtec-hazelnut-")][:n_parts]
    rid = manager.create(DEFAULT_SPEC, tax, pids, per_type, stress=True)
    p.write_text(json.dumps({"run_id": rid}))
    print("forge run", rid, "parts", len(pids))
    run = manager.get(rid)
    last = 0
    while run.data["status"] == "running":
        time.sleep(5)
        n = len(run.data["samples"])
        done = sum(s["status"] in ("accepted", "rejected", "failed") for s in run.data["samples"])
        if done != last:
            print(f"  samples done {done}/{n}  severity {len(run.data['severity'])}  spent ${ledger.spent():.2f}", flush=True)
            last = done
    return run.data


# ---------------------------------------------------------------- 2. real benchmark + in-context conditions

def test_items():
    items = [("good", i) for i in range(40)]
    for t in TYPES:
        n = len(list((D / "test" / t).glob("*.png")))
        items += [(t, i) for i in range(n) if i != ORACLE[t]]
    return items


def exemplar_sets(run: dict) -> dict:
    sd = RUNS / run["id"] / "samples"
    forged, seen = [], {}
    for s in run["samples"]:
        if s["status"] == "accepted" and seen.get(s["defect_type"], 0) < 2:
            seen[s["defect_type"]] = seen.get(s["defect_type"], 0) + 1
            forged.append((s["id"], f"DEFECT, type {s['defect_type']}", sd / f"{s['id']}_composite.jpg"))
    good = [(f"good{i}", "GOOD part", D / "train" / "good" / f"{i:03d}.png") for i in (0, 1)]
    real = [(f"real-{t}", f"DEFECT, type {t}", D / "test" / t / f"{ORACLE[t]:03d}.png") for t in TYPES]
    return {"C0": [], "C1": good, "C2": good + forged, "C3": good + real}


def load_ex(ex):
    return [(label, load_image(p)) for _, label, p in ex]


def run_condition(cond: str, ex) -> list[dict]:
    exs = load_ex(ex)

    def one(item):
        t, i = item
        img = load_image(D / "test" / t / f"{i:03d}.png")
        r = inspect(img, DEFAULT_SPEC, TYPES, exemplars=exs or None, with_mask=False, cache_key=f"eval-{cond}-v1")
        row = {"truth": t, "id": i, "defect": r["defect"], "type": r["type"], "confidence": r["confidence"],
               "box": r["box_px"], "rationale": r["rationale"][:200]}
        if t != "good" and r["box_px"]:
            gt = np.array(Image.open(D / "ground_truth" / t / f"{i:03d}_mask.png")) > 0
            x0, y0, x1, y1 = r["box_px"]
            row["box_hit"] = bool(gt[y0:y1, x0:x1].any())
        return row

    return pmap(one, test_items())


def score(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["truth"] != "good"]
    neg = [r for r in rows if r["truth"] == "good"]
    tp = sum(r["defect"] for r in pos)
    tn = sum(not r["defect"] for r in neg)
    by_type = {t: {"n": sum(r["truth"] == t for r in pos), "detected": sum(r["defect"] for r in pos if r["truth"] == t)} for t in TYPES}
    return {"n_good": len(neg), "n_defect": len(pos), "recall": round(tp / len(pos), 3), "recall_ci": list(sev.wilson(tp, len(pos))),
            "specificity": round(tn / len(neg), 3), "specificity_ci": list(sev.wilson(tn, len(neg))),
            "type_accuracy": round(sum(r["type"] == r["truth"] for r in pos if r["defect"]) / max(1, tp), 3),
            "box_hit": round(sum(r.get("box_hit", False) for r in pos) / len(pos), 3), "by_type": by_type}


def mcnemar_exact(a: list[bool], b: list[bool]) -> float:
    """Two-sided exact McNemar p-value on paired correctness."""
    from math import comb
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return 1.0
    k = min(n01, n10)
    return round(min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n), 4)


def correct(rows):
    return [r["defect"] == (r["truth"] != "good") for r in rows]


# ---------------------------------------------------------------- 3. SAM 3.1 on real defects

def sam_real() -> list[dict]:
    items = [(t, i) for t in TYPES for i in range(len(list((D / "test" / t).glob("*.png"))))]

    def one(item):
        t, i = item
        img = load_image(D / "test" / t / f"{i:03d}.png")
        gt = np.array(Image.open(D / "ground_truth" / t / f"{i:03d}_mask.png")) > 0
        ys, xs = np.nonzero(gt)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        r = sam_segment(img, boxes=[box], op="eval_sam_real")
        m = next((o["mask"] for o in r["objects"] if o["mask"] is not None), None)
        return {"type": t, "id": i, "iou": round(iou(m, gt), 3) if m is not None else 0.0, "ms": round(r["ms"])}

    return pmap(one, items)


# ---------------------------------------------------------------- 5. faint-defect lift

def faint_lift(run: dict, ex_forged) -> list[dict]:
    ex_ids = {e[0] for e in ex_forged}
    exs = load_ex(ex_forged)
    pts = [p for p in run["severity"] if (p["kind"], p["level"]) in HARD and p["sample_id"] not in ex_ids]
    run_dir = RUNS / run["id"]

    def one(p):
        img = Image.open(run_dir / "severity" / f"{p['sample_id']}_{p['kind']}_{p['level']}.jpg").convert("RGB")
        r = inspect(img, DEFAULT_SPEC, TYPES, exemplars=exs, with_mask=False, cache_key="eval-faint-C2-v1")
        return {**{k: p[k] for k in ("sample_id", "defect_type", "kind", "level")}, "zero_shot": p["detected"], "with_forged": r["defect"]}

    return pmap(one, pts)


def total_spend(new: float) -> float:
    p = RAW / "spend.json"
    prev = json.loads(p.read_text())["usd"] if p.exists() else 0.0
    p.write_text(json.dumps({"usd": round(prev + new, 4)}))
    return prev + new


def direction(before: int, after: int, p: float) -> str:
    if p >= 0.05:
        return "no significant change."
    if after < before:
        return ("a significant drop: with forged examples in the prompt, the inspector flagged fewer faint defects. "
                "The cause is untested; one guess is that full-strength examples raise its bar.")
    return "a significant lift."


def revalidation() -> dict | None:
    p = RESULTS / "revalidation.json"
    return json.loads(p.read_text()) if p.exists() else None


def blind_spot_summary(rv: dict | None):
    p = RESULTS / "blind_spot.json"
    if not p.exists() or not rv:
        return None
    b = json.loads(p.read_text())
    o, a = b["original_spec"], b["amended_spec"]
    w = rv["white"]["conditions"]
    names = {"W0": "spec only", "W1": "+ 2 good photos", "W2": "+ 2 forged white prints", "W3": "+ 2 good photos + 2 forged white prints"}
    rows = [{"label": f"Real print, {names[c]} (3 passes pooled)", "tone": "signal" if c == "W0" else "pass",
             "detected": sum(w[c]["print_per_pass"]), "n": w[c]["n_print"] * len(w[c]["print_per_pass"])} for c in names]
    rows += [{"label": f"False alarms on real good parts, {names[c]} (3 passes pooled)", "tone": "signal",
              "detected": sum(w[c]["good_flagged_per_pass"]), "n": w[c]["n_good"] * len(w[c]["good_flagged_per_pass"])} for c in names]
    rows += [{"label": "Bold forged white print, spec only (single pass)", "tone": "signal", **{k: o["forged_white_print"][k] for k in ("detected", "n")}},
             {"label": "Real print, spec with the one-clause amendment (single pass)", "tone": "pass", **{k: a["real_print"][k] for k in ("detected", "n")}},
             {"label": "False alarms on real good parts, amended spec (single pass)", "tone": "signal", **{k: a["real_good_false_alarms"][k] for k in ("detected", "n")}}]
    credit = rv["white"]["forged_examples_get_credit"]
    verdict = ("Under the rule fixed in advance, the forged white-print examples earn credit." if credit else
               "Under the rule fixed in advance, the forged white-print examples earn no credit: "
               f"forged examples alone vs spec only gave p = {rv['white']['p_w2_vs_w0']}.")
    return {"finding": ("Real print is the inspector's weakest real defect: white print is read as gloss. Bold forged white print was caught 12/12, "
                        f"so forging did not reproduce the real misses. {verdict} This replaces our earlier claim, which was confounded "
                        "because that run also contained 2 good photos."),
            "amendment": b["amendment"], "rows": rows, "credit": credit}


# ---------------------------------------------------------------- report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=15)
    ap.add_argument("--parts", type=int, default=16)
    a = ap.parse_args()
    t0 = time.time()
    spend0 = ledger.spent()

    run = forge_batch(a.per_type, a.parts)
    print("forge run complete:", run["summary"], flush=True)
    exs = exemplar_sets(run)
    conds = {}
    for c in ("C0", "C1", "C2", "C3"):
        conds[c] = cached(f"cond_{c}", lambda c=c: run_condition(c, exs[c]))
        print(c, score(conds[c]), flush=True)
    sam = cached("sam_real", sam_real)
    forged_ex = [e for e in exs["C2"] if not e[0].startswith("good")]
    faint = cached("faint_lift", lambda: faint_lift(run, forged_ex))

    ss = run["samples"]
    acc = [s for s in ss if s["status"] == "accepted"]
    ious = [s["sam_iou"] for s in acc if s["sam_iou"] is not None]
    attempts = sum(s["attempt"] for s in ss)
    vals = [v["passed"] for s in ss for v in s["validators"]]
    run_cost = run["summary"]["cost_usd"]       # the original forge+stress run, before any revalidation calls
    forge_cost = sum(s["cost_usd"] for s in ss)
    labels = {"C0": "spec only", "C1": "+2 good examples", "C2": "+8 forged defects", "C3": "+4 real defects (oracle)"}
    in_ctx = []
    for c in ("C0", "C1", "C2", "C3"):
        sc = score(conds[c])
        in_ctx.append({"condition": c, "label": labels[c], "recall": sc["recall"], "specificity": sc["specificity"],
                       "n": sc["n_good"] + sc["n_defect"], "type_accuracy": sc["type_accuracy"], "box_hit": sc["box_hit"]})
    p_c2_c1 = mcnemar_exact(correct(conds["C1"]), correct(conds["C2"]))
    fz = sum(r["zero_shot"] for r in faint)
    fw = sum(r["with_forged"] for r in faint)
    p_faint = mcnemar_exact([r["zero_shot"] for r in faint], [r["with_forged"] for r in faint])
    by_type_iou = {t: round(float(np.median([r["iou"] for r in sam if r["type"] == t])), 3) for t in TYPES}
    first_pass = sev.curves(run["severity"])
    rv = revalidation()
    curves = rv["stress"]["curves"] if rv else first_pass
    report = {
        "generated": time.time(),
        "real_benchmark": score(conds["C0"]),
        "in_context": in_ctx,
        "faint_lift": [{"condition": "C0", "label": "spec only", "detected": fz, "n": len(faint)},
                       {"condition": "C2", "label": "+8 forged defects", "detected": fw, "n": len(faint)}],
        "sam_real": {"n": len(sam), "median_iou": round(float(np.median([r["iou"] for r in sam])), 3),
                     "mean_iou": round(float(np.mean([r["iou"] for r in sam])), 3), "by_type": by_type_iou},
        "forge_stats": {"attempted": len(ss), "accepted": len(acc), "acceptance_rate": round(len(acc) / max(1, len(ss)), 3),
                        "edit_attempts": attempts, "mean_sam_iou": round(float(np.mean(ious)), 3) if ious else None,
                        "cost_per_accepted_usd": round(forge_cost / max(1, len(acc)), 4),
                        "seconds_per_accepted": round(float(np.mean([s["ms"] for s in acc])) / 1000, 1) if acc else None,
                        "validator_pass_rate": round(sum(vals) / max(1, len(vals)), 3), "run_cost_usd": round(run_cost, 2)},
        "curves": curves,
        "stats": {"mcnemar_C2_vs_C1": p_c2_c1, "mcnemar_faint": p_faint},
        "notes": [
            f"Benchmark: MVTec AD hazelnut test split, {score(conds['C0'])['n_defect']} defective + 40 good scored (4 oracle images held out).",
            f"In-context C2 vs C1: exact McNemar p = {p_c2_c1}.",
            f"Faint-defect test (hardest 3 severity levels, {len(faint)} images): spec only {fz} vs with 8 forged examples {fw} detected, "
            f"exact McNemar p = {p_faint}: " + direction(fz, fw, p_faint),
            "Equivalent diameters in mm assume the spec's 20 mm nominal hazelnut width.",
            f"Total Meta API spend for this evaluation (all stages, cumulative across resumed runs): ${total_spend(ledger.spent() - spend0):.2f}.",
        ],
    }
    report["curves_first_pass"] = first_pass
    report["blind_spot"] = blind_spot_summary(rv)
    if rv:
        st, c0, fc = rv["stress"], rv["c0"], rv["faint"]
        report["revalidation"] = rv
        bd = RESULTS / "box_distance.json"
        report["box_distance"] = json.loads(bd.read_text()) if bd.exists() else None
        reval_usd = json.loads((RAW / "spend_revalidation.json").read_text())["usd"]
        report["notes"] = [
            f"Curves: a variant counts as caught when the inspector's box overlaps the defect in at least 2 of 3 passes. All 3 passes agreed on {st['unanimous_rate']:.0%} of {st['variants']} variants.",
            f"False-alarm control: {st['controls']['flagged']}/{st['controls']['n']} inspections of unedited source parts were flagged ({st['controls']['parts']} parts, 3 passes). "
            f"{st['flagged_elsewhere']} variants were flagged in the wrong place.",
            "Real benchmark over 3 passes: recall " + ", ".join(f"{x:.1%}" for x in c0["recall_per_pass"]) + "; specificity " + ", ".join(f"{x:.1%}" for x in c0["specificity_per_pass"]) + ".",
            "Faint-defect check: spec-only passes flagged " + ", ".join(str(x["spec_only"]) for x in fc["passes"]) + f" of {fc['passes'][0]['n']}; the single forged-examples pass flagged "
            f"{fc['with_forged']} (exact McNemar p = " + ", ".join(str(x["p"]) for x in fc["passes"]) + ").",
            "Tiny defects: for shrunken holes and prints the inspector's box often misses by 0.2-0.5 mm. It notices them but can't pinpoint them; "
            "see the box-accuracy table (a post-hoc check, not pre-registered).",
            f"Revalidation spend: ${reval_usd:.2f} of Meta API calls.",
            *report["notes"]]
    (RESULTS / "eval.json").write_text(json.dumps(report, indent=1))
    write_md(report)
    print(json.dumps({k: report[k] for k in ("real_benchmark", "in_context", "faint_lift", "sam_real", "forge_stats", "stats")}, indent=1))
    for c in curves:
        print(c["threshold_note"])


def write_md(r: dict) -> None:
    rb = r["real_benchmark"]
    L = ["# Evaluation results", "", "Generated by `python eval/run_eval.py` under the protocol in [`EVAL.md`](../../EVAL.md).", "",
         "## Headline: detection-threshold curves (Muse Spark inspector, forged hazelnut defects)", "",
         "Caught means the inspector's box overlaps the defect in at least 2 of 3 passes (EVAL.md addendum, R1).", "",
         "| Defect | " + " | ".join(f"{k} {l:g}" for k, l in sev.LEVELS) + " |", "|---|" + "---|" * len(sev.LEVELS)]
    for c in r["curves"]:
        cells = {(x["kind"], x["level"]): x for x in c["cells"]}
        row = []
        for k, l in sev.LEVELS:
            x = cells.get((k, l))
            row.append(f"{x['detected']}/{x['n']}" + (f" (~{x['mean_size_mm']} mm)" if k == "size" and x.get("mean_size_mm") else "") if x else "")
        L.append(f"| {c['defect_type']} | " + " | ".join(row) + " |")
    L += [""] + [f"- {c['threshold_note']}" for c in r["curves"]] + ["",
          "## Real benchmark (MVTec AD hazelnut test split, spec-only inspector)", "",
          f"- Recall **{rb['recall']:.1%}** (95% CI {rb['recall_ci'][0]:.1%}–{rb['recall_ci'][1]:.1%}) on {rb['n_defect']} defective images",
          f"- Specificity **{rb['specificity']:.1%}** (95% CI {rb['specificity_ci'][0]:.1%}–{rb['specificity_ci'][1]:.1%}) on {rb['n_good']} good images",
          f"- Type accuracy {rb['type_accuracy']:.1%} (of detected), box hit {rb['box_hit']:.1%}",
          "", "## In-context examples", "", "| Condition | Recall | Specificity | Type acc. | n |", "|---|---|---|---|---|"]
    for x in r["in_context"]:
        L.append(f"| {x['condition']} {x['label']} | {x['recall']:.1%} | {x['specificity']:.1%} | {x['type_accuracy']:.1%} | {x['n']} |")
    f = r["faint_lift"]
    s = r["sam_real"]
    fs = r["forge_stats"]
    L += ["", f"Exact McNemar C2 vs C1: p = {r['stats']['mcnemar_C2_vs_C1']}.", "",
          "## Faint-defect lift (hardest three severity levels)", "",
          f"- Spec only: {f[0]['detected']}/{f[0]['n']} detected; with 8 forged examples: {f[1]['detected']}/{f[1]['n']} (exact McNemar p = {r['stats']['mcnemar_faint']}): "
          + direction(f[0]['detected'], f[1]['detected'], r['stats']['mcnemar_faint']),
          "", "## SAM 3.1 on real defects (tight ground-truth box prompts)", "",
          f"- Median IoU {s['median_iou']} (mean {s['mean_iou']}) over {s['n']} real defects; by type: " + ", ".join(f"{k} {v}" for k, v in s["by_type"].items()),
          "", "## Forge statistics", "",
          f"- {fs['accepted']}/{fs['attempted']} samples accepted ({fs['acceptance_rate']:.0%}) after {fs['edit_attempts']} Muse Image edits (critic-driven retries)",
          f"- Mean SAM-vs-diff IoU {fs['mean_sam_iou']}; validator pass rate {fs['validator_pass_rate']:.0%}",
          f"- ${fs['cost_per_accepted_usd']} and {fs['seconds_per_accepted']} s per accepted, pixel-labeled sample; whole forge+stress run ${fs['run_cost_usd']}",
          ""]
    rv = r.get("revalidation")
    if r.get("box_distance"):
        bd = r["box_distance"]
        L += [f"## Box accuracy on small defects (post-hoc, not pre-registered)", "",
              f"Strict overlap can understate detection when a tiny defect and a slightly offset box don't touch. This table recounts each variant "
              f"as noticed when the box lands within {bd['tol_mm']:g} mm of the defect in at least 2 of 3 passes.", "",
              "| Defect | Level | Box overlaps | Box within 1 mm | Median miss when off target |", "|---|---|---|---|---|"]
        for c in bd["cells"]:
            if c["kind"] == "size":
                miss = f"{c['median_miss_mm']} mm" if c["median_miss_mm"] is not None else "-"
                L.append(f"| {c['type']} | size {c['level']:g} | {c['overlap']}/{c['n']} | {c['near']}/{c['n']} | {miss} |")
        L.append("")
    if rv:
        L += ["## Real and forged at matched size (R4)", "",
              "Forged defects are much smaller than MVTec's, so the band where both exist is narrow. Below the smallest real defect, "
              "the curves have no real-world check until the physical test in `eval/home_check.py` is done.", "",
              "| Defect | Real median | Smallest real | Largest forged | Overlap band | Real caught in band | Forged caught in band | Real caught overall |",
              "|---|---|---|---|---|---|---|---|"]
        for x in rv["size_match"]:
            band = f"{x['band_mm'][0]:.1f}-{x['band_mm'][1]:.1f} mm" if x["band_mm"] else "none"
            L.append(f"| {x['type']} | {x['real_median_mm']} mm | {x['real_min_mm']} mm | {x['forged_max_mm']} mm | {band} | {x['real_in_band']} | {x['forged_in_band']} | {x['real_all']} |")
        L.append("")
    if r.get("blind_spot"):
        b = r["blind_spot"]
        L += ["## White-print blind spot (R2)", "", b["finding"], "",
              "| Measurement | Result |", "|---|---|"] + [f"| {x['label']} | {x['detected']}/{x['n']} |" for x in b["rows"]] + [
              "", f"Spec amendment tested (exploratory, single pass): \"{b['amendment']}\"", ""]
    L += ["## Notes", ""] + [f"- {n}" for n in r["notes"]] + ["", "## Deviations from EVAL.md", "",
          "- 2 of the 60 forgeries failed on the API's transient 404 before the retry fix landed, and the critic rejected 3 cracks, "
          "leaving 12-15 accepted per type against a target of 15.",
          "- The single-pass curves, which counted any defect claim as caught, were replaced as the headline by the located 3-pass curves "
          "(addendum R1, committed before those runs). The originals are kept in `eval.json` as `curves_first_pass`.",
          "- Our first white-print conclusion was confounded and is withdrawn; R2 replaces it.",
          "- The white-print experiment itself was added after seeing the real misses, so it is exploratory.",
          "- The box-accuracy table was added after seeing the located curves, so it is post-hoc. The headline stays the pre-registered overlap measure.",
          "- The faint-defect comparison repeats the spec-only side three times, but the forged-examples side was run once.",
          "- Part masks now come from a Muse Spark box into SAM 3.1. The evaluated forgeries used the earlier point-prompt masks."]
    (RESULTS / "eval.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
