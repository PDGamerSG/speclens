"""End-to-end smoke run against a running backend: spec -> taxonomy -> forge -> stress, printed as it streams.

usage: python scripts/smoke_run.py [--per-type 1] [--parts mvtec-hazelnut-000,mvtec-hazelnut-001] [--no-stress] [--base http://localhost:8765]
"""
import argparse
import json
import urllib.request


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8765")
    ap.add_argument("--per-type", type=int, default=1)
    ap.add_argument("--parts", default="")
    ap.add_argument("--no-stress", action="store_true")
    a = ap.parse_args()
    spec = call(a.base, "/api/default-spec")["spec_text"]
    tax = call(a.base, "/api/taxonomy", {"spec_text": spec})
    parts = a.parts.split(",") if a.parts else [p["id"] for p in call(a.base, "/api/parts")["parts"]][:2]
    rid = call(a.base, "/api/runs", {"spec_text": spec, "taxonomy": tax, "part_ids": parts, "per_type": a.per_type,
                                     "stress": not a.no_stress})["run_id"]
    print("run", rid, "types", [d["defect_type"] for d in tax["defects"]], "parts", parts)
    ev = None
    with urllib.request.urlopen(f"{a.base}/api/runs/{rid}/events", timeout=1800) as r:
        for raw in r:
            line = raw.decode().rstrip("\r\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:") and ev:
                d = json.loads(line[5:])
                if ev == "sample" and d["status"] in ("accepted", "rejected", "failed"):
                    bad = [v["id"] for v in d["validators"] if not v["passed"]]
                    print(f"  {d['id']} {d['defect_type']:6s} {d['status']:8s} try{d['attempt']} iou={d['sam_iou']} "
                          f"mm={d['size_mm']} realism={(d['critic'] or {}).get('realism')} failed={bad} ${d['cost_usd']} {d['ms']}ms {d.get('error', '')}")
                elif ev == "curves":
                    for c in d["curves"]:
                        print("  CURVE", c["threshold_note"])
                elif ev in ("run_completed", "error"):
                    print(ev, json.dumps(d))
                    break
    print("health", call(a.base, "/api/health"))


if __name__ == "__main__":
    main()
