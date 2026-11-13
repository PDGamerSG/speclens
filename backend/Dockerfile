# API, worker and cron image for Render. Vercel builds and serves the page, so there is no frontend stage here.
# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SPECLENS_VAR=/app/var PYTHONPATH=/app/backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY fixtures/ fixtures/
RUN useradd --uid 10001 --create-home speclens && mkdir -p /app/var && chown -R speclens:speclens /app/var
USER speclens
EXPOSE 8770
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8770\")}/healthz', timeout=4)"
# Render sets PORT. The shell form lets the variable expand; exec keeps Uvicorn as PID 1 for clean shutdowns.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8770} --proxy-headers"]
