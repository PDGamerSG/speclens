"""Download the MVTec AD hazelnut category (or a subset) from the Hugging Face mirror `foersben/mvtec-ad`.

MVTec AD is CC BY-NC-SA 4.0 (non-commercial). This script fetches it for local evaluation only; the images are
never committed (see .gitignore). Original source: https://www.mvtec.com/company/research/datasets/mvtec-ad

usage:
  python eval/download_mvtec.py                 # full hazelnut test split + ground truth + 40 train/good
  python eval/download_mvtec.py --train 391     # all train/good images
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "foersben/mvtec-ad"
API = f"https://huggingface.co/api/datasets/{REPO}/tree/main"
RAW = f"https://huggingface.co/datasets/{REPO}/resolve/main"
ROOT = Path(__file__).resolve().parents[1]


def list_files(category: str) -> list[str]:
    with urllib.request.urlopen(f"{API}/{category}?recursive=true", timeout=60) as r:
        return [x["path"] for x in json.load(r) if x["type"] == "file" and x["path"].endswith(".png")]


def fetch(path: str, dest_root: Path) -> str:
    dest = dest_root / path.split("/", 1)[1]
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(f"{RAW}/{path}", tmp)
    tmp.replace(dest)
    return "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="hazelnut")
    ap.add_argument("--train", type=int, default=40, help="number of train/good images to fetch")
    ap.add_argument("--out", default=str(ROOT / "data" / "mvtec"))
    a = ap.parse_args()
    dest_root = Path(a.out) / a.category
    files = list_files(a.category)
    train = sorted(f for f in files if "/train/good/" in f)[: a.train]
    want = [f for f in files if "/test/" in f or "/ground_truth/" in f] + train
    print(f"fetching {len(want)} files into {dest_root}")
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda p: fetch(p, dest_root), want))
    print(f"done: {res.count('ok')} downloaded, {res.count('skip')} already present")
    lic = dest_root.parent / "LICENSE_MVTEC.txt"
    if not lic.exists():
        urllib.request.urlretrieve(f"{RAW}/license.txt", lic)


if __name__ == "__main__":
    sys.exit(main())
