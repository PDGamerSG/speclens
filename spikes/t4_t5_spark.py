"""T4: Spark inspector headroom (C0 zero-shot / C1 +good / C2 +forged / C3 +real oracle) on 20 test images.
T5: Spark critic on forged composites, with real-defect crops as a calibration control, plus a blind rating sheet.

usage: python spikes/t4_t5_spark.py t4 | t5
"""
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from forge_lib import DEFECTS, crop_around
from metaapi import ROOT, RUNS, data_url, load_rgb, spark_json, to_bytes
from t1_t2_forge import part_center

D = ROOT / "data/gate/hazelnut"
F = RUNS / "forge"

SPEC = """You are a visual quality inspector for whole hazelnuts photographed top-down on a dark background.
ACCEPT (good): natural shell colour variation, stripes, the rough fuzzy cap area, small natural specks, shadows.
REJECT (defect), with type:
- crack: any split, fracture or broken-away piece of shell
- cut: a slice, notch or knife cut through the shell
- hole: a drilled, bored or punctured hole of any size
- print: any ink, stamp, printed characters or marking on the shell
Report a bounding box around the defect on a 0-1000 grid (x0,y0 top-left; x1,y1 bottom-right). If good, set has_box false and all coordinates 0."""

INSPECT = {"type": "object", "additionalProperties": False,
           "required": ["defect", "type", "has_box", "x0", "y0", "x1", "y1", "confidence", "rationale"],
           "properties": {"defect": {"type": "boolean"},
                          "type": {"type": "string", "enum": ["good", "crack", "cut", "hole", "print"]},
                          "has_box": {"type": "boolean"}, "x0": {"type": "integer"}, "y0": {"type": "integer"},
                          "x1": {"type": "integer"}, "y1": {"type": "integer"},
                          "confidence": {"type": "number"}, "rationale": {"type": "string"}}}

CRITIC = {"type": "object", "additionalProperties": False,
          "required": ["realism", "matches_type", "artifacts", "verdict", "revised_prompt"],
          "properties": {"realism": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                         "matches_type": {"type": "boolean"}, "artifacts": {"type": "string"},
                         "verdict": {"type": "string", "enum": ["accept", "reject"]},
                         "revised_prompt": {"type": "string"}}}


def jpg_url(img: Image.Image, side: int = 768) -> str:
    im = img.copy()
    im.thumbnail((side, side), Image.LANCZOS)
    return data_url(to_bytes(im, "JPEG", 90))


def forged_full(defect: str, idx: int, offset) -> Image.Image:
    """Paste a T2 text-style composite crop back into its full source image."""
    src = load_rgb(D / f"train/good/{idx:03d}.png")
    cx, cy = part_center(src)
    _, (x0, y0) = crop_around(src, cx + offset[0], cy + offset[1])
    comp = Image.open(F / f"t2_{defect}_text_low_notools_{idx:03d}_composite.png").convert("RGB")
    src.paste(comp, (x0, y0))
    return src


OFFSETS = {1: (0, 0), 2: (-60, 40), 3: (50, -50), 4: (40, 60), 5: (-50, -40)}


def exemplars(cond: str):
    parts = []
    def add(label, img):
        parts.append({"type": "text", "text": label})
        parts.append({"type": "image_url", "image_url": {"url": jpg_url(img)}})
    if cond in ("C1", "C2", "C3"):
        for i in (0, 1):
            add(f"Reference example: GOOD part.", load_rgb(D / f"train/good/{i:03d}.png"))
    if cond == "C2":
        for d in ("hole", "crack", "print"):
            for i in (1, 2):
                add(f"Reference example: DEFECT, type {d}.", forged_full(d, i, OFFSETS[i]))
    if cond == "C3":
        for d in ("crack", "cut", "hole", "print"):
            add(f"Reference example: DEFECT, type {d}.", load_rgb(D / f"test/{d}/005.png"))
    return parts


def queries():
    q = [("good", i) for i in range(10)]
    q += [("crack", i) for i in range(3)] + [("cut", i) for i in range(2)] + [("hole", i) for i in range(3)] + [("print", i) for i in range(2)]
    return q


def inspect(cond, ex_parts, q):
    t, i = q
    img = load_rgb(D / f"test/{t}/{i:03d}.png")
    msgs = [{"role": "system", "content": SPEC},
            {"role": "user", "content": [*ex_parts, {"type": "text", "text": "Inspect this part."},
                                         {"type": "image_url", "image_url": {"url": jpg_url(img)}}]}]
    r = spark_json(msgs, INSPECT, "inspection", cache_key=f"hazelnut-gate-{cond}-v1")
    out = r["data"]
    row = {"cond": cond, "truth": t, "id": i, "pred_defect": out["defect"], "pred_type": out["type"],
           "conf": out["confidence"], "ms": round(r["ms"]), "prompt_tokens": r["prompt_tokens"], "cached": r["cached"],
           "rationale": out["rationale"][:160]}
    if t != "good" and out["has_box"]:
        gt = np.array(Image.open(D / f"ground_truth/{t}/{i:03d}_mask.png")) > 0
        H, W = gt.shape
        x0, y0, x1, y1 = [int(np.clip(v, 0, 1000) / 1000 * s) for v, s in zip((out["x0"], out["y0"], out["x1"], out["y1"]), (W, H, W, H))]
        row["box_hit"] = bool(gt[min(y0, y1):max(y0, y1) + 1, min(x0, x1):max(x0, x1) + 1].any())
    return row


