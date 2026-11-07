# Serve the API and built interface on http://localhost:8770.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$specLensPort = if ($env:SPECLENS_PORT) { $env:SPECLENS_PORT } else { "8770" }
& .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $specLensPort
