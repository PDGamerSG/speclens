# Serve the API and the built frontend on http://localhost:8765 (pass -Dev for Vite hot reload on :5173).
param([switch]$Dev)
Set-Location (Join-Path $PSScriptRoot "..")
if ($Dev) { Start-Process -NoNewWindow -WorkingDirectory frontend npm -ArgumentList "run", "dev" }
& .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
