"""Run engine: forge samples in parallel, stream events, stress-test the inspector, and replay recorded runs."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from . import parts as parts_mod
from .config import DEMO_MODE, FIXTURES, FORGE_WORKERS, MODELS, VAR
from .forge import severity as sev
from .forge.composite import composite, dhash, iou, overlay
from .forge.locate import crop_box, crop_size, load_image, part_width, sample_centres
from .forge.spec import critic, forge_prompt
from .forge.validators import accepted as is_accepted
from .forge.validators import run_validators
from .inspect.inspector import inspect
from .meta import ledger
from .meta.client import image_edit, sam_segment, to_png

RUNS = VAR / "runs"


def _save_jpg(arr_or_img, path: Path, q: int = 90) -> None:
    im = arr_or_img if isinstance(arr_or_img, Image.Image) else Image.fromarray(arr_or_img)
    im.convert("RGB").save(path, "JPEG", quality=q)


class Run:
    def __init__(self, rid: str, data: dict, demo: bool = False):
        self.id = rid
        self.dir = RUNS / rid
        (self.dir / "samples").mkdir(parents=True, exist_ok=True)
        (self.dir / "severity").mkdir(exist_ok=True)
        self.data = data
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.demo = demo
        self.accepted_hashes: list[int] = []
        self.stress_from: int | None = None      # event index where a separate stress re-run began

    def url(self, path: Path) -> str:
        return parts_mod.url_for(path)

    def stream_window(self) -> tuple[int, set[str]]:
        """Where an SSE stream starts and which events end it. A stress re-run streams only its own events,
        otherwise the replay would stop at the original run_completed and never reach the new results."""
        if self.stress_from is not None:
            return self.stress_from, {"stress_completed", "error"}
        return 0, {"run_completed", "error"}

    def emit(self, event: str, data: dict) -> None:
        with self.lock:
            ev = {"t": round(time.time(), 3), "event": event, "data": data}
            self.events.append(ev)
            with (self.dir / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
            if event == "sample":
                ss = self.data["samples"]
                for i, s in enumerate(ss):
                    if s["id"] == data["id"]:
                        ss[i] = data
                        break
                else:
                    ss.append(data)
            elif event == "severity":
                self.data["severity"].append(data)
            elif event == "curves":
                self.data["curves"] = data["curves"]
            elif event == "controls":
                self.data["controls"] = data
            elif event == "stress_completed" and self.stress_from is not None:
                self.data["status"] = "completed"
            elif event == "run_completed":
                self.data["status"] = "completed"
                self.data["summary"] = data["summary"]
            elif event == "error":
                self.data["status"] = "failed"
            if event in ("sample", "curves", "run_completed", "error", "stress_completed"):
                self.save()

    def save(self) -> None:
        (self.dir / "run.json").write_text(json.dumps(self.data, indent=1))


class Manager:
    def __init__(self):
        self.runs: dict[str, Run] = {}
        ledger.on_call(self._on_call)

    def _on_call(self, rec: dict) -> None:
        r = self.runs.get(rec.get("run_id") or "")
        if r is not None:
            r.emit("call", rec)

    def get(self, rid: str) -> Run | None:
        if rid in self.runs:
            return self.runs[rid]
        p = RUNS / rid / "run.json"
        if p.exists():
            r = Run(rid, json.loads(p.read_text()), demo=False)
            ev = RUNS / rid / "events.jsonl"
            if ev.exists():
                r.events = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.runs[rid] = r
            return r
        return None

    def list(self) -> list[dict]:
        out = []
        for p in sorted(RUNS.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            out.append({"id": d["id"], "created": d["created"], "status": d["status"], "per_type": d["per_type"],
                        "accepted": sum(1 for s in d["samples"] if s["status"] == "accepted"), "demo": d.get("demo", False)})
        return out

    # ------------------------------------------------------------------ create

    def create(self, spec_text: str, taxonomy: dict, part_ids: list[str], per_type: int, stress: bool) -> str:
        if DEMO_MODE:
            return self.replay()
        rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        data = {"id": rid, "created": time.time(), "status": "running", "spec_text": spec_text, "taxonomy": taxonomy,
                "part_ids": part_ids, "per_type": per_type, "samples": [], "severity": [], "curves": [], "controls": None,
                "summary": None, "demo": False}
        run = Run(rid, data)
        run.save()
        self.runs[rid] = run
        threading.Thread(target=self._execute, args=(run, stress), daemon=True).start()
        return rid

    def _execute(self, run: Run, stress: bool) -> None:
        t0 = time.time()
        try:
            tax = run.data["taxonomy"]
            jobs = self._plan(run)
            run.emit("run_started", {"run_id": run.id, "total_samples": len(jobs)})
            run.emit("stage", {"stage": "taxonomy", "status": "done", "detail": f"{len(tax['defects'])} defect classes"})
            run.emit("stage", {"stage": "locate", "status": "start"})
            for pid in run.data["part_ids"]:
                parts_mod.get_mask(pid, run_id=run.id)
            run.emit("stage", {"stage": "locate", "status": "done", "detail": f"{len(run.data['part_ids'])} part mask(s)"})
            with ThreadPoolExecutor(FORGE_WORKERS) as ex:
                list(ex.map(lambda j: self._forge_safe(run, *j), jobs))
            if stress:
                self._stress(run)
            ss = run.data["samples"]
            ious = [s["sam_iou"] for s in ss if s["status"] == "accepted" and s["sam_iou"] is not None]
            summary = {"accepted": sum(s["status"] == "accepted" for s in ss), "rejected": sum(s["status"] == "rejected" for s in ss),
                       "failed": sum(s["status"] == "failed" for s in ss),
                       "cost_usd": round(ledger.run_cost(run.id), 4),
                       "seconds": round(time.time() - t0, 1), "mean_sam_iou": round(float(np.mean(ious)), 3) if ious else None}
            run.emit("run_completed", {"summary": summary})
        except Exception as e:
            traceback.print_exc()
            run.emit("error", {"message": str(e)[:300]})

    def _plan(self, run: Run) -> list[tuple]:
        tax = run.data["taxonomy"]
        pids = run.data["part_ids"]
        rng = np.random.default_rng(int(hashlib.sha256(run.id.encode()).hexdigest()[:8], 16))
        jobs = []
        n_total = len(tax["defects"]) * run.data["per_type"]
        per_part = int(np.ceil(n_total / len(pids)))
        centres = {}
        for pid in pids:
            img = load_image(parts_mod.all_parts()[pid]["path"])
            mask = parts_mod.get_mask(pid, run_id=run.id)
            centres[pid] = sample_centres(mask, per_part, crop_size(img, part_width(mask)), rng)
        k = 0
        for i in range(run.data["per_type"]):
            for d in tax["defects"]:
                pid = pids[k % len(pids)]
                c = centres[pid][(k // len(pids)) % len(centres[pid])]
                jobs.append((f"s{k:03d}", pid, d, c))
                k += 1
        return jobs

    # ------------------------------------------------------------------ forge one sample

    def _forge_safe(self, run: Run, sid: str, pid: str, d: dict, centre) -> None:
        try:
            self._forge(run, sid, pid, d, centre)
        except ledger.BudgetExceeded as e:
            run.emit("error", {"message": str(e)})
        except Exception as e:
            traceback.print_exc()
            s = next((x for x in run.data["samples"] if x["id"] == sid), None)
            base = s or {"id": sid, "run_id": run.id, "part_id": pid, "defect_type": d["defect_type"], "attempt": 1, "prompt": "",
                         "original_url": "", "crop_original_url": "", "crop_raw_url": None, "crop_composite_url": None,
                         "composite_url": None, "mask_url": None, "overlay_url": None, "bbox": None, "area_px": 0,
                         "size_mm": None, "sam_iou": None, "critic": None, "validators": [], "cost_usd": 0.0, "ms": 0}
            run.emit("sample", {**base, "status": "failed", "error": str(e)[:200]})

    def _forge(self, run: Run, sid: str, pid: str, d: dict, centre) -> None:
        tax = run.data["taxonomy"]
        part = parts_mod.all_parts()[pid]
        img = load_image(part["path"])
        pmask = parts_mod.get_mask(pid, run_id=run.id)
        W, H = img.size
        part_w_px = part_width(pmask) or float(W)
        cs = crop_size(img, part_w_px)
        box = crop_box(img.size, centre[0], centre[1], cs)
        crop_img = img.crop(box)
        orig = np.array(crop_img)
        sd = run.dir / "samples"
        _save_jpg(crop_img, sd / f"{sid}_crop_original.jpg")
        prompt = forge_prompt(tax["part_name"], d["description"])
        t0 = time.time()
        cost = 0.0
        sample = {"id": sid, "run_id": run.id, "part_id": pid, "defect_type": d["defect_type"], "status": "forging", "attempt": 1,
                  "prompt": prompt, "original_url": parts_mod.describe(pid)["url"],
                  "crop_original_url": run.url(sd / f"{sid}_crop_original.jpg"), "crop_raw_url": None,
                  "crop_composite_url": None, "composite_url": None, "mask_url": None, "overlay_url": None, "bbox": None,
                  "area_px": 0, "size_mm": None, "sam_iou": None, "critic": None, "validators": [], "cost_usd": 0.0, "ms": 0}
        run.emit("sample", dict(sample))
        for attempt in (1, 2, 3):
            sample["attempt"] = attempt
            sample["prompt"] = prompt
            run.emit("stage", {"stage": "forge", "status": "start", "sample_id": sid})
            r = image_edit(to_png(crop_img), prompt, run_id=run.id)
            cost += r["cost_usd"]
            raw = Image.open(io.BytesIO(r["images"][0])).convert("RGB")
            _save_jpg(raw.resize(crop_img.size, Image.LANCZOS), sd / f"{sid}_crop_raw.jpg")
            run.emit("stage", {"stage": "composite", "status": "start", "sample_id": sid})
            comp = composite(orig, np.array(raw))
            cmask = comp["mask"]
            full = img.copy()
            full.paste(Image.fromarray(comp["composite"]), box[:2])
            fmask = np.zeros((H, W), bool)
            fmask[box[1]:box[3], box[0]:box[2]] = cmask
            _save_jpg(comp["composite"], sd / f"{sid}_crop_composite.jpg")
            sample.update({"crop_raw_url": run.url(sd / f"{sid}_crop_raw.jpg"),
                           "crop_composite_url": run.url(sd / f"{sid}_crop_composite.jpg")})
            # label: diff mask is exact by construction; SAM 3.1 tight box is an independent cross-check
            run.emit("stage", {"stage": "label", "status": "start", "sample_id": sid})
            sam_iou = None
            bbox = None
            if cmask.any():
                yy, xx = np.nonzero(cmask)
                cb = (int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1)
                bbox = [cb[0] + box[0], cb[1] + box[1], cb[2] + box[0], cb[3] + box[1]]
                try:   # independent cross-check only (V4 is advisory); never fail a sample on it
                    s = sam_segment(Image.fromarray(comp["composite"]), boxes=[cb], run_id=run.id, op="label")
                    cost += s["cost_usd"]
                    sm = next((o["mask"] for o in s["objects"] if o["mask"] is not None), None)
                    sam_iou = round(iou(sm, cmask), 3) if sm is not None else 0.0
                except ledger.BudgetExceeded:
                    raise
                except Exception:
                    sam_iou = None
            run.emit("stage", {"stage": "critic", "status": "start", "sample_id": sid})
            cr = critic(Image.fromarray(comp["composite"]), tax["part_name"], d["defect_type"], d["description"], run_id=run.id) if cmask.any() else None
            if cr:
                cost += cr.pop("cost_usd", 0.0)
                cr.pop("ms", None)
            run.emit("stage", {"stage": "validate", "status": "start", "sample_id": sid})
            h = dhash(comp["composite"])
            prov = {"prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "models": {"forge": MODELS["image"], "label": MODELS["sam"], "critic": MODELS["spark"]},
                    "source_image": part["path"], "crop_box": list(box)}
            vals = run_validators(comp=comp, defect_mask_full=fmask, part_mask=pmask, crop_area=cs * cs, sam_iou=sam_iou,
                                  defect_type=d["defect_type"], critic=cr, dhash_val=h,
                                  accepted_hashes=list(self_hashes(run)), provenance=prov)
            area = int(fmask.sum())
            sample.update({"bbox": bbox, "area_px": area, "sam_iou": sam_iou, "critic": cr, "validators": vals,
                           "size_mm": sev.equiv_diameter_mm(area, part_w_px, tax.get("part_width_mm", 0)),
                           "cost_usd": round(cost, 4), "ms": round((time.time() - t0) * 1000)})
            ok = is_accepted(vals)
            if ok:
                full.save(sd / f"{sid}_composite.png")
                _save_jpg(full, sd / f"{sid}_composite.jpg")
                Image.fromarray((fmask * 255).astype(np.uint8)).save(sd / f"{sid}_mask.png")
                _save_jpg(overlay(np.array(full), fmask), sd / f"{sid}_overlay.jpg")
                (sd / f"{sid}_provenance.json").write_text(json.dumps({**prov, "validators": vals, "critic": cr,
                                                                      "sam_iou": sam_iou, "cost_usd": cost, "attempt": attempt}, indent=1))
                sample.update({"status": "accepted", "composite_url": run.url(sd / f"{sid}_composite.jpg"),
                               "mask_url": run.url(sd / f"{sid}_mask.png"), "overlay_url": run.url(sd / f"{sid}_overlay.jpg")})
                with run.lock:
                    run.accepted_hashes.append(h)
                run.emit("sample", dict(sample))
                return
            if attempt < 3:
                if cr and cr.get("revised_prompt"):
                    prompt = forge_prompt(tax["part_name"], d["description"]) + " " + cr["revised_prompt"]
                run.emit("sample", {**sample, "status": "forging"})
        sample["status"] = "rejected"
        run.emit("sample", dict(sample))

    # ------------------------------------------------------------------ stress test

    def stress(self, rid: str) -> None:
        run = self.get(rid)
        if run is None:
            raise KeyError(rid)
        with run.lock:
            if run.data["status"] == "running":
                raise RuntimeError("run is busy")
            run.stress_from = len(run.events)
            run.data["status"] = "running"
        threading.Thread(target=self._stress_and_finish, args=(run,), daemon=True).start()

    def _stress_and_finish(self, run: Run) -> None:
        try:
            self._stress(run)
        except Exception as e:
            traceback.print_exc()
            run.emit("error", {"message": str(e)[:300]})
            run.data["status"] = "completed"     # the forged samples are still valid
            run.save()

    def stress_point(self, run: Run, s: dict, kind: str, level: float, *, save: bool = True, cache_key: str | None = None) -> dict:
        """Render one severity variant and inspect it. 'detected' needs the inspector's box to overlap the defect;
        'flagged' is any defect claim, including one in the wrong place."""
        types = [d["defect_type"] for d in run.data["taxonomy"]["defects"]]
        sd = run.dir / "samples"
        prov = json.loads((sd / f"{s['id']}_provenance.json").read_text())
        x0, y0, x1, y1 = prov["crop_box"]
        full = Image.open(sd / f"{s['id']}_composite.png").convert("RGB")
        fmask = np.array(Image.open(sd / f"{s['id']}_mask.png")) > 0
        comp_crop = np.array(full.crop((x0, y0, x1, y1)))
        base = load_image(parts_mod.all_parts()[s["part_id"]]["path"])
        orig = np.array(base.crop((x0, y0, x1, y1)))     # exact (lossless) original crop
        vcrop, vmask = sev.variant(orig, comp_crop, fmask[y0:y1, x0:x1], kind, level)
        vimg = base.copy()
        vimg.paste(Image.fromarray(vcrop), (x0, y0))
        vfull = np.zeros(fmask.shape, bool)
        vfull[y0:y1, x0:x1] = vmask
        url = ""
        if save:
            p = run.dir / "severity" / f"{s['id']}_{kind}_{level}.jpg"
            _save_jpg(vimg, p, 92)
            url = run.url(p)
        res = inspect(vimg, run.data["spec_text"], types, run_id=run.id, with_mask=False, cache_key=cache_key or f"stress-{run.id}")
        size_mm = s["size_mm"] * level if (s["size_mm"] and kind == "size") else s["size_mm"]
        flagged = bool(res["defect"])
        return {"sample_id": s["id"], "defect_type": s["defect_type"], "kind": kind, "level": level, "url": url,
                "size_mm": round(size_mm, 2) if size_mm else None, "flagged": flagged,
                "detected": flagged and sev.box_hits(res["box_px"], vfull), "box_px": res["box_px"],
                "pred_type": res["type"], "confidence": res["confidence"]}

    def control_point(self, run: Run, pid: str, *, cache_key: str | None = None) -> dict:
        """Inspect a part with no forged defect: the false-alarm baseline for the severity ladder."""
        types = [d["defect_type"] for d in run.data["taxonomy"]["defects"]]
        base = load_image(parts_mod.all_parts()[pid]["path"])
        res = inspect(base, run.data["spec_text"], types, run_id=run.id, with_mask=False, cache_key=cache_key or f"stress-{run.id}")
        return {"part_id": pid, "flagged": bool(res["defect"]), "pred_type": res["type"], "box_px": res["box_px"]}

    def _stress(self, run: Run) -> None:
        acc = [s for s in run.data["samples"] if s["status"] == "accepted"]
        run.data["severity"] = []
        run.emit("stage", {"stage": "stress", "status": "start", "detail": f"{len(acc)} samples x {len(sev.LEVELS)} levels"})
        jobs = [(s, k, lv) for s in acc for k, lv in sev.LEVELS]

        def safe(fn):
            try:
                return fn()
            except ledger.BudgetExceeded:
                raise
            except Exception:
                traceback.print_exc()
                return None

        def one(job):
            pt = safe(lambda: self.stress_point(run, *job))
            if pt is not None:
                run.emit("severity", pt)
            return pt

        with ThreadPoolExecutor(8) as ex:
            pts = [p for p in ex.map(one, jobs) if p is not None]
            parts = sorted({s["part_id"] for s in acc})
            ctrl = [c for c in ex.map(lambda pid: safe(lambda: self.control_point(run, pid)), parts) if c is not None]
        run.emit("controls", {"n": len(ctrl), "flagged": sum(c["flagged"] for c in ctrl)})
        cv = sev.curves(pts)
        run.emit("curves", {"curves": cv})
        run.emit("stage", {"stage": "stress", "status": "done"})
        run.emit("stress_completed", {"curves": cv})

    # ------------------------------------------------------------------ demo replay

    def replay(self) -> str:
        src = FIXTURES / "demo_run"
        rec = json.loads((src / "run.json").read_text())
        events = [json.loads(x) for x in (src / "events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        rid = "demo-" + uuid.uuid4().hex[:6]
        data = {**rec, "id": rid, "created": time.time(), "status": "running", "samples": [], "severity": [], "curves": [],
                "controls": None, "summary": None, "demo": True}
        run = Run(rid, data, demo=True)
        self.runs[rid] = run

        def play():
            t_prev = events[0]["t"] if events else 0
            for ev in events:
                time.sleep(min(2.0, max(0.0, (ev["t"] - t_prev) / 4)))
                t_prev = ev["t"]
                d = ev["data"]
                if isinstance(d, dict) and "run_id" in d and ev["event"] != "call":
                    d = {**d, "run_id": rid}
                if ev["event"] == "call":
                    d = {**d, "run_id": rid, "status": "replay"}
                run.emit(ev["event"], d)

        threading.Thread(target=play, daemon=True).start()
        return rid


def self_hashes(run: Run) -> list[int]:
    with run.lock:
        return list(run.accepted_hashes)


manager = Manager()
