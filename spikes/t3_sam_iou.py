"""T3: SAM 3.1 box-prompt IoU on real hazelnut defects + concept-prompt part mask."""
import json, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from metaapi import ROOT, RUNS, load_rgb, sam_image

D = ROOT / "data/gate/hazelnut"
CASES = [("crack", i) for i in range(3)] + [("cut", i) for i in range(2)] + [("hole", i) for i in range(3)] + [("print", i) for i in range(2)]

def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0

def run(case, pad):
    t, i = case
    img = load_rgb(D / f"test/{t}/{i:03d}.png")
    gt = np.array(Image.open(D / f"ground_truth/{t}/{i:03d}_mask.png")) > 0
    ys, xs = np.nonzero(gt)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    W, H = img.size
    dx, dy = int((x1 - x0) * pad), int((y1 - y0) * pad)
    box = (max(0, x0 - dx), max(0, y0 - dy), min(W, x1 + dx), min(H, y1 + dy))
    r = sam_image(img, boxes=[tuple(int(v) for v in box)])
    m = next((o["mask"] for o in r["objects"] if o["mask"] is not None), None)
    score = iou(m, gt) if m is not None else 0.0
    return {"type": t, "id": i, "pad": pad, "iou": round(score, 3), "ms": round(r["ms"]),
            "gt_area_pct": round(100 * gt.mean(), 2), "got_mask": m is not None}

if __name__ == "__main__":
    part = sam_image(load_rgb(D / "train/good/000.png"), text="hazelnut")
    pm = next((o["mask"] for o in part["objects"] if o["mask"] is not None), None)
    print(f"concept 'hazelnut': {len(part['objects'])} objects, mask area {100*pm.mean():.1f}% of image, {part['ms']:.0f} ms" if pm is not None else f"concept: no mask {part}")
    if pm is not None:
        Image.fromarray((pm * 255).astype(np.uint8)).save(RUNS / "t3_part_mask.png")
    jobs = [(c, p) for c in CASES for p in (0.0, 0.2)]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda a: run(*a), jobs))
    for r in rows: print(r)
    for p in (0.0, 0.2):
        v = [r["iou"] for r in rows if r["pad"] == p]
        print(f"pad={p}: median IoU {np.median(v):.3f}, mean {np.mean(v):.3f}, min {min(v):.3f}")
    ms = [r["ms"] for r in rows]
    print(f"latency p50 {np.median(ms):.0f} ms, p90 {np.percentile(ms, 90):.0f} ms")
    (RUNS / "t3_results.json").write_text(json.dumps(rows, indent=1))
