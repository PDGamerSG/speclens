#!/usr/bin/env bash
# Serve the complete app, or use --dev for API reload and the Vite dev server.
set -euo pipefail
cd "$(dirname "$0")/.."
speclens_port="${SPECLENS_PORT:-8770}"
if [ ! -x .venv/bin/python ]; then
  printf 'Run ./scripts/setup.sh first.\n' >&2
  exit 1
fi
if [ "${1:-}" = "--dev" ]; then
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$speclens_port" --reload &
  speclens_backend_pid=$!
  (cd frontend && VITE_API_TARGET="http://127.0.0.1:$speclens_port" npm run dev -- --host 127.0.0.1) &
  speclens_frontend_pid=$!
  trap 'kill "$speclens_backend_pid" "$speclens_frontend_pid" 2>/dev/null || true' EXIT INT TERM
  wait "$speclens_backend_pid" "$speclens_frontend_pid"
else
  if [ ! -f frontend/dist/index.html ]; then
    printf 'Build the interface first: cd frontend && npm run build\n' >&2
    exit 1
  fi
  exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$speclens_port"
fi
