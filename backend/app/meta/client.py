"""Meta Model API calls used by SpecLens: Muse Spark (strict JSON), Muse Image (edits, generations), SAM 3.1.

Requests follow Meta's documented compatible API shapes. Every call goes through the ledger.
"""
from __future__ import annotations

import base64
import io
import json
import random
import threading
import time

import httpx
import numpy as np
from openai import OpenAI
from PIL import Image

import meta_sam_parser as msp

from ..config import API_KEY, BASE_URL, IMAGE_RPS, MODELS, PRICE
from . import ledger

_spark = OpenAI(base_url=BASE_URL, api_key=API_KEY or "demo", max_retries=4, timeout=180)
_sam = OpenAI(base_url=BASE_URL, api_key=API_KEY or "demo", max_retries=2, timeout=90)
RETRYABLE = {429, 500, 502, 503, 504}
TRANSIENT = {404, 429}   # the Model API intermittently answers 404 "model not found" for valid models; retry it


class MetaAPIError(RuntimeError):
    def __init__(self, status, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


def to_jpeg(img: Image.Image, quality: int = 92, max_side: int | None = None) -> bytes:
    im = img.convert("RGB")
    if max_side and max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


# ------------------------------------------------------------------ Muse Spark

def spark_json(messages: list, schema: dict, name: str, *, effort: str = "low", max_tokens: int = 4000,
               cache_key: str | None = None, run_id: str | None = None, model: str | None = None) -> dict:
    """Chat Completions with a strict flat JSON schema. Returns {data, ms, cost_usd, usage}."""
    model = model or MODELS["spark"]
    ledger.check_budget()
    kw = {"extra_body": {"prompt_cache_key": cache_key}} if cache_key else {}
    for attempt in range(3):
        t = time.time()
        try:
            r = _spark.chat.completions.create(
                model=model, reasoning_effort=effort, max_tokens=max_tokens, messages=messages,
                response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}, **kw)
            break
        except Exception as e:
            code = getattr(e, "status_code", "error")
            ledger.record(model, name, (time.time() - t) * 1000, code, 0.0, run_id, err=str(e)[:200])
            if code not in TRANSIENT or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    ms = (time.time() - t) * 1000
    u = r.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    cost = ledger.spark_cost(model, u.prompt_tokens, u.completion_tokens, cached)
    ledger.record(model, name, ms, 200, cost, run_id, cached_tokens=cached,
                  prompt_tokens=u.prompt_tokens, completion_tokens=u.completion_tokens)
    content = r.choices[0].message.content or ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise MetaAPIError("bad_json", f"{name}: {content[:200]}") from e
    return {"data": data, "ms": ms, "cost_usd": cost, "usage": {"prompt": u.prompt_tokens, "completion": u.completion_tokens, "cached": cached}}


# ------------------------------------------------------------------ Muse Image

_rate_lock = threading.Lock()
_next_slot = [0.0]


def _image_slot() -> None:
    """Simple shared rate limiter: at most IMAGE_RPS image calls start per second across threads."""
    with _rate_lock:
        now = time.time()
        wait = _next_slot[0] - now
        _next_slot[0] = max(now, _next_slot[0]) + 1.0 / IMAGE_RPS
    if wait > 0:
        time.sleep(wait)


def _image_post(path: str, payload: dict, op: str, run_id: str | None) -> dict:
    model = payload["model"]
    for attempt in range(4):
        ledger.check_budget(PRICE[model]["image"])
        _image_slot()
        t = time.time()
        try:
            r = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=240, headers={"Authorization": f"Bearer {API_KEY}"})
        except httpx.HTTPError as e:
            ledger.record(model, op, (time.time() - t) * 1000, "neterr", 0.0, run_id, err=str(e)[:200])
            time.sleep(2 ** attempt + random.random())
            continue
        ms = (time.time() - t) * 1000
        if r.status_code == 200:
            imgs = [base64.b64decode(d["b64_json"]) for d in r.json()["data"]]
            cost = PRICE[model]["image"] * len(imgs)
            ledger.record(model, op, ms, 200, cost, run_id, n=len(imgs))
            return {"images": imgs, "ms": ms, "cost_usd": cost}
        # failed and filtered images are not billed
        ledger.record(model, op, ms, r.status_code, 0.0, run_id, err=r.text[:300])
        if r.status_code not in RETRYABLE:
            raise MetaAPIError(r.status_code, r.text[:400])
        wait = float(r.headers.get("retry-after", 0) or 0)
        time.sleep(max(wait, 2 ** attempt + random.random()))
    raise MetaAPIError("gave_up", f"{op}: retries exhausted")


