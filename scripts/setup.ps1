# Install SpecLens on Windows with Python 3.13+ and Node.js 22.12+.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .venv\Scripts\python.exe)) {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Install Python 3.13, then run setup again." }
}
& .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependencies could not be installed." }
Push-Location frontend
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally { Pop-Location }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Add the vision and Hindsight credentials to .env."
Write-Host "Run scripts\dev.ps1 and open http://localhost:8770."
