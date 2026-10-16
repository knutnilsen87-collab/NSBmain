# =========================================================
# FBL Logging Module (dot-source)
# - Agent TRACE JSONL
# - Transaction INFO JSONL + TXT transcript
# - Audit INFO CSV + JSON
# - Error Telemetry WARN/ERROR JSON
# - Heuristic analysis JSONL -> Markdown report (lightweight)
# - SHA256 + RSA sign + TransparencyLog.jsonl
# =========================================================

Set-StrictMode -Version Latest

function New-FblGuid {
  return ([Guid]::NewGuid().ToString("N"))
}

function Ensure-Dir([string]$Path) {
  if (!(Test-Path $Path)) { New-Item -ItemType Directory -Path $Path -Force | Out-Null }
}

function Get-NowIso {
  return (Get-Date).ToString("o")
}

function Get-NowText {
  return (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
}

function Append-Jsonl {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][hashtable]$Obj)
  $line = ($Obj | ConvertTo-Json -Compress -Depth 30)
  Add-Content -Path $Path -Value $line -Encoding UTF8
}

function Ensure-RsaKeypair {
  param([Parameter(Mandatory=$true)][string]$PrivateKeyPath, [Parameter(Mandatory=$true)][string]$PublicKeyPath)

  if ((Test-Path $PrivateKeyPath) -and (Test-Path $PublicKeyPath)) { return }

  Ensure-Dir (Split-Path $PrivateKeyPath -Parent)
  Ensure-Dir (Split-Path $PublicKeyPath -Parent)

  $rsa = [System.Security.Cryptography.RSACryptoServiceProvider]::new(2048)
  Set-Content -Path $PrivateKeyPath -Value ($rsa.ToXmlString($true))  -Encoding UTF8
  Set-Content -Path $PublicKeyPath  -Value ($rsa.ToXmlString($false)) -Encoding UTF8
}

function Get-RsaFromPrivateKey {
  param([Parameter(Mandatory=$true)][string]$PrivateKeyPath, [Parameter(Mandatory=$true)][string]$PublicKeyPath)
  Ensure-RsaKeypair -PrivateKeyPath $PrivateKeyPath -PublicKeyPath $PublicKeyPath
  $xml = Get-Content -Path $PrivateKeyPath -Raw -Encoding UTF8
  $rsa = [System.Security.Cryptography.RSACryptoServiceProvider]::new()
  $rsa.FromXmlString($xml)
  return $rsa
}

function Protect-LogFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$RunId,
    [Parameter(Mandatory=$true)][string]$SigDir,
    [Parameter(Mandatory=$true)][string]$TransparencyPath,
    [Parameter(Mandatory=$true)][string]$PrivateKeyPath,
    [Parameter(Mandatory=$true)][string]$PublicKeyPath
  )

  if (!(Test-Path $Path)) { return }

  Ensure-Dir $SigDir
  Ensure-Dir (Split-Path $TransparencyPath -Parent)

  $rsa = Get-RsaFromPrivateKey -PrivateKeyPath $PrivateKeyPath -PublicKeyPath $PublicKeyPath

  $bytes = [System.IO.File]::ReadAllBytes($Path)
  $sha   = [System.Security.Cryptography.SHA256]::Create()
  $hash  = $sha.ComputeHash($bytes)
  $hashB64 = [Convert]::ToBase64String($hash)

  $sig = $rsa.SignHash($hash, "SHA256")
  $sigB64 = [Convert]::ToBase64String($sig)

  $sigPath = Join-Path $SigDir ((Split-Path $Path -Leaf) + ".sig.b64")
  Set-Content -Path $sigPath -Value $sigB64 -Encoding ASCII

  $entry = @{
    timestamp  = Get-NowIso
    runId      = $RunId
    file       = $Path
    sha256_b64 = $hashB64
    sig_b64    = $sigB64
    pubkey     = $PublicKeyPath
  } | ConvertTo-Json -Compress

  Add-Content -Path $TransparencyPath -Value $entry -Encoding UTF8
}

