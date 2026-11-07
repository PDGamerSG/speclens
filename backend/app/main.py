"""Chief Skill API. Run: python -m uvicorn app.main:app --app-dir backend --port 8000"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import time

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import parts as parts_mod
from .config import BUDGET_USD, DATA, DEMO_MODE, FIXTURES, MODELS, RESULTS, ROOT, VAR
from .export.coco import export_run
from .forge.composite import overlay
from .forge.locate import load_image
from .forge.spec import DEFAULT_SPEC, taxonomy
from .inspect.inspector import inspect
from .meta import ledger
from .runs import manager
from .public import PUBLIC_MODE, PublicWorkspaceMiddleware, owner
from .workspace import routes as workspace_routes
from .workspace.routes import router as workspace_router

app = FastAPI(title="Chief Skill", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=[] if PUBLIC_MODE else ["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(PublicWorkspaceMiddleware)
app.include_router(workspace_router)


class TaxonomyIn(BaseModel):
    spec_text: str


class RunIn(BaseModel):
    spec_text: str
    taxonomy: dict
    part_ids: list[str]
    per_type: int = 4
    stress: bool = True


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": DEMO_MODE, "models": list(MODELS.values()), "spent_usd": ledger.spent(), "budget_usd": BUDGET_USD}


@app.get("/api/ledger")
def get_ledger(limit: int = 200):
    return {"calls": ledger.recent(limit), "spent_usd": ledger.spent(), "by_model": ledger.by_model()}


@app.get("/api/default-spec")
def default_spec():
    return {"spec_text": DEFAULT_SPEC}


@app.post("/api/taxonomy")
def post_taxonomy(body: TaxonomyIn):
    if DEMO_MODE:
        return json.loads((FIXTURES / "demo_run" / "run.json").read_text())["taxonomy"]
    try:
        return taxonomy(body.spec_text)
    except ledger.BudgetExceeded as e:
        raise HTTPException(402, str(e))


@app.get("/api/parts")
def get_parts():
    return {"parts": parts_mod.list_parts()}


@app.post("/api/parts")
async def post_parts(files: list[UploadFile] = File(...)):
    if DEMO_MODE:
        raise HTTPException(400, "uploads are disabled in demo mode")
    out = []
    for f in files[:10]:
        data = await f.read()
        out.append(await asyncio.to_thread(parts_mod.add_upload, data, f.filename or "upload.jpg"))
    return {"parts": out}


@app.post("/api/runs")
def post_run(body: RunIn):
    known = parts_mod.all_parts()
    if not DEMO_MODE:
        bad = [p for p in body.part_ids if p not in known]
        if bad or not body.part_ids:
            raise HTTPException(400, f"unknown or missing part ids: {bad}")
        if not body.taxonomy.get("defects"):
            raise HTTPException(400, "taxonomy has no defects")
        ledger.check_budget()
    rid = manager.create(body.spec_text, body.taxonomy, body.part_ids, max(1, min(body.per_type, 30)), body.stress)
    return {"run_id": rid}


@app.get("/api/runs")
def list_runs():
    return {"runs": manager.list()}


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    r = manager.get(rid)
    if r is None:
        raise HTTPException(404, "run not found")
    return r.data


@app.post("/api/runs/{rid}/stress")
def post_stress(rid: str):
    if DEMO_MODE:
        raise HTTPException(400, "stress is replayed as part of the demo run")
    try:
        manager.stress(rid)
    except KeyError:
        raise HTTPException(404, "run not found")
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.get("/api/runs/{rid}/events")
async def run_events(rid: str):
    r = manager.get(rid)
    if r is None:
        raise HTTPException(404, "run not found")

    async def gen():
        i, stop = r.stream_window()
        idle = 0
        while True:
            evs = r.events
            while i < len(evs):
                ev = evs[i]
                i += 1
                yield {"event": ev["event"], "data": json.dumps(ev["data"])}
                if ev["event"] in stop:
                    return
            if r.data.get("status") in ("completed", "failed") and i >= len(r.events):
                idle += 1
                if idle > 8:
                    return
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen(), ping=10)


@app.get("/api/runs/{rid}/export")
def export(rid: str):
    r = manager.get(rid)
    if r is None:
        raise HTTPException(404, "run not found")
    extra = [FIXTURES / "demo_run" / "samples"] if r.data.get("demo") else None
    return Response(export_run(r.dir, r.data, extra), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="chief-skill-{rid}.zip"'})


@app.post("/api/inspect")
async def post_inspect(file: UploadFile = File(...), spec_text: str = Form(""), use_examples_run_id: str = Form("")):
    data = await file.read()
    if DEMO_MODE:
        demo = FIXTURES / "demo_inspect" / "inspection.json"
        if demo.exists():
            return {**json.loads(demo.read_text()), "rationale": "[demo replay: recorded result] " + json.loads(demo.read_text())["rationale"]}
        raise HTTPException(400, "live inspection needs MODEL_API_KEY")
    img = load_image(io.BytesIO(data))
    h = hashlib.sha256(data).hexdigest()[:12]
    d = VAR / "inspections"
    ip = d / f"{h}.jpg"
    img.save(ip, "JPEG", quality=92)
    spec = spec_text.strip() or DEFAULT_SPEC
    types = ["hole", "crack", "cut", "print"]
    exemplars = []
    if use_examples_run_id:
        r = manager.get(use_examples_run_id)
        if r is not None:
            types = [x["defect_type"] for x in r.data["taxonomy"]["defects"]]
            seen: dict[str, int] = {}
            for s in r.data["samples"]:
                if s["status"] == "accepted" and seen.get(s["defect_type"], 0) < 2:
                    seen[s["defect_type"]] = seen.get(s["defect_type"], 0) + 1
                    exemplars.append((f"DEFECT, type {s['defect_type']}", Image.open(r.dir / "samples" / f"{s['id']}_composite.jpg")))
    try:
        res = await asyncio.to_thread(inspect, img, spec, types, exemplars=exemplars or None)
    except ledger.BudgetExceeded as e:
        raise HTTPException(402, str(e))
    mask = res.pop("mask")
    out = {**res, "image_url": f"/files/inspections/{h}.jpg", "overlay_url": None, "mask_url": None}
    if mask is not None:
        Image.fromarray((mask * 255).astype(np.uint8)).save(d / f"{h}_mask.png")
        ov = overlay(np.array(img), mask, color=(255, 60, 60))
        Image.fromarray(ov).save(d / f"{h}_overlay.jpg", "JPEG", quality=92)
        out.update({"overlay_url": f"/files/inspections/{h}_overlay.jpg", "mask_url": f"/files/inspections/{h}_mask.png"})
    (d / f"{h}.json").write_text(json.dumps({**out, "t": time.time()}))
    return out


@app.get("/api/eval")
def get_eval():
    p = RESULTS / "eval.json"
    if not p.exists():
        return {"generated": 0, "real_benchmark": None, "in_context": [], "faint_lift": [], "sam_real": None,
                "forge_stats": None, "curves": [], "notes": ["eval has not been run yet: python eval/run_eval.py"]}
    return json.loads(p.read_text())


app.mount("/files/fixtures", StaticFiles(directory=FIXTURES, check_dir=False), name="fixtures")
if (DATA / "mvtec").exists():
    app.mount("/files/mvtec", StaticFiles(directory=DATA / "mvtec"), name="mvtec")
# Publish media directories individually. VAR also contains private SQLite records
# and the API ledger, which must never be reachable through StaticFiles.
for directory in ('parts', 'runs', 'inspections'):
    app.mount(f'/files/{directory}', StaticFiles(directory=VAR / directory, check_dir=False), name=directory)


@app.get('/files/workspace/{filename}')
def workspace_image(filename: str, request: Request):
    if not filename.endswith('.jpg'):
        raise HTTPException(404, 'Photo not found.')
    item = workspace_routes.service.store.inspection(filename[:-4])
    if item is None or item.get('owner_id', '') != owner(request):
        raise HTTPException(404, 'Photo not found.')
    path = workspace_routes.service.media_root / filename
    if not path.is_file():
        raise HTTPException(404, 'Photo not found.')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets", check_dir=False), name="assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(_dist / "favicon.svg")

    @app.get("/")
    def spa():
        # index.html must never be cached: it points at the current hashed bundle
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
