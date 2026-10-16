param(
    [string]$Backend = "faster-whisper",
    [string]$ModelName = "medium",
    [string]$ModelDevice = "cpu",
    [string]$ModelComputeType = "int8",
    [int]$Port = 8091
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$env:ASR_BACKEND = $Backend
$env:ASR_MODEL_NAME = $ModelName
$env:ASR_MODEL_DEVICE = $ModelDevice
$env:ASR_MODEL_COMPUTE_TYPE = $ModelComputeType
$env:ASR_PORT = [string]$Port

$PyVenv = Join-Path $RepoRoot ".venv-pilot-asr-py311\Scripts\python.exe"
if (-not (Test-Path $PyVenv)) {
    throw "Fant ikke venv runtime: $PyVenv"
}

& $PyVenv -m uvicorn app.main:app --host 127.0.0.1 --port $Port
