"""Pipeline tests on a fake Meta transport: inspector sanitizer, a full forge run, export, and the demo-mode API."""
import io
import json
import time
import zipfile

import cv2
import numpy as np
from PIL import Image

import app.forge.locate as locate
import app.inspect.inspector as inspector
import app.runs as runs
from app.export.coco import export_run
from app.forge.spec import DEFAULT_SPEC

TAX = {"part_name": "hazelnut", "part_width_mm": 20, "defects": [
    {"defect_type": "hole", "clause": "4.1", "description": "a small dark hole", "severity_note": "any"},
    {"defect_type": "print", "clause": "4.4", "description": "a small ink stamp", "severity_note": "any"}]}


def fake_sam(img, *, text=None, boxes=None, points=None, run_id=None, op="segment"):
    w, h = img.size
    m = np.zeros((h, w), bool)
    if boxes:
        x0, y0, x1, y1 = boxes[0]
        m[y0:y1, x0:x1] = True
    else:
        m = locate.otsu_mask(img)
    return {"objects": [{"object_id": "1", "box": None, "mask": m, "confidence": 0.9}], "ms": 1, "cost_usd": 0.0}


def fake_edit(png, prompt, **kw):
    a = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    h, w = a.shape[:2]
    cv2.circle(a, (w // 2, h // 2), 12, (15, 10, 8), -1)
    a = cv2.resize(a, (int(w * 1.5), int(h * 1.5)))
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    return {"images": [buf.getvalue()], "ms": 1, "cost_usd": 0.0}


def fake_spark_box(*a, **k):
    return None


def fake_critic(*a, **k):
    return {"realism": 5, "matches_type": True, "artifacts": "", "verdict": "accept", "revised_prompt": "", "cost_usd": 0.0, "ms": 1}


def fake_spark(messages, schema, name, **kw):
    return {"data": {"defect": True, "type": "hole", "has_box": True, "x0": 400, "y0": 400, "x1": 600, "y1": 600,
                     "confidence": 0.9, "rationale": "dark hole"}, "ms": 1, "cost_usd": 0.0, "usage": {}}


def test_inspector_box_scaling_and_sanitizer(monkeypatch):
    monkeypatch.setattr(inspector, "spark_json", fake_spark)
    img = Image.new("RGB", (1000, 500), (120, 60, 30))
    monkeypatch.setattr(inspector, "sam_segment", lambda *a, **k: {"objects": [{"mask": np.zeros((500, 1000), bool)}], "cost_usd": 0.0})
    r = inspector.inspect(img, DEFAULT_SPEC, ["hole"])
    assert r["box_px"] == [400, 200, 600, 300]
    assert r["verdict"] == "uncertain"          # claimed defect, but SAM found nothing in the box
    m = np.zeros((500, 1000), bool)
    m[220:280, 450:550] = True
    monkeypatch.setattr(inspector, "sam_segment", lambda *a, **k: {"objects": [{"mask": m}], "cost_usd": 0.0})
    assert inspector.inspect(img, DEFAULT_SPEC, ["hole"])["verdict"] == "defect"


def test_full_forge_run_on_fake_transport(monkeypatch):
    monkeypatch.setattr(runs, "image_edit", fake_edit)
    monkeypatch.setattr(runs, "sam_segment", fake_sam)
    monkeypatch.setattr(runs, "critic", fake_critic)
    monkeypatch.setattr(locate, "sam_segment", fake_sam)
    monkeypatch.setattr(locate, "spark_box", fake_spark_box)
    monkeypatch.setattr(inspector, "spark_json", fake_spark)
    monkeypatch.setattr(runs, "DEMO_MODE", False)
    pid = "sample-hazelnut_gen_01"
    rid = runs.manager.create(DEFAULT_SPEC, TAX, [pid], per_type=1, stress=True)
    run = runs.manager.get(rid)
    for _ in range(300):
        if run.data["status"] != "running":
            break
        time.sleep(0.1)
    assert run.data["status"] == "completed", run.events[-3:]
    acc = [s for s in run.data["samples"] if s["status"] == "accepted"]
    assert len(acc) == 2
    s = acc[0]
    assert all(v["passed"] for v in s["validators"] if v["hard"])
    assert s["size_mm"] and s["sam_iou"] is not None
    assert len(run.data["severity"]) == 2 * 7 and run.data["curves"]
    names = {e["event"] for e in run.events}
    assert {"run_started", "sample", "stage", "severity", "curves", "stress_completed", "run_completed"} <= names
    z = zipfile.ZipFile(io.BytesIO(export_run(run.dir, run.data)))
    coco = json.loads(z.read("annotations.json"))
    assert len(coco["images"]) == 2 and len(coco["annotations"]) == 2
    assert "evaluation" in coco["info"]["intended_use"]


def test_demo_mode_api_routes():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    h = c.get("/api/health").json()
    assert h["demo_mode"] is True and "sam-3.1" in h["models"]
    assert "HAZELNUT" in c.get("/api/default-spec").json()["spec_text"]
    parts = c.get("/api/parts").json()["parts"]
    assert any(p["id"].startswith("sample-hazelnut_gen") for p in parts)
    assert c.get("/api/runs/does-not-exist").status_code == 404
    ev = c.get("/api/eval").json()
    assert "curves" in ev


def _finished_run(monkeypatch):
    monkeypatch.setattr(runs, "image_edit", fake_edit)
    monkeypatch.setattr(runs, "sam_segment", fake_sam)
    monkeypatch.setattr(runs, "critic", fake_critic)
    monkeypatch.setattr(locate, "sam_segment", fake_sam)
    monkeypatch.setattr(locate, "spark_box", fake_spark_box)
    monkeypatch.setattr(inspector, "spark_json", fake_spark)
    monkeypatch.setattr(runs, "DEMO_MODE", False)
    rid = runs.manager.create(DEFAULT_SPEC, TAX, ["sample-hazelnut_gen_02"], per_type=1, stress=True)
    run = runs.manager.get(rid)
    for _ in range(300):
        if run.data["status"] != "running":
            break
        time.sleep(0.1)
    assert run.data["status"] == "completed", run.events[-3:]
    return rid, run


def test_stress_rerun_streams_only_its_own_events(monkeypatch):
    rid, run = _finished_run(monkeypatch)
    assert run.stream_window() == (0, {"run_completed", "error"})
    n_before = len(run.events)
    runs.manager.stress(rid)
    start, stop = run.stream_window()
    assert start == n_before and "stress_completed" in stop and "run_completed" not in stop
    for _ in range(300):
        if run.data["status"] != "running":
            break
        time.sleep(0.1)
    assert run.data["status"] == "completed"
    new = [e["event"] for e in run.events[start:]]
    assert "severity" in new and new[-1] == "stress_completed" and "run_completed" not in new


def test_stress_rerun_is_refused_while_busy(monkeypatch):
    rid, run = _finished_run(monkeypatch)
    run.data["status"] = "running"
    try:
        runs.manager.stress(rid)
        raised = False
    except RuntimeError:
        raised = True
    run.data["status"] = "completed"
    assert raised


def test_stress_records_location_and_unedited_controls(monkeypatch):
    _, run = _finished_run(monkeypatch)
    assert run.data["controls"]["n"] == 1
    pts = run.data["severity"]
    assert all({"flagged", "detected", "box_px"} <= set(p) for p in pts)
    assert all(p["flagged"] or not p["detected"] for p in pts)   # located implies flagged


def test_part_mask_rejects_a_background_mask(monkeypatch):
    img = Image.new("RGB", (400, 400), (205, 195, 180))
    a = np.array(img)
    cv2.circle(a, (200, 200), 80, (110, 60, 30), -1)
    img = Image.fromarray(a)

    def background_sam(image, **kw):
        m = np.ones((400, 400), bool)
        m[120:280, 120:280] = False
        return {"objects": [{"mask": m}], "cost_usd": 0.0}

    monkeypatch.setattr(locate, "sam_segment", background_sam)
    monkeypatch.setattr(locate, "spark_box", lambda *a, **k: (100, 100, 300, 300))
    m, how = locate.part_mask(img)
    assert how == "otsu fallback" and 0.1 < m.mean() < 0.2 and m[200, 200] and not m[5, 5]


def test_part_mask_prefers_the_spark_box(monkeypatch):
    img = Image.new("RGB", (400, 400), (240, 240, 235))     # a nut on white paper on a dark desk
    a = np.array(img)
    a[:, :40] = (40, 30, 25)
    a[:, 360:] = (40, 30, 25)
    cv2.circle(a, (200, 200), 40, (110, 60, 30), -1)
    img = Image.fromarray(a)
    monkeypatch.setattr(locate, "spark_box", lambda *a, **k: (160, 160, 240, 240))
    monkeypatch.setattr(locate, "sam_segment", fake_sam)
    m, how = locate.part_mask(img)
    assert how.startswith("muse-spark") and m[200, 200] and not m[100, 100]


def test_crop_tightens_around_a_small_part():
    img = Image.new("RGB", (1024, 1024))
    assert locate.crop_size(img) == 512
    assert locate.crop_size(img, 700) == 512
    assert locate.crop_size(img, 300) == 300
    assert locate.crop_size(img, 60) == 192
