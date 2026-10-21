<#
.SYNOPSIS
  Starter nsb-engine lokalt (http://127.0.0.1:8765) med NB-Whisper distil-turbo på GPU.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$Model = 'nb-whisper-large-distil-turbo-beta',
    [string]$Device = 'cuda',
    [int]$Port = 8765,
    # Nettsider som får koble seg til (EVIDA lokalt). Paringskoden vises i vinduet.
    [string[]]$AllowOrigin = @('http://127.0.0.1:5173', 'http://localhost:5173'),
    # Ikke åpne testsiden (når motoren startes av Verity eller EVIDA).
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location $Root
$Py = Join-Path $Root '.venv-bench/Scripts/python.exe'
if (-not (Test-Path $Py)) { Write-Host 'Fant ikke .venv-bench. Kjør scripts\RUN_BENCHMARK.cmd først.'; exit 1 }
& $Py -m pip install --quiet numpy fastapi uvicorn websockets cryptography
$site = (& $Py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
$sep = [System.IO.Path]::PathSeparator
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub
    if (Test-Path $p) { $env:PATH = "$p$sep$env:PATH" }
}
$env:PYTHONPATH = $Root
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$registry = Get-Content (Join-Path $Root 'eval/results/models.json') -Raw | ConvertFrom-Json
$path = $registry.$Model.path
if (-not $path -or -not (Test-Path (Join-Path $Root $path))) { Write-Host "Fant ikke modellen $Model. Kjør scripts\RUN_BENCHMARK.cmd først."; exit 1 }
$ct = if ($Device -eq 'cpu') { 'int8' } else { 'float16' }
$originArgs = @(); foreach ($o in ($AllowOrigin | ForEach-Object { $_ -split ',' })) { if ($o.Trim()) { $originArgs += @('--allow-origin', $o.Trim()) } }
& $Py -m nsb_engine.server --model $path --label $Model --device $Device --compute-type $ct --port $Port @(if ($NoBrowser) { @() } else { @('--open') }) @originArgs @args
