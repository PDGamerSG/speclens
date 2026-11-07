"""Paths, environment and prices. Everything runtime-writable lives under var/ (gitignored)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get("MODEL_API_BASE_URL", "https://api.meta.ai/v1")
API_KEY = os.environ.get("MODEL_API_KEY", "")
DEMO_MODE = os.environ.get("DEMO_MODE", "0") == "1" or not API_KEY
# Hard stop for this app's own Meta spend (ledger total). The app refuses new calls beyond it.
BUDGET_USD = float(os.environ.get("BUDGET_USD", "100"))

VAR = Path(os.environ.get("SPECLENS_VAR", ROOT / "var"))
FIXTURES = ROOT / "fixtures"
DATA = ROOT / "data"
RESULTS = ROOT / "docs" / "results"
for p in (VAR, VAR / "parts", VAR / "runs", VAR / "inspections"):
    p.mkdir(parents=True, exist_ok=True)

MODELS = {
    "spark": "muse-spark-1.3",
    "image": "muse-image-1.0",
    "sam": "sam-3.1",
}

# USD, from dev.meta.ai/docs/pricing-rate-limits
PRICE = {
    "muse-spark-1.3": {"in": 1.25e-6, "cached": 0.15e-6, "out": 4.25e-6},
    "muse-wonder-1.0": {"in": 4.0e-6, "cached": 0.4e-6, "out": 20.0e-6},
    "muse-image-1.0": {"image": 0.01},
    "sam-3.1": {"image": 0.0025},
}

IMAGE_RPS = 2.0          # Muse Image is limited to 150 RPM per team
FORGE_WORKERS = 4
MAX_SIDE = 1280          # SAM wants <= 1280 px; phone photos are downscaled to this
CROP = 512
