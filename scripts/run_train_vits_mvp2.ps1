param(
  [int]$epochs = 1,
  [int]$batch_size = 16,
  [int]$num_workers = 0,
  [int]$save_every = 50,
  [int]$limit_items = 2000,
  [switch]$resume
)

$ProjectRoot = "F:\NorwegianSpeechBase"
$TtsRoot     = Join-Path $ProjectRoot "tts_vits"
$VenvPy      = Join-Path $ProjectRoot "envs\tts_vits_env\Scripts\python.exe"

$DatasetRoot = Join-Path $TtsRoot "data\consent_voice\dataset"
$MetaCsv     = Join-Path $DatasetRoot "metadata.csv"
$TrainPy     = Join-Path $TtsRoot "src\train_vits.py"
$ModelsRoot  = Join-Path $TtsRoot "models"

$LogsDir     = Join-Path $ProjectRoot "logs_v2\tx"
if (!(Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }
if (!(Test-Path $ModelsRoot)) { New-Item -ItemType Directory -Path $ModelsRoot -Force | Out-Null }

$ts     = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $ModelsRoot ("mvp2_run_" + $ts)
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null

$logTxt = Join-Path $LogsDir ("tx_train_vits_mvp2_" + $ts + ".txt")
"[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] RUN_START RunDir=$RunDir" | Add-Content -Path $logTxt

function Require-Path([string]$p,[string]$name){
  if (!(Test-Path -LiteralPath $p)) { throw ("Mangler {0}: {1}" -f $name, $p)}
}

Require-Path $VenvPy "VenvPy"
Require-Path $TtsRoot "TtsRoot"
Require-Path $DatasetRoot "DatasetRoot"
Require-Path $MetaCsv "MetaCsv"
Require-Path $TrainPy "TrainPy"

Write-Host ""
Write-Host ">>> VITS MVP2 training runner" -ForegroundColor Cyan
Write-Host ">>> RunDir: $RunDir" -ForegroundColor Green
Write-Host ">>> Logg:   $logTxt" -ForegroundColor Green
Write-Host ">>> CWD:    $TtsRoot" -ForegroundColor Green
Write-Host ""

# Optional: auto-resume if checkpoint exists in a *previous* run dir you pass manually
# For now: only use -resume if user passes it; keeps behavior predictable.
$extra = @()
if ($resume) { $extra += "--resume" }

# Build python args
$pyArgs = @(
  "-u", $TrainPy,
  "--dataset_root", $DatasetRoot,
  "--metadata_csv", $MetaCsv,
  "--out_dir", $RunDir,
  "--epochs", "$epochs",
  "--batch_size", "$batch_size",
  "--num_workers", "$num_workers",
  "--save_every", "$save_every",
  "--limit_items", "$limit_items"
) + $extra

# Start process
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VenvPy
$psi.WorkingDirectory = $TtsRoot
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow  = $true

$psi.Arguments = ($pyArgs | ForEach-Object {
  if ($_ -match '\s') { '"' + ($_ -replace '"','\"') + '"' } else { $_ }
}) -join " "

"[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] CMD: $($psi.FileName) $($psi.Arguments)" | Add-Content -Path $logTxt
Write-Host "RUN: (cwd=$($psi.WorkingDirectory)) $($psi.FileName) $($psi.Arguments)" -ForegroundColor Gray

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()

# Progress + ETA
$activity   = "VITS MVP2 training"
$pct        = 0.0
$start      = Get-Date
$lastOut    = Get-Date
$spinner    = "/-\|"
$spinIdx    = 0

function Update-Progress([double]$p,[string]$status){
  if ($p -lt 0) { $p = 0 }
  if ($p -gt 100) { $p = 100 }
  Write-Progress -Activity $activity -PercentComplete $p -Status $status
}

function Format-ETA([datetime]$startTime,[double]$percent){
  if ($percent -le 0.1) { return "" }
  $elapsed = (Get-Date) - $startTime
  $totalSec = $elapsed.TotalSeconds / ($percent / 100.0)
  $remainSec = [Math]::Max(0, $totalSec - $elapsed.TotalSeconds)

  $mins = [Math]::Round($remainSec / 60.0, 1)
  $hrs  = [Math]::Round($remainSec / 3600.0, 2)

  return ("ETA ~ {0} min (~{1} t)" -f $mins, $hrs)
}

while (-not $proc.HasExited) {
  $had = $false

  while (-not $proc.StandardOutput.EndOfStream) {
    $line = $proc.StandardOutput.ReadLine()
    if ($null -eq $line) { break }
    $had = $true
    $lastOut = Get-Date

    Add-Content -Path $logTxt -Value $line
    Write-Host $line

    # Accept either:
    #   PROGRESS:24.50
    # or lines containing "(24.50% total)"
    if ($line -match "^PROGRESS:(\d+(\.\d+)?)") {
      $pct = [double]$matches[1]
    } elseif ($line -match "\((\d+(\.\d+)?)%\s+total\)") {
      $pct = [double]$matches[1]
    }

    $eta = Format-ETA $start $pct
    $status = ("{0:N2}%  {1}" -f $pct, $eta).Trim()
    Update-Progress $pct $status
  }

  while (-not $proc.StandardError.EndOfStream) {
    $err = $proc.StandardError.ReadLine()
    if ($null -eq $err) { break }
    $had = $true
    $lastOut = Get-Date

    Add-Content -Path $logTxt -Value ("[PYTHON ERR] " + $err)
    Write-Host ("[PYTHON ERR] " + $err) -ForegroundColor Red
  }

  if (-not $had) {
    $spinIdx = ($spinIdx + 1) % $spinner.Length
    $spin = $spinner[$spinIdx]
    $elapsed = (Get-Date) - $start
    $silent  = (Get-Date) - $lastOut
    $eta = Format-ETA $start $pct
    $status = ("Kjører... {0} | kjørt {1:hh\:mm\:ss} | ingen output {2:N0}s | {3:N2}% {4}" -f $spin, $elapsed, $silent.TotalSeconds, $pct, $eta).Trim()
    Update-Progress $pct $status
    Start-Sleep -Milliseconds 200
  }
}

# Drain remainder
while (-not $proc.StandardOutput.EndOfStream) {
  $line = $proc.StandardOutput.ReadLine()
  if ($line) { Add-Content -Path $logTxt -Value $line; Write-Host $line }
}
while (-not $proc.StandardError.EndOfStream) {
  $err = $proc.StandardError.ReadLine()
  if ($err) { Add-Content -Path $logTxt -Value ("[PYTHON ERR] " + $err); Write-Host ("[PYTHON ERR] " + $err) -ForegroundColor Red }
}

Write-Progress -Activity $activity -Completed -Status "Ferdig"

"[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] RUN_END ExitCode=$($proc.ExitCode) RunDir=$RunDir" | Add-Content -Path $logTxt

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " VITS MVP2 runner ferdig" -ForegroundColor Green
Write-Host " ExitCode: $($proc.ExitCode)" -ForegroundColor Green
Write-Host " RunDir:   $RunDir" -ForegroundColor Green
Write-Host " Logg:     $logTxt" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

if ($proc.ExitCode -ne 0) {
  throw "Trening feilet (ExitCode=$($proc.ExitCode)). Se logg: $logTxt"
}

