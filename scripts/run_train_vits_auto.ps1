#requires -Version 7.0
[CmdletBinding()]
param(
  [string]$RepoRoot   = "F:\NorwegianSpeechBase",
  [string]$PythonExe  = "F:\NorwegianSpeechBase\envs\tts_vits_env\Scripts\python.exe",
  [string]$DatasetDir = "F:\NorwegianSpeechBase\tts_vits\data\consent_voice\dataset",
  [int]$MaxSteps  = 2000,
  [int]$SaveEvery = 500,
  [int]$LogEvery  = 50,
  [int]$NumWorkers = 4,
  [string]$TrainEntrypoint = "",
  [string]$ConfigPath = "",
  [string]$Tag = "vits_auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Import-Module (Join-Path $RepoRoot "scripts\FBL.Harness.psm1") -Force
$ctx = Start-FBLRun -RepoRoot $RepoRoot -TaskName "Train VITS Auto Runner"

function Assert-Path([string]$p,[string]$label){ if(!(Test-Path $p)){ throw "Fant ikke ${label}: $p" } }

Invoke-FBLStep -Ctx $ctx -Name "Verify paths" -Block {
  Assert-Path $RepoRoot "RepoRoot"
  Assert-Path $PythonExe "PythonExe"
  Assert-Path $DatasetDir "DatasetDir"
  Assert-Path (Join-Path $DatasetDir "metadata.csv") "metadata.csv"
  Assert-Path (Join-Path $DatasetDir "wavs") "wavs dir"
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$runRoot = Join-Path $RepoRoot ("runs\{0}_{1}" -f $ts,$Tag)
$logDir  = Join-Path $runRoot "logs"
$ckptDir = Join-Path $runRoot "checkpoints"
New-Item -ItemType Directory -Force -Path $logDir,$ckptDir | Out-Null
$logFile = Join-Path $logDir "train.log"

Push-Location $RepoRoot

# Watch only inside runRoot (der vi forventer output)
$script:patterns = @("*.pt","*.pth","*.ckpt","*.safetensors","*.bin","*.onnx")
$script:seen = @{}
$fsw = New-Object System.IO.FileSystemWatcher
$fsw.Path = $runRoot
$fsw.IncludeSubdirectories = $true
$fsw.EnableRaisingEvents = $true
$fsw.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, Size, DirectoryName'

$action = {
  try {
    $p = $Event.SourceEventArgs.FullPath
    $name = [IO.Path]::GetFileName($p)
    foreach($pat in $script:patterns){
      if($name -like $pat){
        $key=$p.ToLowerInvariant(); $now=Get-Date
        if(-not $script:seen.ContainsKey($key) -or ($now-$script:seen[$key]).TotalSeconds -gt 2){
          $script:seen[$key]=$now
          $fi=Get-Item -LiteralPath $p -ErrorAction SilentlyContinue
          $sz= if($fi){$fi.Length}else{0}
          Write-Host ("[CHECKPOINT_ARTIFACT] {0} | {1} | {2} bytes | {3}" -f $Event.SourceEventArgs.ChangeType,$p,$sz,$now) -ForegroundColor Green
        }
        break
      }
    }
  } catch {}
}

$subs=@()
$subs += Register-ObjectEvent -InputObject $fsw -EventName Created -Action $action
$subs += Register-ObjectEvent -InputObject $fsw -EventName Changed -Action $action
$subs += Register-ObjectEvent -InputObject $fsw -EventName Renamed -Action $action

try {
  Invoke-FBLStep -Ctx $ctx -Name "Resolve train entrypoint" -Block {
    if($TrainEntrypoint){
      Assert-Path $TrainEntrypoint "TrainEntrypoint"
      $script:entry=$TrainEntrypoint
      return
    }
    $found = Get-ChildItem -Path $RepoRoot -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Extension -eq ".py" -and $_.Name -match '^train.*\.py$' } |
      Sort-Object FullName | Select-Object -First 1
    if(-not $found){ throw "Fant ingen train*.py under repo. Angi -TrainEntrypoint eksplisitt." }
    $script:entry=$found.FullName
  }

  $meta = Join-Path $DatasetDir "metadata.csv"
  $wavs = Join-Path $DatasetDir "wavs"

  # NOTE: Hvis din train CLI har andre flagg, endrer vi KUN disse.
  $pyArgs = @(
    $script:entry,
    "--dataset_dir",$DatasetDir,
    "--metadata",$meta,
    "--wavs_dir",$wavs,
    "--out_dir",$runRoot,
    "--ckpt_dir",$ckptDir,
    "--max_steps","$MaxSteps",
    "--save_every","$SaveEvery",
    "--log_every","$LogEvery",
    "--num_workers","$NumWorkers"
  )
  if($ConfigPath -and (Test-Path $ConfigPath)){ $args += @("--config",$ConfigPath) }

  Invoke-FBLStep -Ctx $ctx -Name "Run training (tee log)" -Block {
    "RUNROOT=$runRoot" | Tee-Object -FilePath $logFile -Append | Out-Null
    "ENTRY=$($script:entry)" | Tee-Object -FilePath $logFile -Append | Out-Null
        # GUARD: ensure python args are valid (avoid falling into interactive REPL)
    if (-not $script:entry -or -not (Test-Path $script:entry)) {
      throw "Train entrypoint er ikke satt eller finnes ikke: $($script:entry)"
    }
    if (-not $pyArgs -or $pyArgs.Count -lt 2) {
      throw "pyArgs er tom/for kort. Dette ville startet python interaktivt. pyArgsCount=$($pyArgs.Count)"
    }
    if ($pyArgs[0] -notmatch '\.py
  }
}
finally {
  foreach($s in $subs){ Unregister-Event -SourceIdentifier $s.Name -ErrorAction SilentlyContinue }
  $fsw.EnableRaisingEvents=$false
  $fsw.Dispose()
  Pop-Location

  if($script:seen.Count -eq 0){
    Write-FBLError -Ctx $ctx -Step "CheckpointWatch" -Message "Ingen checkpoint/model artifacts observert under runRoot"
    Write-Host "[ALERT] Ingen checkpoint/model artifacts observert under runRoot." -ForegroundColor Red
  } else {
    Write-Host "OK: Observerte $($script:seen.Count) unike artifact-paths." -ForegroundColor Green
  }

  $report = Finalize-FBLRun -Ctx $ctx
  Write-Host "FBL report: $report" -ForegroundColor Cyan
  Write-Host "Train log:   $logFile" -ForegroundColor Cyan
}


) {
      throw "Første argument er ikke en .py-fil. pyArgs[0]=$($pyArgs[0])"
    }
    & $PythonExe @pyArgs 2>&1 | Tee-Object -FilePath $logFile -Append
  }
}
finally {
  foreach($s in $subs){ Unregister-Event -SourceIdentifier $s.Name -ErrorAction SilentlyContinue }
  $fsw.EnableRaisingEvents=$false
  $fsw.Dispose()
  Pop-Location

  if($script:seen.Count -eq 0){
    Write-FBLError -Ctx $ctx -Step "CheckpointWatch" -Message "Ingen checkpoint/model artifacts observert under runRoot"
    Write-Host "[ALERT] Ingen checkpoint/model artifacts observert under runRoot." -ForegroundColor Red
  } else {
    Write-Host "OK: Observerte $($script:seen.Count) unike artifact-paths." -ForegroundColor Green
  }

  $report = Finalize-FBLRun -Ctx $ctx
  Write-Host "FBL report: $report" -ForegroundColor Cyan
  Write-Host "Train log:   $logFile" -ForegroundColor Cyan
}



