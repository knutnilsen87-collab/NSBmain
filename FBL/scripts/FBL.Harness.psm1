Set-StrictMode -Version Latest

function Ensure-FBLDirs { param([string]$FBLRoot)
  $need = @("logs\agent","logs\errors","reports","signatures","temp","security\keys","security\pubkeys","runs")
  foreach($d in $need){ New-Item -ItemType Directory -Force -Path (Join-Path $FBLRoot $d) | Out-Null }
}

function Get-FBLRunId { ([guid]::NewGuid().ToString("N")) }
function Get-FBLTaskId { ([guid]::NewGuid().ToString("N")) }

function New-FBLSignature {
  param([string]$FBLRoot,[string]$FilePath,[string]$RunId,[string]$TaskId)
  $priv = Join-Path $FBLRoot "security\keys\fbl_signing_private.pem"
  $pem = Get-Content -LiteralPath $priv -Raw
  $rsa = [System.Security.Cryptography.RSA]::Create()
  $rsa.ImportFromPem($pem)
  $bytes = [System.IO.File]::ReadAllBytes($FilePath)
  $sig = $rsa.SignData($bytes,[System.Security.Cryptography.HashAlgorithmName]::SHA256,[System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
  $rsa.Dispose()

  $sigDir = Join-Path $FBLRoot "signatures"
  New-Item -ItemType Directory -Force -Path $sigDir | Out-Null
  $sigPath = Join-Path $sigDir ("{0}.{1}.sig" -f ([IO.Path]::GetFileName($FilePath)),$RunId)
  Set-Content -LiteralPath $sigPath -Value ([Convert]::ToBase64String($sig)) -Encoding ascii -NoNewline

  $tlog = Join-Path $FBLRoot "logs\agent\TransparencyLog.jsonl"
  $sha = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
  $evt = [ordered]@{ timestamp=(Get-Date).ToString("o"); runId=$RunId; taskId=$TaskId; file=$FilePath; sha256=$sha; signatureFile=$sigPath } |
    ConvertTo-Json -Compress
  Add-Content -LiteralPath $tlog -Value $evt -Encoding utf8
  return $sigPath
}

function Start-FBLRun {
  param([string]$FBLRoot,[string]$TaskName)
  Ensure-FBLDirs -FBLRoot $FBLRoot
  $runId = Get-FBLRunId; $taskId = Get-FBLTaskId
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $base = Join-Path $FBLRoot "logs\agent"
  $txt  = Join-Path $base ("run_{0}_{1}.log" -f $ts,$runId)
  $json = Join-Path $base ("run_{0}_{1}.jsonl" -f $ts,$runId)
  $err  = Join-Path $FBLRoot ("logs\errors\errors_{0}_{1}.jsonl" -f $ts,$runId)

  "ERROR SUMMARY (TOP): 0 errors" | Set-Content -LiteralPath $txt -Encoding utf8
  Add-Content -LiteralPath $txt -Value ("RUN_START: {0} | runId={1} | taskId={2} | {3}" -f (Get-Date).ToString("o"),$runId,$taskId,$TaskName)
  Add-Content -LiteralPath $json -Value (([ordered]@{t=(Get-Date).ToString("o");type="RUN_START";runId=$runId;taskId=$taskId;task=$TaskName} | ConvertTo-Json -Compress))

  return [pscustomobject]@{ FBLRoot=$FBLRoot; RunId=$runId; TaskId=$taskId; TaskName=$TaskName; StartTime=(Get-Date); LogTxt=$txt; LogJsonl=$json; ErrJsonl=$err; ErrorCount=0 }
}

function Log-Json {
  param($Ctx,[string]$Type,[hashtable]$Data)
  $h = [ordered]@{ t=(Get-Date).ToString("o"); type=$Type; runId=$Ctx.RunId; taskId=$Ctx.TaskId } + $Data
  Add-Content -LiteralPath $Ctx.LogJsonl -Value (($h | ConvertTo-Json -Compress)) -Encoding utf8
}

function Write-FBLError { param($Ctx,[string]$Step,[string]$Message)
  $Ctx.ErrorCount++
  Add-Content -LiteralPath $Ctx.ErrJsonl -Value (([ordered]@{t=(Get-Date).ToString("o");type="ERROR";runId=$Ctx.RunId;taskId=$Ctx.TaskId;step=$Step;message=$Message} | ConvertTo-Json -Compress)) -Encoding utf8
  Add-Content -LiteralPath $Ctx.LogTxt -Value ("ERROR: step={0} | {1}" -f $Step,$Message)
  Log-Json -Ctx $Ctx -Type "ERROR" -Data @{ step=$Step; message=$Message }
}

function Invoke-FBLStep { param($Ctx,[string]$Name,[scriptblock]$Block)
  $sw=[System.Diagnostics.Stopwatch]::StartNew()
  Add-Content -LiteralPath $Ctx.LogTxt -Value ("STEP_START: {0} | {1}" -f (Get-Date).ToString("o"),$Name)
  Log-Json -Ctx $Ctx -Type "STEP_START" -Data @{ name=$Name }
  try { & $Block; $sw.Stop()
    Add-Content -LiteralPath $Ctx.LogTxt -Value ("STEP_OK: {0} | {1} | {2}ms" -f (Get-Date).ToString("o"),$Name,$sw.ElapsedMilliseconds)
    Log-Json -Ctx $Ctx -Type "STEP_OK" -Data @{ name=$Name; ms=$sw.ElapsedMilliseconds }
  } catch { $sw.Stop(); Write-FBLError -Ctx $Ctx -Step $Name -Message $_.Exception.Message; throw }
}

function Finalize-FBLRun { param($Ctx)
  $lines = Get-Content -LiteralPath $Ctx.LogTxt
  $lines[0] = "ERROR SUMMARY (TOP): $($Ctx.ErrorCount) errors"
  Set-Content -LiteralPath $Ctx.LogTxt -Value $lines -Encoding utf8
  Add-Content -LiteralPath $Ctx.LogTxt -Value ("ERROR SUMMARY (BOTTOM): $($Ctx.ErrorCount) errors")
  Add-Content -LiteralPath $Ctx.LogTxt -Value ("RUN_END: {0} | runId={1} | taskId={2}" -f (Get-Date).ToString("o"),$Ctx.RunId,$Ctx.TaskId)

  $sig1 = New-FBLSignature -FBLRoot $Ctx.FBLRoot -FilePath $Ctx.LogTxt -RunId $Ctx.RunId -TaskId $Ctx.TaskId
  $sig2 = New-FBLSignature -FBLRoot $Ctx.FBLRoot -FilePath $Ctx.LogJsonl -RunId $Ctx.RunId -TaskId $Ctx.TaskId

  $rep = Join-Path $Ctx.FBLRoot ("reports\report_{0}.md" -f $Ctx.RunId)
  @(
    "# FBL Report",
    "",
    "- runId: $($Ctx.RunId)",
    "- taskId: $($Ctx.TaskId)",
    "- task: $($Ctx.TaskName)",
    "- start: $($Ctx.StartTime.ToString("o"))",
    "- errors: $($Ctx.ErrorCount)",
    "- log: $($Ctx.LogTxt)",
    "- jsonl: $($Ctx.LogJsonl)",
    "- sig(log): $sig1",
    "- sig(jsonl): $sig2"
  ) | Set-Content -LiteralPath $rep -Encoding utf8
  New-FBLSignature -FBLRoot $Ctx.FBLRoot -FilePath $rep -RunId $Ctx.RunId -TaskId $Ctx.TaskId | Out-Null
  return $rep
}
