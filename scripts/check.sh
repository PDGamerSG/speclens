#!/usr/bin/env bash
# Reproducible offline application checks; no live provider calls.
set -euo pipefail
cd "$(dirname "$0")/.."
export MODEL_API_KEY='' HINDSIGHT_API_KEY='' HINDSIGHT_BASE_URL='' DEMO_MODE=1
npm --prefix frontend run build
npm --prefix frontend run lint
.venv/bin/python -m pytest -q --tb=short
npm --prefix frontend run test:e2e
