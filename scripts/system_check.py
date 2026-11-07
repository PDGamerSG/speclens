"""Live end-to-end check of a running backend. Exits non-zero if any step fails. Costs about $0.30 of Meta API spend.

usage: python scripts/system_check.py [--base http://localhost:8765]
"""
import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)
    return bool(ok)


def get(base, path, raw=False):
    with urllib.request.urlopen(base + path, timeout=120) as r:
        data = r.read()
    return data if raw else json.loads(data)


def post(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def post_file(base, path, field, file: Path):
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="{field}"; filename="{file.name}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n").encode() + file.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(base + path, data=body, headers={"content-type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def stream(base, rid, stop, timeout=600):
    """Read the SSE stream the way the UI does; returns a count of events by name."""
    counts: dict[str, int] = {}
    ev = None
    with urllib.request.urlopen(f"{base}/api/runs/{rid}/events", timeout=timeout) as r:
        for raw in r:
            line = raw.decode().rstrip("\r\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
                counts[ev] = counts.get(ev, 0) + 1
                if ev in (stop, "error"):
                    break
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8765")
    a = ap.parse_args()
    base = a.base
    t0 = time.time()

    h = get(base, "/api/health")
    start_spend = sum(m["cost_usd"] for m in get(base, "/api/ledger?limit=1")["by_model"].values())
    check("backend is up in live mode", h["ok"] and not h["demo_mode"], str(h["models"]))
    check("UI is served", b"<div id=" in get(base, "/", raw=True))
    ev = get(base, "/api/eval")
    check("evaluation results load", len(ev["curves"]) == 4 and bool(ev.get("blind_spot")))

    spec = get(base, "/api/default-spec")["spec_text"]
    tax = post(base, "/api/taxonomy", {"spec_text": spec})
    check("Muse Spark reads the spec", len(tax["defects"]) >= 4, str([d["defect_type"] for d in tax["defects"]]))

    parts = [p["id"] for p in get(base, "/api/parts")["parts"] if p["id"].startswith("sample-")]
    check("sample parts listed", len(parts) >= 2, f"{len(parts)} parts")

    rid = post(base, "/api/runs", {"spec_text": spec, "taxonomy": tax, "part_ids": parts[:2], "per_type": 1, "stress": True})["run_id"]
    counts = stream(base, rid, "run_completed")
    check("forge run streams to completion", "run_completed" in counts and "error" not in counts, str(counts))
    run = get(base, f"/api/runs/{rid}")
    acc = [s for s in run["samples"] if s["status"] == "accepted"]
    check("forged defects accepted", len(acc) >= 2, f"{len(acc)} of {len(run['samples'])}; ${run['summary']['cost_usd']}")
    if acc:
        s = acc[0]
        check("every hard validator passed", all(v["passed"] for v in s["validators"] if v.get("hard", True)))
        for key in ("crop_composite_url", "composite_url", "mask_url", "overlay_url"):
            ok = len(get(base, s[key], raw=True)) > 500
            check(f"artifact serves: {key}", ok)
    pts = run["severity"]
    check("stress test ran with location checks", len(pts) == 7 * len(acc) and all("flagged" in p for p in pts),
          f"{len(pts)} points, {sum(p['detected'] for p in pts)} caught, {sum(p['flagged'] and not p['detected'] for p in pts)} box off")
    check("unedited controls ran", (run.get("controls") or {}).get("n", 0) >= 1, str(run.get("controls")))
    check("curves produced", len(run["curves"]) >= 1, "; ".join(c["threshold_note"][:60] for c in run["curves"][:2]))

    z = zipfile.ZipFile(io.BytesIO(get(base, f"/api/runs/{rid}/export", raw=True)))
    coco = json.loads(z.read("annotations.json"))
    check("COCO export is complete", len(coco["images"]) == len(acc) == len(coco["annotations"]), f"{len(coco['images'])} images")

    fixture = ROOT / "fixtures" / "parts" / "hazelnut_gen_01.jpg"
    forged = ROOT / "fixtures" / "demo_inspect" / "image.jpg"
    good = post_file(base, "/api/inspect", "file", fixture)
    check("inspect: good part", good["verdict"] == "good", f"{good['verdict']} {good['type']} {good['confidence']}")
    bad = post_file(base, "/api/inspect", "file", forged)
    check("inspect: forged defect with a SAM overlay", bad["verdict"] == "defect" and bool(bad["overlay_url"]), f"{bad['verdict']} {bad['type']} {bad['confidence']}")
    real = ROOT / "data" / "mvtec" / "hazelnut" / "test" / "hole" / "003.png"
    if real.exists():
        r = post_file(base, "/api/inspect", "file", real)
        check("inspect: real MVTec hole", r["verdict"] == "defect", f"{r['verdict']} {r['type']} {r['confidence']}")

    up = post_file(base, "/api/parts", "files", fixture)["parts"][0]
    check("photo upload makes a part mask", bool(up["mask_url"]), up["id"])

    post(base, f"/api/runs/{rid}/stress")
    try:
        post(base, f"/api/runs/{rid}/stress")
        busy = False
    except urllib.error.HTTPError as e:
        busy = e.code == 409
    check("second stress click is refused while busy", busy)
    c2 = stream(base, rid, "stress_completed")
    check("stress re-run streams its own results", c2.get("severity", 0) == 7 * len(acc) and "stress_completed" in c2, str(c2))
    check("run returns to completed", get(base, f"/api/runs/{rid}")["status"] == "completed")

    # remove the test upload so it doesn't appear in the gallery
    idx = ROOT / "var" / "parts" / "index.json"
    if idx.exists() and up["id"].startswith("upload-"):
        d = json.loads(idx.read_text())
        d.pop(up["id"], None)
        idx.write_text(json.dumps(d, indent=1))
        for f in (ROOT / "var" / "parts").glob(f"{up['id']}*"):
            f.unlink()

    spend = sum(m["cost_usd"] for m in get(base, "/api/ledger?limit=1")["by_model"].values()) - start_spend
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed in {time.time() - t0:.0f} s, ${spend:.2f} of Meta API spend")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
