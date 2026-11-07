"""Physical validation: run the spec-only Muse Spark inspector on photos of REAL parts you damaged yourself.

Put photos (phone or webcam, part on matte black paper, desk lamp) in folders named by condition, e.g.:
  eval/home_set/good/              undamaged nuts
  eval/home_set/hole_0.5mm/        drilled with a 0.5 mm bit (or a pin)
  eval/home_set/hole_1mm/          1 mm bit
  eval/home_set/hole_2mm/          2 mm bit
  eval/home_set/print_faint/       one light pen dot / stamp
  eval/home_set/print_strong/      clear ink mark
  eval/home_set/crack/             cracked with pliers
Then: python eval/home_check.py   ->  docs/results/home_check.json + a printed table.
Compare the real detection per size with the forged curve in docs/results/eval.md.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import RESULTS  # noqa: E402
from app.forge.locate import load_image  # noqa: E402
from app.forge.severity import wilson  # noqa: E402
from app.forge.spec import DEFAULT_SPEC  # noqa: E402
from app.inspect.inspector import inspect  # noqa: E402

HOME = ROOT / "eval" / "home_set"
EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def main():
    folders = [d for d in sorted(HOME.iterdir()) if d.is_dir()] if HOME.exists() else []
    items = [(d.name, f) for d in folders for f in sorted(d.iterdir()) if f.suffix.lower() in EXT]
    if not items:
        sys.exit(f"no photos found under {HOME} (see the docstring for the folder layout)")

    def one(it):
        label, f = it
        r = inspect(load_image(f), DEFAULT_SPEC, ["hole", "crack", "cut", "print"], with_mask=False)
        return {"condition": label, "file": f.name, "defect": r["defect"], "type": r["type"], "confidence": r["confidence"],
                "rationale": r["rationale"][:160]}

    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, items))
    summary = {}
    for label in dict.fromkeys(r["condition"] for r in rows):
        rs = [r for r in rows if r["condition"] == label]
        k = sum(r["defect"] for r in rs)
        summary[label] = {"n": len(rs), "flagged_defect": k, "rate": round(k / len(rs), 3), "ci": wilson(k, len(rs))}
        print(f"{label:16s} flagged {k}/{len(rs)}  (95% CI {summary[label]['ci'][0]:.0%}-{summary[label]['ci'][1]:.0%})")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "home_check.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