def summarize(rows):
    out = {}
    for c in sorted({r["cond"] for r in rows}):
        rs = [r for r in rows if r["cond"] == c]
        pos = [r for r in rs if r["truth"] != "good"]
        neg = [r for r in rs if r["truth"] == "good"]
        tp = sum(r["pred_defect"] for r in pos)
        tn = sum(not r["pred_defect"] for r in neg)
        typed = sum(r["pred_type"] == r["truth"] for r in pos)
        hits = sum(r.get("box_hit", False) for r in pos)
        out[c] = {"recall": f"{tp}/{len(pos)}", "specificity": f"{tn}/{len(neg)}",
                  "balanced_acc": round((tp / len(pos) + tn / len(neg)) / 2, 3),
                  "type_correct": f"{typed}/{len(pos)}", "box_hit": f"{hits}/{len(pos)}",
                  "p50_ms": int(np.median([r["ms"] for r in rs])),
                  "mean_prompt_tokens": int(np.mean([r["prompt_tokens"] for r in rs])),
                  "cached_calls": sum(1 for r in rs if r["cached"])}
    return out


def t4():
    jobs = []
    for c in ("C0", "C1", "C2", "C3"):
        ex = exemplars(c)
        jobs += [(c, ex, q) for q in queries()]
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(lambda a: inspect(*a), jobs))
    (RUNS / "t4_results.json").write_text(json.dumps(rows, indent=1))
    s = summarize(rows)
    (RUNS / "t4_summary.json").write_text(json.dumps(s, indent=1))
    for c, v in s.items():
        print(c, v)
    for r in rows:
        if (r["truth"] == "good") == r["pred_defect"]:
            print("  miss:", r["cond"], r["truth"], r["id"], "->", r["pred_type"], "|", r["rationale"][:110])


def crop512(img: Image.Image, cx: int, cy: int) -> Image.Image:
    return crop_around(img, cx, cy)[0]


def critic_one(label, img, defect):
    msgs = [{"role": "system", "content": "You are a strict reviewer of synthetic training images for industrial inspection. "
             "Judge whether the defect in the image looks like a real, physically plausible defect photographed with the same camera "
             "and lighting as the rest of the image. Penalize pasted-looking edges, wrong lighting, painterly texture, blur mismatch, "
             "and defects that do not match the requested type."},
            {"role": "user", "content": [
                {"type": "text", "text": f"Requested defect type: {defect} ({DEFECTS[defect]}). Rate realism 1-5 (5 = indistinguishable from a real photo). "
                                         "verdict accept if realism >= 4 and the type matches. If rejecting, write a revised_prompt for the image editor; else empty string."},
                {"type": "image_url", "image_url": {"url": jpg_url(img, 512)}}]}]
    r = spark_json(msgs, CRITIC, "critic")
    return {"item": label, "defect": defect, **r["data"], "ms": round(r["ms"])}


def t5():
    jobs = []
    for d in ("hole", "crack", "print"):
        for st in ("text", "outline"):
            for i in range(1, 6):
                p = F / f"t2_{d}_{st}_low_notools_{i:03d}_composite.png"
                jobs.append((f"forged:{d}:{st}:{i}", Image.open(p).convert("RGB"), d))
    real = []
    for d in ("hole", "crack", "print"):
        for i in (0, 1, 2):
            img = load_rgb(D / f"test/{d}/{i:03d}.png")
            gt = np.array(Image.open(D / f"ground_truth/{d}/{i:03d}_mask.png")) > 0
            ys, xs = np.nonzero(gt)
            c = crop512(img, int(xs.mean()), int(ys.mean()))
            real.append((d, i, c))
            jobs.append((f"real:{d}:{i}", c, d))
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(lambda a: critic_one(*a), jobs))
    (RUNS / "t5_critic.json").write_text(json.dumps(rows, indent=1))
    for grp in ("forged", "real"):
        for d in ("hole", "crack", "print"):
            for st in (("text", "outline") if grp == "forged" else ("",)):
                rs = [r for r in rows if r["item"].startswith(f"{grp}:{d}:{st}")]
                if rs:
                    print(f"{grp:6s} {d:6s} {st:8s} realism={[r['realism'] for r in rs]} accept={sum(r['verdict']=='accept' for r in rs)}/{len(rs)}")
    # blind 2AFC-style sheet: 10 forged (text style) + 10 real crops, shuffled, with a separate answer key
    forged = random.Random(7).sample([(f"forged:{d}:{i}", Image.open(F / f"t2_{d}_text_low_notools_{i:03d}_composite.png").convert("RGB"))
                                      for d in ("hole", "crack", "print") for i in range(1, 6)], 10)
    reals = [(f"real:{d}:{i}", c) for d, i, c in real] + [("real:cut:0", crop512(load_rgb(D / "test/cut/000.png"), *[int(v.mean()) for v in np.nonzero(np.array(Image.open(D / "ground_truth/cut/000_mask.png")) > 0)][::-1]))]
    items = forged + reals[:10]
    random.Random(42).shuffle(items)
    sheet = Image.new("RGB", (5 * 260, 4 * 280), "white")
    dr = ImageDraw.Draw(sheet)
    key = {}
    for n, (label, im) in enumerate(items):
        x, y = (n % 5) * 260, (n // 5) * 280
        sheet.paste(im.resize((256, 256)), (x + 2, y + 22))
        dr.text((x + 8, y + 4), f"#{n + 1}", fill="black")
        key[n + 1] = label
    sheet.save(RUNS / "t5_blind_sheet.jpg", quality=90)
    (RUNS / "t5_blind_key.json").write_text(json.dumps(key, indent=1))
    print("blind sheet written (answer key separate)")


if __name__ == "__main__":
    {"t4": t4, "t5": t5}[sys.argv[1]]()
