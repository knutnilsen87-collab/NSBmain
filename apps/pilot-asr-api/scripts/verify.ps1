$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$PyVenv = Join-Path $RepoRoot ".venv-pilot-asr-py311\Scripts\python.exe"
if (-not (Test-Path $PyVenv)) {
    throw "Fant ikke venv runtime: $PyVenv. Run: py -3.11 -m venv .venv-pilot-asr-py311; then pip install -r requirements.dev.txt"
}

Write-Output "== dev requirements =="
& $PyVenv -m pip install -r (Join-Path $RepoRoot "requirements.dev.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.dev.txt failed" }

Write-Output "== ruff =="
& $PyVenv -m ruff check app tests
if ($LASTEXITCODE -ne 0) { throw "ruff failed" }

Write-Output "== pytest =="
& $PyVenv -m pytest -v
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Output "== TestClient smoke =="
$env:PYTHONPATH = $RepoRoot
$smoke = @"
import os
os.environ.setdefault('ASR_BACKEND', 'mock')
os.environ.setdefault('ASR_MODEL_NAME', 'mock-small')
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
endpoints = ['/health', '/version', '/v1/health', '/v1/readiness', '/v1/models', '/openapi.json']
ok = True
for ep in endpoints:
    r = client.get(ep)
    print(f'{ep} -> {r.status_code}')
    if r.status_code != 200:
        ok = False
if not ok:
    raise SystemExit(1)
print('ALL_200_OK')
"@
& $PyVenv -c $smoke
if ($LASTEXITCODE -ne 0) { throw "smoke test failed" }

Write-Output ""
Write-Output "All verification checks passed."