function Ensure-AuditHeaders {
  param([string]$AuditCsv, [string]$AuditJson)
  if (!(Test-Path $AuditCsv)) {
    "timestamp,runId,taskId,decisionType,target,before,after,reason" | Set-Content -Path $AuditCsv -Encoding UTF8
  }
  if (!(Test-Path $AuditJson)) {
    "[]" | Set-Content -Path $AuditJson -Encoding UTF8
  }
}

function Init-FblRun {
  param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [string]$TaskId = $null,
    [string]$ScriptName = $null,
    [ValidateSet("TRACE","INFO")][string]$AgentLevel = "TRACE"
  )

  $runId = New-FblGuid
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"

  $logsRoot = Join-Path $ProjectRoot "logs"
  $security = Join-Path $ProjectRoot "security"
  $reports  = Join-Path $ProjectRoot "reports"

  $agentDir = Join-Path $logsRoot "agent"
  $txDir    = Join-Path $logsRoot "transaction"
  $auditDir = Join-Path $logsRoot "audit"
  $telDir   = Join-Path $logsRoot "telemetry"
  $anaDir   = Join-Path $logsRoot "analysis"

  Ensure-Dir $logsRoot; Ensure-Dir $security; Ensure-Dir $reports
  Ensure-Dir $agentDir; Ensure-Dir $txDir; Ensure-Dir $auditDir; Ensure-Dir $telDir; Ensure-Dir $anaDir

  $keysDir  = Join-Path $security "keys"
  $pubDir   = Join-Path $security "pubkeys"
  $sigDir   = Join-Path $security "signatures"
  Ensure-Dir $keysDir; Ensure-Dir $pubDir; Ensure-Dir $sigDir

  $privateKey = Join-Path $keysDir "fbl_rsa_private.xml"
  $publicKey  = Join-Path $pubDir  "fbl_rsa_public.xml"
  $transparency = Join-Path $security "TransparencyLog.jsonl"

  $agentTrace   = Join-Path $agentDir ("agent_trace_{0}_{1}.jsonl" -f $ts,$runId)
  $txJsonl      = Join-Path $txDir    ("transaction_{0}_{1}.jsonl" -f $ts,$runId)
  $txTxt        = Join-Path $txDir    ("transaction_{0}_{1}.txt"   -f $ts,$runId)
  $auditCsv     = Join-Path $auditDir ("audit_{0}_{1}.csv"         -f $ts,$runId)
  $auditJson    = Join-Path $auditDir ("audit_{0}_{1}.json"        -f $ts,$runId)
  $telemetry    = Join-Path $telDir   ("telemetry_{0}_{1}.json"    -f $ts,$runId)
  $analysisJsonl= Join-Path $anaDir   ("analysis_{0}_{1}.jsonl"     -f $ts,$runId)
  $reportMd     = Join-Path $reports  ("heuristic_report_{0}_{1}.md" -f $ts,$runId)

  # init telemetry as array
  if (!(Test-Path $telemetry)) { "[]" | Set-Content -Path $telemetry -Encoding UTF8 }
  Ensure-AuditHeaders -AuditCsv $auditCsv -AuditJson $auditJson

  $ctx = [ordered]@{
    runId = $runId
    taskId = $TaskId
    script = $ScriptName
    projectRoot = $ProjectRoot
    agentTrace = $agentTrace
    transactionJsonl = $txJsonl
    transactionTxt = $txTxt
    auditCsv = $auditCsv
    auditJson = $auditJson
    telemetryJson = $telemetry
    analysisJsonl = $analysisJsonl
    reportMd = $reportMd
    sigDir = $sigDir
    transparency = $transparency
    privateKey = $privateKey
    publicKey = $publicKey
  }

  # make global for convenience
  $global:FBL = $ctx

  # Print paths (user requirement)
  Write-Host ""
  Write-Host "=============================================" -ForegroundColor Green
  Write-Host " FBL Logging aktiv (per-script run)" -ForegroundColor Green
  Write-Host (" RunId: {0}" -f $runId) -ForegroundColor Green
  if ($TaskId) { Write-Host (" TaskId: {0}" -f $TaskId) -ForegroundColor Green }
  if ($ScriptName) { Write-Host (" Script: {0}" -f $ScriptName) -ForegroundColor Green }
  Write-Host (" Transaction TXT:  {0}" -f $txTxt) -ForegroundColor Green
  Write-Host (" Transaction JSONL:{0}" -f $txJsonl) -ForegroundColor Green
  Write-Host (" Agent TRACE JSONL:{0}" -f $agentTrace) -ForegroundColor Green
  Write-Host (" Audit CSV:        {0}" -f $auditCsv) -ForegroundColor Green
  Write-Host (" Telemetry JSON:   {0}" -f $telemetry) -ForegroundColor Green
  Write-Host (" Report MD:        {0}" -f $reportMd) -ForegroundColor Green
  Write-Host "=============================================" -ForegroundColor Green
  Write-Host ""

  return $ctx
}

