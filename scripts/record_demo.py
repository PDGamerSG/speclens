"""Turn a completed live run (on Muse-Image-generated sample parts) into the committed DEMO_MODE fixture.

usage: python scripts/record_demo.py <run_id> [--inspect]
Copies JPEG artifacts only (no PNGs, no MVTec images), rewrites URLs to /files/fixtures/demo_run/, and with
--inspect records one live inspection of a forged sample for the demo Inspect page.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import FIXTURES, VAR  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()
    src = VAR / "runs" / a.run_id
    run = json.loads((src / "run.json").read_text())
    bad = [p for p in run["part_ids"] if not p.startswith("sample-")]
    if bad:
        sys.exit(f"refusing: run uses non-fixture parts {bad} (demo fixtures must be license-clean)")
    dst = FIXTURES / "demo_run"
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "samples").mkdir(parents=True)
    (dst / "severity").mkdir()
    for sub in ("samples", "severity"):
        for f in (src / sub).glob("*.jpg"):
            shutil.copy2(f, dst / sub / f.name)
        for f in (src / sub).glob("*_mask.png"):
            shutil.copy2(f, dst / sub / f.name)
    old, new = f"/files/runs/{a.run_id}/", "/files/fixtures/demo_run/"

    def rw(s: str) -> str:
        return s.replace(old, new)

    (dst / "run.json").write_text(rw(json.dumps({**run, "demo": True}, indent=1)))
    ev = (src / "events.jsonl").read_text(encoding="utf-8")
    (dst / "events.jsonl").write_text(rw(ev), encoding="utf-8")
    print("demo fixture written:", dst, "samples", len(run["samples"]), "severity", len(run["severity"]))

    if a.inspect:
        from PIL import Image
        import numpy as np
        from app.forge.composite import overlay
        from app.inspect.inspector import inspect
        acc = [s for s in run["samples"] if s["status"] == "accepted"]
        s = acc[0]
        img = Image.open(src / "samples" / f"{s['id']}_composite.jpg").convert("RGB")
        types = [d["defect_type"] for d in run["taxonomy"]["defects"]]
        r = inspect(img, run["spec_text"], types)
        out = FIXTURES / "demo_inspect"
        out.mkdir(exist_ok=True)
        img.save(out / "image.jpg", quality=92)
        mask = r.pop("mask")
        res = {**r, "image_url": "/files/fixtures/demo_inspect/image.jpg", "overlay_url": None, "mask_url": None}
        if mask is not None:
            Image.fromarray(overlay(np.array(img), mask, color=(255, 60, 60))).save(out / "overlay.jpg", quality=92)
            res["overlay_url"] = "/files/fixtures/demo_inspect/overlay.jpg"
        (out / "inspection.json").write_text(json.dumps(res, indent=1))
        print("demo inspection:", res["verdict"], res["type"], res["confidence"])


if __name__ == "__main__":
    main()