def image_edit(png: bytes, prompt: str, *, strength: str = "low", tools: bool = False, run_id: str | None = None) -> dict:
    payload = {
        "model": MODELS["image"], "prompt": prompt, "n": 1,
        "images": [{"image_url": data_url(png, "image/png")}],
        # JPEG: 1.3 MB instead of 5.5 MB per response, which stalled on slow links; it's downscaled 3x before compositing
        "output_format": "jpeg", "response_format": "b64_json", "reasoning_strength": strength,
        "tool_enablement": {"enable_image_search": tools, "enable_web_search": tools, "enable_shell": tools},
    }
    return _image_post("/images/edits", payload, "edit", run_id)


def image_generate(prompt: str, *, strength: str = "low", tools: bool = False, size: str = "1024x1024", run_id: str | None = None) -> dict:
    payload = {
        "model": MODELS["image"], "prompt": prompt, "n": 1, "size": size,
        "output_format": "png", "response_format": "b64_json", "reasoning_strength": strength,
        "tool_enablement": {"enable_image_search": tools, "enable_web_search": tools, "enable_shell": tools},
    }
    return _image_post("/images/generations", payload, "generate", run_id)


# ------------------------------------------------------------------ SAM 3.1

def sam_segment(img: Image.Image, *, text: str | None = None, boxes: list | None = None, points: list | None = None,
                run_id: str | None = None, op: str = "segment") -> dict:
    """Segment one image. Exactly one of text / boxes / points. Returns full-frame boolean masks per object."""
    w, h = img.size
    if boxes is not None:
        prompt = msp.build_object_prompt(size=(w, h), objects=[
            msp.PromptObject(id=i + 1, prompts=[msp.FramePrompt(frame=0, box=msp.PromptBox(*[int(v) for v in b]))])
            for i, b in enumerate(boxes)])
    elif points is not None:
        prompt = msp.build_object_prompt(size=(w, h), objects=[
            msp.PromptObject(id=i + 1, prompts=[msp.FramePrompt(frame=0, points=[msp.PromptPoint(int(x), int(y)) for x, y in pts])])
            for i, pts in enumerate(points)])
    else:
        prompt = text
    ledger.check_budget(PRICE["sam-3.1"]["image"])
    t = time.time()
    last_err = None
    for attempt in range(3):
        try:
            r = _sam.responses.create(
                model=MODELS["sam"], store=False,
                metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
                input=[{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url(to_jpeg(img))}]}])
            break
        except Exception as e:  # SDK already retried transport errors; manual passes for 5xx and the API's transient 404s
            last_err = e
            code = getattr(e, "status_code", 500)
            ledger.record(MODELS["sam"], op, (time.time() - t) * 1000, code, 0.0, run_id, err=str(e)[:200])
            if code < 500 and code not in TRANSIENT:
                raise
            time.sleep(1.5 * (attempt + 1))
            t = time.time()
    else:
        raise MetaAPIError("gave_up", str(last_err)[:200])
    ms = (time.time() - t) * 1000
    cost = PRICE["sam-3.1"]["image"]
    raw = r.output_text or ""
    parser = msp.image_segmentation_format().create_parser()
    parser.push(raw)
    result = parser.finish(msp.CompletedOutcome()).result
    objs: dict[str, dict] = {}
    for rec in result.records:
        o = objs.setdefault(str(rec.object_id), {"object_id": str(rec.object_id), "box": None, "mask": None, "confidence": None})
        if rec.kind == "box":
            o["box"] = (rec.left, rec.top, rec.right, rec.bottom)
        elif rec.kind == "mask":
            local = np.frombuffer(msp.decode_mask_to_raster(rec.mask), dtype=np.uint8).reshape(rec.mask.height, rec.mask.width) > 0
            full = np.zeros((h, w), dtype=bool)
            l, tp = rec.bounds.left, rec.bounds.top
            hh, ww = min(local.shape[0], h - tp), min(local.shape[1], w - l)
            full[tp:tp + hh, l:l + ww] = local[:hh, :ww]
            o["mask"] = full if o["mask"] is None else (o["mask"] | full)
        if getattr(rec, "confidence", None) is not None:
            o["confidence"] = rec.confidence
    ledger.record(MODELS["sam"], op, ms, 200, cost, run_id, n=len(objs))
    return {"objects": list(objs.values()), "ms": ms, "cost_usd": cost}
