# One-time setup on Windows: Python venv + backend deps, frontend deps and build, .env from the example.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Python 3.11+ is required (numpy 2.x). Try the py launcher for 3.13 / 3.12 / 3.11, then plain python.
$made = $false
foreach ($v in @("3.13", "3.12", "3.11")) {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { & py "-$v" -m venv .venv; $made = $true; break }
}
if (-not $made) {
    & python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required (install from python.org, then re-run)." }
    & python -m venv .venv
}
& .venv\Scripts\python.exe -m pip install -q --upgrade pip
& .venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Push-Location frontend
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm ci failed" }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "frontend build failed" }
Pop-Location
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host ""
Write-Host "Setup done. Put your Meta Model API key in .env (MODEL_API_KEY=...), or leave it empty for DEMO_MODE replay."
Write-Host "Then run: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1   and open http://localhost:8765"
