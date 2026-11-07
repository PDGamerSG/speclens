"""Good-part photos: built-in samples (fixtures/parts, plus local MVTec train/good if downloaded) and uploads."""
from __future__ import annotations

import hashlib
import io
import json
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from .config import DATA, FIXTURES, VAR
from .forge.locate import load_image, part_mask

PARTS = VAR / "parts"
INDEX = PARTS / "index.json"
_lock = threading.Lock()
_mask_cache: dict[str, np.ndarray] = {}


def _url(path: Path) -> str:
    path = path.resolve()
    for root, prefix in ((FIXTURES.resolve(), "/files/fixtures"), ((DATA / "mvtec").resolve(), "/files/mvtec"), (VAR.resolve(), "/files")):
        try:
            return f"{prefix}/{path.relative_to(root).as_posix()}"
        except ValueError:
            continue
    raise ValueError(path)


def _load_index() -> dict:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def _save_index(idx: dict) -> None:
    INDEX.write_text(json.dumps(idx, indent=1))


def _samples() -> dict:
    out = {}
    for p in sorted((FIXTURES / "parts").glob("*.jpg")):
        out[f"sample-{p.stem}"] = {"id": f"sample-{p.stem}", "name": p.stem.replace("_", " "), "path": str(p), "source": "sample"}
    mv = DATA / "mvtec" / "hazelnut" / "train" / "good"
    for p in sorted(mv.glob("*.png"))[:16]:
        out[f"mvtec-hazelnut-{p.stem}"] = {"id": f"mvtec-hazelnut-{p.stem}", "name": f"MVTec hazelnut {p.stem} (local)",
                                           "path": str(p), "source": "sample"}
    return out


def all_parts() -> dict:
    return {**_samples(), **_load_index()}


def mask_path(pid: str) -> Path:
    return PARTS / f"{pid}_mask.png"


def get_mask(pid: str, run_id: str | None = None) -> np.ndarray:
    if pid in _mask_cache:
        return _mask_cache[pid]
    mp = mask_path(pid)
    if mp.exists():
        m = np.array(Image.open(mp)) > 0
    else:
        img = load_image(all_parts()[pid]["path"])
        m, _ = part_mask(img, run_id=run_id)
        Image.fromarray((m * 255).astype(np.uint8)).save(mp)
    _mask_cache[pid] = m
    return m


def _web_copy(pid: str, path: Path) -> Path:
    """Large PNG sources get a cached JPEG for the UI; forging still reads the lossless original."""
    if path.suffix.lower() != ".png":
        return path
    web = PARTS / "web" / f"{pid}.jpg"
    if not web.exists():
        web.parent.mkdir(exist_ok=True)
        load_image(path).save(web, "JPEG", quality=88)
    return web


def describe(pid: str) -> dict:
    p = all_parts()[pid]
    src = Path(p["path"])
    with Image.open(src) as im:
        w, h = im.size
    if max(w, h) > 1280:
        s = 1280 / max(w, h)
        w, h = int(w * s), int(h * s)
    mp = mask_path(pid)
    return {"id": pid, "name": p["name"], "url": _url(_web_copy(pid, src)), "mask_url": _url(mp) if mp.exists() else None,
            "width": w, "height": h, "source": p["source"]}


def list_parts() -> list[dict]:
    return [describe(pid) for pid in all_parts()]


def add_upload(data: bytes, filename: str) -> dict:
    img = load_image(io.BytesIO(data))
    h = hashlib.sha256(data).hexdigest()[:12]
    pid = f"upload-{h}"
    path = PARTS / f"{pid}.jpg"
    img.save(path, "JPEG", quality=95)
    with _lock:
        idx = _load_index()
        idx[pid] = {"id": pid, "name": Path(filename).stem[:40] or pid, "path": str(path), "source": "upload"}
        _save_index(idx)
    get_mask(pid)
    return describe(pid)


def url_for(path: Path) -> str:
    return _url(path)
