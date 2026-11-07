#!/usr/bin/env bash
# Install SpecLens and build its web interface on macOS or Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  if [ -n "${SPECLENS_PYTHON:-}" ]; then
    "$SPECLENS_PYTHON" -m venv .venv
  elif command -v uv >/dev/null 2>&1; then
    uv venv --python 3.13 .venv
  elif command -v python3.13 >/dev/null 2>&1; then
    python3.13 -m venv .venv
  else
    python3 -c 'import sys; assert sys.version_info >= (3, 13), "Install Python 3.13+ or uv, then run setup again."'
    python3 -m venv .venv
  fi
fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3, 13), "SpecLens requires Python 3.13+. Recreate .venv with a supported Python."'
if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -r backend/requirements.txt
else
  .venv/bin/python -m pip install -r backend/requirements.txt
fi
(cd frontend && npm ci --no-audit --no-fund && npm run build)
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
printf '\nSpecLens is installed. Add the vision and Hindsight credentials to .env.\n'
printf 'Start: ./scripts/dev.sh\nOpen:  http://localhost:8770\n'
