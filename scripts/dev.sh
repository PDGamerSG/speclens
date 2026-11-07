#!/usr/bin/env bash
# Serve the API and the built frontend on http://localhost:8765 (add --dev for Vite hot reload on :5173).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--dev" ]; then
  (cd frontend && npm run dev) &
fi
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
