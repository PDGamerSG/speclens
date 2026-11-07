#!/usr/bin/env bash
# One-time setup on macOS / Linux: Python venv + backend deps, frontend deps and build, .env from the example.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
"$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r backend/requirements.txt
(cd frontend && npm ci --no-audit --no-fund && npm run build)
[ -f .env ] || cp .env.example .env
echo
echo "Setup done. Put your Meta Model API key in .env (MODEL_API_KEY=...), or leave it empty for DEMO_MODE replay."
echo "Then run: ./scripts/dev.sh   and open http://localhost:8765"
