"""Thin Meta Model API helpers for the gate tests: Spark JSON, Muse Image edits, SAM 3.1 image masks.

Every call is appended to runs/gate/ledger.jsonl (model, op, ms, status). The key is never printed.
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import time
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

import meta_sam_parser as msp

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BASE = os.environ.get("MODEL_API_BASE_URL", "https://api.meta.ai/v1")
KEY = os.environ["MODEL_API_KEY"]
RUNS = ROOT / "runs" / "gate"
RUNS.mkdir(parents=True, exist_ok=True)
LEDGER = RUNS / "ledger.jsonl"

client = OpenAI(base_url=BASE, api_key=KEY, max_retries=4, timeout=180)
sam_client = OpenAI(base_url=BASE, api_key=KEY, max_retries=2, timeout=60)


def log(model: str, op: str, ms: float, status, **extra) -> None:
    rec = {"t": time.time(), "model": model, "op": op, "ms": round(ms), "status": status, **extra}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def to_bytes(img: Image.Image, fmt: str = "JPEG", quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, fmt, **({"quality": quality} if fmt == "JPEG" else {}))
    return buf.getvalue()


def data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def load_rgb(path: Path, max_side: int | None = None) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max_side and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return img


# ---------------------------------------------------------------- Muse Image

RETRYABLE = {429, 500, 502, 503, 504}


def image_edit(png: bytes, prompt: str, strength: str = "low", tools: bool = False, n: int = 1) -> dict:
    """Raw-JSON /images/edits. Returns {images: [bytes], ms, status, error}."""
    payload = {
        "model": "muse-image-1.0", "prompt": prompt, "n": n,
        "images": [{"image_url": data_url(png, "image/png")}],
        "output_format": "png", "response_format": "b64_json", "reasoning_strength": strength,
        "tool_enablement": {"enable_image_search": tools, "enable_web_search": tools, "enable_shell": tools},
    }
    for attempt in range(4):
        t = time.time()
        try:
            r = httpx.post(f"{BASE}/images/edits", json=payload, timeout=240,
                           headers={"Authorization": f"Bearer {KEY}"})
        except httpx.HTTPError as e:
            log("muse-image-1.0", "edit", (time.time() - t) * 1000, "neterr", err=str(e)[:200])
            time.sleep(2 ** attempt + random.random())
            continue
        ms = (time.time() - t) * 1000
        if r.status_code == 200:
            imgs = [base64.b64decode(d["b64_json"]) for d in r.json()["data"]]
            log("muse-image-1.0", "edit", ms, 200, strength=strength, tools=tools, n=len(imgs))
            return {"images": imgs, "ms": ms, "status": 200, "error": None}
        log("muse-image-1.0", "edit", ms, r.status_code, err=r.text[:300])
        if r.status_code not in RETRYABLE:
            return {"images": [], "ms": ms, "status": r.status_code, "error": r.text[:500]}
        wait = float(r.headers.get("retry-after", 0) or 0)
        time.sleep(max(wait, 2 ** attempt + random.random()))
    return {"images": [], "ms": 0, "status": "gave_up", "error": "retries exhausted"}


# ---------------------------------------------------------------- SAM 3.1

def sam_image(img: Image.Image, text: str | None = None, boxes: list[tuple[int, int, int, int]] | None = None) -> dict:
    """Segment one image with a noun phrase or box prompts. Returns full-frame boolean masks."""
    w, h = img.size
    if boxes is not None:
        prompt = msp.build_object_prompt(size=(w, h), objects=[
            msp.PromptObject(id=i + 1, prompts=[msp.FramePrompt(frame=0, box=msp.PromptBox(*b))])
            for i, b in enumerate(boxes)])
    else:
        prompt = text
    t = time.time()
    r = sam_client.responses.create(
        model="sam-3.1", store=False,
        metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": data_url(to_bytes(img))}]}])
    ms = (time.time() - t) * 1000
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
            local = np.frombuffer(msp.decode_mask_to_raster(rec.mask), dtype=np.uint8)
            local = local.reshape(rec.mask.height, rec.mask.width) > 0
            full = np.zeros((h, w), dtype=bool)
            l, tp = rec.bounds.left, rec.bounds.top
            hh, ww = min(local.shape[0], h - tp), min(local.shape[1], w - l)
            full[tp:tp + hh, l:l + ww] = local[:hh, :ww]
            o["mask"] = full
        if getattr(rec, "confidence", None) is not None:
            o["confidence"] = rec.confidence
    log("sam-3.1", "image", ms, 200, prompt=("boxes" if boxes else text), n=len(objs))
    return {"objects": list(objs.values()), "ms": ms, "raw_len": len(raw)}


# ---------------------------------------------------------------- Spark

def spark_json(messages: list, schema: dict, name: str, effort: str = "low",
               max_tokens: int = 4000, cache_key: str | None = None, model: str = "muse-spark-1.3") -> dict:
    t = time.time()
    kw = {"extra_body": {"prompt_cache_key": cache_key}} if cache_key else {}
    r = client.chat.completions.create(
        model=model, reasoning_effort=effort, max_tokens=max_tokens, messages=messages,
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}, **kw)
    ms = (time.time() - t) * 1000
    u = r.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    log(model, name, ms, 200, prompt_tokens=u.prompt_tokens, completion_tokens=u.completion_tokens, cached=cached)
    content = r.choices[0].message.content
    return {"data": json.loads(content), "ms": ms, "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens, "cached": cached}