function Write-AgentTrace {
  param(
    [Parameter(Mandatory=$true)][string]$Agent,
    [Parameter(Mandatory=$true)][string]$Action,
    [hashtable]$Input = @{},
    [hashtable]$Output = @{},
    [double]$DurationMs = 0,
    [int]$ExitCode = 0,
    [string]$Error = $null,
    [string]$TaskId = $null
  )
  if (-not $global:FBL) { return }
  $obj = @{
    ts         = Get-NowIso
    level      = "TRACE"
    runId      = $global:FBL.runId
    taskId     = ($TaskId ?? $global:FBL.taskId)
    agent      = $Agent
    action     = $Action
    input      = $Input
    output     = $Output
    durationMs = $DurationMs
    exitCode   = $ExitCode
    error      = $Error
  }
  Append-Jsonl -Path $global:FBL.agentTrace -Obj $obj
}

function Write-Transaction {
  param(
    [Parameter(Mandatory=$true)][string]$Message,
    [string]$TaskId = $null,
    [string]$Step = $null,
    [ValidateSet("INFO","WARN","ERROR")][string]$Level = "INFO",
    [hashtable]$Meta = @{}
  )
  if (-not $global:FBL) { return }
  $obj = @{
    ts     = Get-NowIso
    level  = $Level
    runId  = $global:FBL.runId
    taskId = ($TaskId ?? $global:FBL.taskId)
    step   = $Step
    msg    = $Message
    meta   = $Meta
  }
  Append-Jsonl -Path $global:FBL.transactionJsonl -Obj $obj

  $txtLine = "[{0}] [{1}] runId={2} taskId={3} step={4} {5}" -f (Get-NowText), $Level, $global:FBL.runId, ($TaskId ?? $global:FBL.taskId), $Step, $Message
  Add-Content -Path $global:FBL.transactionTxt -Value $txtLine -Encoding UTF8
  Write-Host $txtLine
}

function Write-AuditDecision {
  param(
    [Parameter(Mandatory=$true)][string]$DecisionType,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$Before = "",
    [string]$After = "",
    [string]$Reason = "",
    [string]$TaskId = $null
  )
  if (-not $global:FBL) { return }
  Ensure-AuditHeaders -AuditCsv $global:FBL.auditCsv -AuditJson $global:FBL.auditJson
  $t = Get-NowIso

  $csvLine = '"' + ($t,$global:FBL.runId,($TaskId ?? $global:FBL.taskId),$DecisionType,$Target,$Before,$After,$Reason -join '","') + '"'
  Add-Content -Path $global:FBL.auditCsv -Value $csvLine -Encoding UTF8

  $arr = Get-Content -Path $global:FBL.auditJson -Raw -Encoding UTF8 | ConvertFrom-Json
  $arr += [pscustomobject]@{
    timestamp    = $t
    runId        = $global:FBL.runId
    taskId       = ($TaskId ?? $global:FBL.taskId)
    decisionType = $DecisionType
    target       = $Target
    before       = $Before
    after        = $After
    reason       = $Reason
  }
  ($arr | ConvertTo-Json -Depth 30) | Set-Content -Path $global:FBL.auditJson -Encoding UTF8
}

