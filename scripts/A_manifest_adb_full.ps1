param(
  [string]$ProjectRoot = "F:\NorwegianSpeechBase",
  [string]$SourceRoot  = "F:\GPT\datasetVoice\norwegian",

  # ADB JSON roots (train/test/dictation)
  [string[]]$JsonRoots = @(
    "F:\GPT\datasetVoice\norwegian\ADB_NOR_0463",
    "F:\GPT\datasetVoice\norwegian\ADB_NOR_0464",
    "F:\GPT\datasetVoice\norwegian\ADB_OD_Nor.NOR"
  ),

  # WAV roots (we will auto-discover lydfiler_16* folders under SourceRoot as well)
  [string[]]$WavRoots = @(),

  [string]$OutManifest = "F:\NorwegianSpeechBase\tts_vits\data\consent_voice\raw_manifest.adb.txt",

  [switch]$WriteDebugSamples = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p){ if(!(Test-Path -LiteralPath $p)){ New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function NowStamp(){ Get-Date -Format "yyyy-MM-dd HH:mm:ss" }

# ---------- logging ----------
$LogsRoot = Join-Path $ProjectRoot "logs_v2"
$RunId = [guid]::NewGuid().ToString()
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Ensure-Dir $LogsRoot
Ensure-Dir (Join-Path $LogsRoot "tx")
Ensure-Dir (Join-Path $LogsRoot "telemetry")
Ensure-Dir (Join-Path $LogsRoot "reports")

$TxJsonl = Join-Path $LogsRoot "tx" ("tx_adb_manifest_full_{0}_{1}.jsonl" -f $ts, $RunId)
$TxTxt   = Join-Path $LogsRoot "tx" ("tx_adb_manifest_full_{0}_{1}.txt"  -f $ts, $RunId)
$TelJson = Join-Path $LogsRoot "telemetry" ("telemetry_adb_manifest_full_{0}_{1}.json" -f $ts, $RunId)
$Report  = Join-Path $LogsRoot "reports" ("report_adb_manifest_full_{0}_{1}.md" -f $ts, $RunId)

$telemetry = [System.Collections.Generic.List[object]]::new()

function Write-Tx {
  param(
    [string]$Step,
    [string]$Msg,
    [string]$Level="INFO",
    [hashtable]$Data=@{}
  )
  $evt = [ordered]@{
    ts    = (Get-Date).ToString("o")
    runId = $RunId
    step  = $Step
    level = $Level
    msg   = $Msg
    data  = $Data
  }
  ($evt | ConvertTo-Json -Compress -Depth 10) | Add-Content -LiteralPath $TxJsonl
  ("[{0}] [{1}] {2} :: {3}" -f (NowStamp), $Level, $Step, $Msg) | Add-Content -LiteralPath $TxTxt
  Write-Host ("[{0}] [{1}] {2} :: {3}" -f (NowStamp), $Level, $Step, $Msg)
}

function Write-Telemetry {
  param(
    [string]$Step,
    [string]$Kind,
    [string]$Message,
    [hashtable]$Context=@{}
  )
  $telemetry.Add([ordered]@{
    ts=(Get-Date).ToString("o")
    runId=$RunId
    step=$Step
    kind=$Kind
    message=$Message
    context=$Context
  }) | Out-Null
}

function Flush-Telemetry {
  ($telemetry | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $TelJson -Encoding UTF8
}

# ---------- helpers ----------
function Get-StringCandidates {
  param($obj)
  $vals = New-Object System.Collections.Generic.List[string]
  if($null -eq $obj){ return $vals }
  foreach($p in $obj.PSObject.Properties){
    $v = $p.Value
    if($v -is [string]){
      $s = $v.Trim()
      if($s){ $vals.Add($s) }
    }
  }
  return $vals
}

function Pick-Text {
  param($rec)
  foreach($k in @("text","transcript","transcription","sentence","orth","prompt","normalized_text","txt","utt","utterance")){
    if($rec.PSObject.Properties.Name -contains $k){
      $v = $rec.$k
      if($v -is [string] -and $v.Trim()){
        return $v.Trim()
      }
    }
  }
  # fallback: any string that looks like a sentence (has letters + space)
  $cands = Get-StringCandidates $rec
  $best = $cands | Where-Object { $_.Length -ge 3 -and $_ -match "[A-Za-zÆØÅæøå]" } | Select-Object -First 1
  return ($best ?? "")
}

function Pick-WavName {
  param($rec)
  foreach($k in @("wav","wave","audio","file","filename","audio_filepath","wav_path","path")){
    if($rec.PSObject.Properties.Name -contains $k){
      $v = $rec.$k
      if($v -is [string] -and $v.Trim()){
        $s = $v.Trim().Trim('"')
        if($s -match "\.wav$"){ return [System.IO.Path]::GetFileName($s) }
        # sometimes JSON stores base w/o extension
        if($s -notmatch "\." -and $s.Length -gt 1){ return ($s + ".wav") }
      }
    }
  }
  # fallback: any string value ending with .wav
  $cands = Get-StringCandidates $rec
  $wav = $cands | Where-Object { $_ -match "\.wav$" } | Select-Object -First 1
  if($wav){ return [System.IO.Path]::GetFileName($wav) }
  return ""
}

# ---------- preflight ----------
Write-Tx "PRECHECK" "Starter ADB manifest full build. RunId=$RunId"

if(!(Test-Path -LiteralPath $ProjectRoot)){ throw "ProjectRoot finnes ikke: $ProjectRoot" }
if(!(Test-Path -LiteralPath $SourceRoot)){ throw "SourceRoot finnes ikke: $SourceRoot" }

$consentRoot = Join-Path $ProjectRoot "tts_vits\data\consent_voice"
Ensure-Dir $consentRoot
Ensure-Dir (Split-Path $OutManifest -Parent)

# Auto-discover wav roots if not provided
if($WavRoots.Count -eq 0){
  $auto = Get-ChildItem -LiteralPath $SourceRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^lydfiler_16" } |
    ForEach-Object { $_.FullName }
  $WavRoots = @($auto)
}

Write-Tx "CONFIG" ("JsonRoots={0} | WavRoots={1} | OutManifest={2}" -f ($JsonRoots -join ","), ($WavRoots -join ","), $OutManifest)

# Validate json roots
$validJsonRoots = @()
foreach($jr in $JsonRoots){
  if(Test-Path -LiteralPath $jr){ $validJsonRoots += $jr }
  else { Write-Tx "PRECHECK" "JSON-root mangler: $jr (hopper over)" "WARN"; Write-Telemetry "PRECHECK" "missing_json_root" "JSON-root mangler" @{path=$jr} }
}
if($validJsonRoots.Count -eq 0){ throw "Ingen gyldige JSON-roots. Sjekk JsonRoots i scriptet." }

# Validate wav roots
$validWavRoots = @()
foreach($wr in $WavRoots){
  if(Test-Path -LiteralPath $wr){ $validWavRoots += $wr }
  else { Write-Tx "PRECHECK" "WAV-root mangler: $wr (hopper over)" "WARN"; Write-Telemetry "PRECHECK" "missing_wav_root" "WAV-root mangler" @{path=$wr} }
}
if($validWavRoots.Count -eq 0){ throw "Ingen gyldige WAV-roots. Sjekk WavRoots eller at lydfiler_16* finnes." }

# ---------- STEP 1: index wav files ----------
Write-Tx "WAV_INDEX" "Indekserer wav-filer (basename -> fullpath list)... dette kan ta tid."
$wavIndex = @{}   # key=lowercase basename, val=list of fullpaths
$totalWavs = 0
$rootIdx = 0

foreach($wr in $validWavRoots){
  $rootIdx++
  Write-Tx "WAV_INDEX" "Scanner root $rootIdx/$($validWavRoots.Count): $wr"
  $files = Get-ChildItem -LiteralPath $wr -Recurse -File -Filter *.wav -ErrorAction SilentlyContinue
  $n = $files.Count
  $i = 0
  foreach($f in $files){
    $i++; $totalWavs++
    if($i % 5000 -eq 0){
      $pct = [math]::Round(($i / [math]::Max(1,$n)) * 100, 2)
      Write-Progress -Activity "Indekserer WAV ($wr)" -Status "$i / $n" -PercentComplete $pct
    }
    $bn = $f.Name.ToLowerInvariant()
    if(!$wavIndex.ContainsKey($bn)){ $wavIndex[$bn] = New-Object System.Collections.Generic.List[string] }
    $wavIndex[$bn].Add($f.FullName) | Out-Null
  }
  Write-Progress -Activity "Indekserer WAV ($wr)" -Completed
  Write-Tx "WAV_INDEX" "Root ferdig: $wr | wavs=$n | totalIndexKeys=$($wavIndex.Keys.Count)"
}
Write-Tx "WAV_INDEX" "WAV indeks ferdig. totalWavs=$totalWavs | unikeBasenames=$($wavIndex.Keys.Count)"

# ---------- STEP 2: parse ADB JSON and build manifest lines ----------
Write-Tx "JSON_PARSE" "Leser JSON og matcher (wav|text)..."

$manifestLines = New-Object System.Collections.Generic.List[string]

# detailed counters
$stats = [ordered]@{
  jsonFilesTotal = 0
  jsonFilesParsed = 0
  sessionsWithValRecordings = 0
  recordingsTotal = 0
  recordingsNoText = 0
  recordingsNoWavRef = 0
  recordingsWavNotFound = 0
  pairsAdded = 0
}

# samples
$sampleNoText = New-Object System.Collections.Generic.List[string]
$sampleNoWav  = New-Object System.Collections.Generic.List[string]
$sampleNotFound = New-Object System.Collections.Generic.List[string]

# Gather json files
$jsonFiles = New-Object System.Collections.Generic.List[string]
foreach($jr in $validJsonRoots){
  $fs = Get-ChildItem -LiteralPath $jr -Recurse -File -Filter *.json -ErrorAction SilentlyContinue
  foreach($f in $fs){ $jsonFiles.Add($f.FullName) | Out-Null }
}
$stats.jsonFilesTotal = $jsonFiles.Count
Write-Tx "JSON_PARSE" "Fant JSON-filer: $($stats.jsonFilesTotal)"

if($jsonFiles.Count -eq 0){ throw "Fant 0 json-filer i ADB_NOR_0463/0464/OD. Sjekk stier." }

$jfIdx = 0
foreach($jf in $jsonFiles){
  $jfIdx++
  if($jfIdx % 25 -eq 0){
    $pct = [math]::Round(($jfIdx / $jsonFiles.Count) * 100, 2)
    Write-Progress -Activity "Parser JSON" -Status "$jfIdx / $($jsonFiles.Count)" -PercentComplete $pct
  }

  $stats.jsonFilesParsed++

  try {
    $raw = Get-Content -LiteralPath $jf -Raw -Encoding UTF8 -ErrorAction Stop
    if(-not $raw){ continue }
    $obj = $raw | ConvertFrom-Json -ErrorAction Stop
  } catch {
    Write-Tx "JSON_PARSE" "JSON parse-feil: $jf" "WARN"
    Write-Telemetry "JSON_PARSE" "json_parse_error" "ConvertFrom-Json feilet" @{file=$jf; error=$_.Exception.Message}
    continue
  }

  if($obj.PSObject.Properties.Name -notcontains "val_recordings"){ continue }

  $stats.sessionsWithValRecordings++

  $recs = $obj.val_recordings
  if($null -eq $recs){ continue }

  # normalize to array
  if($recs -isnot [System.Collections.IEnumerable] -or $recs -is [string]){
    $recs = @($recs)
  }

  foreach($rec in $recs){
    $stats.recordingsTotal++

    $text = Pick-Text $rec
    if([string]::IsNullOrWhiteSpace($text)){
      $stats.recordingsNoText++
      if($WriteDebugSamples -and $sampleNoText.Count -lt 20){ $sampleNoText.Add($jf) | Out-Null }
      continue
    }

    $wavName = Pick-WavName $rec
    if([string]::IsNullOrWhiteSpace($wavName)){
      $stats.recordingsNoWavRef++
      if($WriteDebugSamples -and $sampleNoWav.Count -lt 20){ $sampleNoWav.Add($jf) | Out-Null }
      continue
    }

    $key = $wavName.ToLowerInvariant()
    if(!$wavIndex.ContainsKey($key)){
      $stats.recordingsWavNotFound++
      if($WriteDebugSamples -and $sampleNotFound.Count -lt 20){ $sampleNotFound.Add("$wavName  <=  $jf") | Out-Null }
      continue
    }

    # pick first match (if duplicates exist we log it)
    $paths = $wavIndex[$key]
    if($paths.Count -gt 1){
      Write-Telemetry "JSON_PARSE" "duplicate_wav_basename" "Flere filer med samme basename" @{wav=$wavName; count=$paths.Count; pick=$paths[0]}
    }

    $full = $paths[0]
    $manifestLines.Add("$full|$text") | Out-Null
    $stats.pairsAdded++
  }
}
Write-Progress -Activity "Parser JSON" -Completed -Status "Ferdig"

Write-Tx "JSON_PARSE" ("Stats: jsonParsed={0}/{1} sessionsWithValRecordings={2} recordingsTotal={3} pairsAdded={4} noText={5} noWavRef={6} wavNotFound={7}" -f `
  $stats.jsonFilesParsed, $stats.jsonFilesTotal, $stats.sessionsWithValRecordings, $stats.recordingsTotal, $stats.pairsAdded, $stats.recordingsNoText, $stats.recordingsNoWavRef, $stats.recordingsWavNotFound)

# If zero pairs, write a diagnosis report and hard fail
if($stats.pairsAdded -le 0){
  $md = @()
  $md += "# ADB manifest build report"
  $md += ""
  $md += "- RunId: $RunId"
  $md += "- SourceRoot: $SourceRoot"
  $md += "- JsonFilesTotal: $($stats.jsonFilesTotal)"
  $md += "- SessionsWithValRecordings: $($stats.sessionsWithValRecordings)"
  $md += "- RecordingsTotal: $($stats.recordingsTotal)"
  $md += "- PairsAdded: $($stats.pairsAdded)"
  $md += "- NoText: $($stats.recordingsNoText)"
  $md += "- NoWavRef: $($stats.recordingsNoWavRef)"
  $md += "- WavNotFound: $($stats.recordingsWavNotFound)"
  $md += ""
  $md += "## Sample files (debug)"
  $md += ""
  $md += "### JSON with missing text (first 20)"
  $md += ($sampleNoText | ForEach-Object { "- $_" })
  $md += ""
  $md += "### JSON with missing wav-ref (first 20)"
  $md += ($sampleNoWav | ForEach-Object { "- $_" })
  $md += ""
  $md += "### wav basename not found in wav roots (first 20)"
  $md += ($sampleNotFound | ForEach-Object { "- $_" })
  $md += ""
  $md += "## Next fix suggestions"
  $md += "- Sjekk at JSON faktisk inneholder tekstfelter (text/transcript/...) i val_recordings."
  $md += "- Sjekk om JSON refererer til ORIGINALFILNAVN (u0005001.wav) mens dine wav-filer er RENAMED (no10x005-..._u0005001-1.wav)."
  $md += "- Hvis wav er renamet: vi må matche på substring (original filnavn inne i renamet fil) – be om 'match-by-substring' variant."
  $md += ""

  $md -join "`r`n" | Set-Content -LiteralPath $Report -Encoding UTF8
  Flush-Telemetry
  Write-Tx "DONE" "0 match: ingen (wav|text) ble laget. Rapport skrevet: $Report" "ERROR"
  throw "0 match: ingen (wav|text). Se rapport: $Report"
}

# ---------- STEP 3: write manifest ----------
Ensure-Dir (Split-Path $OutManifest -Parent)

# backup if exists
if(Test-Path -LiteralPath $OutManifest){
  $bak = $OutManifest + ".bak_" + $ts
  Copy-Item -LiteralPath $OutManifest -Destination $bak -Force
  Write-Tx "WRITE" "Backup: $OutManifest -> $bak" "WARN"
}

# write
$manifestLines | Set-Content -LiteralPath $OutManifest -Encoding UTF8
Write-Tx "WRITE" "Manifest skrevet: $OutManifest | linjer=$($manifestLines.Count)"

# ---------- report ----------
$md = @()
$md += "# ADB manifest build report"
$md += ""
$md += "- RunId: $RunId"
$md += "- OutManifest: $OutManifest"
$md += "- ManifestLines: $($manifestLines.Count)"
$md += ""
$md += "## Stats"
foreach($k in $stats.Keys){ $md += "- $k: $($stats[$k])" }
$md += ""
$md += "## Preview (first 5 lines)"
$md += "```"
$md += (Get-Content -LiteralPath $OutManifest -TotalCount 5 -ErrorAction SilentlyContinue)
$md += "```"
$md += ""
$md += "## Notes"
$md += "- Wav indexing was by exact basename match."
$md += "- Hvis JSON peker på originalnavn, men wav er renamet (inneholder originalnavn som substring), trenger vi substring-match variant."

$md -join "`r`n" | Set-Content -LiteralPath $Report -Encoding UTF8

Flush-Telemetry

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " OK: raw_manifest.adb.txt generert" -ForegroundColor Green
Write-Host " RunId:   $RunId" -ForegroundColor Green
Write-Host " Manifest:$OutManifest" -ForegroundColor Green
Write-Host " Linjer:  $($manifestLines.Count)" -ForegroundColor Green
Write-Host " TxTxt:   $TxTxt" -ForegroundColor Green
Write-Host " Report:  $Report" -ForegroundColor Green
Write-Host " LogsRoot:$LogsRoot" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