function Write-Telemetry {
  param(
    [Parameter(Mandatory=$true)][ValidateSet("WARN","ERROR")][string]$Level,
    [Parameter(Mandatory=$true)][string]$Message,
    [string]$TaskId = $null,
    [string]$Exception = $null,
    [string]$Line = $null,
    [string]$Recommendation = $null,
    [hashtable]$Context = @{}
  )
  if (-not $global:FBL) { return }

  $payload = @{
    ts             = Get-NowIso
    level          = $Level
    runId          = $global:FBL.runId
    taskId         = ($TaskId ?? $global:FBL.taskId)
    msg            = $Message
    exception      = $Exception
    line           = $Line
    recommendation = $Recommendation
    context        = $Context
  }

  if (!(Test-Path $global:FBL.telemetryJson)) { "[]" | Set-Content -Path $global:FBL.telemetryJson -Encoding UTF8 }
  $arr = Get-Content -Path $global:FBL.telemetryJson -Raw -Encoding UTF8 | ConvertFrom-Json
  $arr += [pscustomobject]$payload
  ($arr | ConvertTo-Json -Depth 30) | Set-Content -Path $global:FBL.telemetryJson -Encoding UTF8

  if ($Level -eq "ERROR") { Write-Host "[FBL TELEMETRY ERROR] $Message" -ForegroundColor Red }
  else { Write-Host "[FBL TELEMETRY WARN] $Message" -ForegroundColor Yellow }
}

function Run-HeuristicAnalysis {
  param([string]$TaskId = $null)

  if (-not $global:FBL) { return }

  $tele = @()
  try { $tele = (Get-Content -Path $global:FBL.telemetryJson -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { $tele = @() }

  foreach($e in $tele){
    $obj = @{
      ts     = Get-NowIso
      runId  = $global:FBL.runId
      taskId = ($TaskId ?? $global:FBL.taskId)
      kind   = "telemetry"
      level  = $e.level
      msg    = $e.msg
      hint   = $e.recommendation
      context= $e.context
    }
    Append-Jsonl -Path $global:FBL.analysisJsonl -Obj $obj
  }

  $errCount  = ($tele | Where-Object { $_.level -eq "ERROR" }).Count
  $warnCount = ($tele | Where-Object { $_.level -eq "WARN" }).Count

  $md = @()
  $md += "# Heuristisk rapport"
  $md += ""
  $md += "- **RunId:** $($global:FBL.runId)"
  if ($TaskId) { $md += "- **TaskId:** $TaskId" }
  $md += "- **Tid:** $(Get-NowText)"
  $md += "- **Errors:** $errCount | **Warnings:** $warnCount"
  $md += ""
  $md += "## Telemetry (siste 20)"
  if ($tele.Count -gt 0) {
    foreach($t in ($tele | Select-Object -Last 20)) {
      $md += "- **[$($t.level)]** $($t.msg)"
      if ($t.recommendation) { $md += "  - anbefaling: $($t.recommendation)" }
      if ($t.exception) { $md += "  - exception: $($t.exception)" }
      if ($t.line) { $md += "  - line: $($t.line)" }
    }
  } else {
    $md += "- (Ingen telemetry registrert)"
  }

  $md -join "`r`n" | Set-Content -Path $global:FBL.reportMd -Encoding UTF8
}

function Finalize-FblRun {
  # Sign + transparency for "known" files in current run
  if (-not $global:FBL) { return }

  foreach($p in @(
    $global:FBL.agentTrace,
    $global:FBL.transactionJsonl,
    $global:FBL.transactionTxt,
    $global:FBL.auditCsv,
    $global:FBL.auditJson,
    $global:FBL.telemetryJson,
    $global:FBL.analysisJsonl,
    $global:FBL.reportMd
  )){
    try {
      if (Test-Path $p) {
        Protect-LogFile -Path $p -RunId $global:FBL.runId -SigDir $global:FBL.sigDir -TransparencyPath $global:FBL.transparency -PrivateKeyPath $global:FBL.privateKey -PublicKeyPath $global:FBL.publicKey
      }
    } catch { }
  }
}

# -------------------------------
# Backward-compat shims (for old scripts)
# -------------------------------
function Write-Log {
  param([string]$Msg, [string]$Level="INFO")
  # map to transaction
  $lvl = $Level.ToUpperInvariant()
  if ($lvl -notin @("INFO","WARN","ERROR")) { $lvl = "INFO" }
  Write-Transaction -Message $Msg -Level $lvl -Step "legacy"
}
function Log {
  param([string]$Msg, [string]$Level="INFO")
  Write-Log -Msg $Msg -Level $Level
}
