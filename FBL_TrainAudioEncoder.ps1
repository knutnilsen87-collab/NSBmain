# -------------------------------
# FBL Logging (auto-injected)
# -------------------------------
$ProjectRoot = "F:\NorwegianSpeechBase"
. (Join-Path $ProjectRoot "scripts\fbl_logging.ps1")
Init-FblRun -ProjectRoot $ProjectRoot -TaskId "AUTO" -ScriptName $MyInvocation.MyCommand.Name | Out-Null
# -------------------------------
# === Front and backend Legend (FBL) Auto Script ===
# Description: Full Audio Encoder-trening (self-supervised) med venv + progressbar + signerte logger
# Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

param()

# -------------------------------
# Konfig
# -------------------------------
$ProjectRoot       = "F:\NorwegianSpeechBase"
$dataIndexJsonl    = Join-Path $ProjectRoot "data\raw\norwegian_raw_wav_index.jsonl"

$scriptsDir        = Join-Path $ProjectRoot "scripts"
$modelsDir         = Join-Path $ProjectRoot "models"
$audioModelDir     = Join-Path $modelsDir "audio_encoder"

$envsDir           = Join-Path $ProjectRoot "envs"
$venvDir           = Join-Path $envsDir "audio_encoder_env"

$logsDir           = Join-Path $ProjectRoot "logs"
$rollbackDir       = Join-Path $ProjectRoot "rollback"
$stateDir          = Join-Path $ProjectRoot "state"
$reportsDir        = Join-Path $ProjectRoot "reports"
$securityDir       = Join-Path $ProjectRoot "security"
$securityKeysDir   = Join-Path $securityDir "keys"
$securityPubDir    = Join-Path $securityDir "pubkeys"
$securitySigDir    = Join-Path $securityDir "signatures"
$tempDir           = Join-Path $ProjectRoot "temp"
$configDir         = Join-Path $ProjectRoot "config"
$transparencyLog   = Join-Path $securityDir "TransparencyLog.jsonl"

$pythonScriptPath  = Join-Path $scriptsDir "train_audio_encoder_selfsup.py"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile   = Join-Path $logsDir ("train_audio_encoder_full_{0}.log" -f $timestamp)

# -------------------------------
# Hjelpefunksjoner
# -------------------------------
function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("INFO","WARN","ERROR")][string]$Level = "INFO"
    )
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

function Initialize-ProjectStructure {
    Ensure-Directory $ProjectRoot
    Ensure-Directory $scriptsDir
    Ensure-Directory $modelsDir
    Ensure-Directory $audioModelDir
    Ensure-Directory $envsDir
    Ensure-Directory $logsDir
    Ensure-Directory $rollbackDir
    Ensure-Directory $stateDir
    Ensure-Directory $reportsDir
    Ensure-Directory $securityDir
    Ensure-Directory $securityKeysDir
    Ensure-Directory $securityPubDir
    Ensure-Directory $securitySigDir
    Ensure-Directory $tempDir
    Ensure-Directory $configDir
}

function Initialize-Keys {
    $privKeyPath = Join-Path $securityKeysDir "private_key.xml"
    $pubKeyPath  = Join-Path $securityPubDir "public_key.xml"

    if (-not (Test-Path $privKeyPath -PathType Leaf -ErrorAction SilentlyContinue) -or
        -not (Test-Path $pubKeyPath  -PathType Leaf -ErrorAction SilentlyContinue)) {

        Write-Log "Ingen eksisterende RSA-nøkler funnet. Genererer nytt nøkkelpar..." "WARN"
        $rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider(2048)
        $privateXml = $rsa.ToXmlString($true)
        $publicXml  = $rsa.ToXmlString($false)
        Set-Content -Path $privKeyPath -Value $privateXml
        Set-Content -Path $pubKeyPath  -Value $publicXml
        Write-Log "RSA-nøkkelpar generert og lagret." "INFO"
    }
    else {
        Write-Log "Eksisterende RSA-nøkler funnet. Bruker disse." "INFO"
    }
}

function Get-RSAProvider {
    $privKeyPath = Join-Path $securityKeysDir "private_key.xml"
    if (-not (Test-Path $privKeyPath)) {
        throw "Private key mangler: $privKeyPath"
    }
    $xml = Get-Content -Path $privKeyPath -Raw
    $rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
    $rsa.PersistKeyInCsp = $false
    $rsa.FromXmlString($xml)
    return $rsa
}

function Protect-LogFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Host "Ingen logg å signere: $Path" -ForegroundColor Yellow
        return
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $sha   = [System.Security.Cryptography.SHA256]::Create()
    $hash  = $sha.ComputeHash($bytes)
    $hashB64 = [System.Convert]::ToBase64String($hash)

    $rsa = Get-RSAProvider
    $signatureBytes = $rsa.SignHash($hash, [System.Security.Cryptography.CryptoConfig]::MapNameToOID("SHA256"))
    $sigB64 = [System.Convert]::ToBase64String($signatureBytes)

    $sigFileName = [System.IO.Path]::GetFileNameWithoutExtension($Path) + ".sig"
    $sigFilePath = Join-Path $securitySigDir $sigFileName
    Set-Content -Path $sigFilePath -Value $sigB64

    $entry = @{
        timestamp       = (Get-Date).ToString("o")
        file            = $Path
        hash_sha256_b64 = $hashB64
        signature_file  = $sigFilePath
        status          = "signed"
    } | ConvertTo-Json -Compress

    Add-Content -Path $transparencyLog -Value $entry
    Write-Host "Logg signert og registrert i TransparencyLog." -ForegroundColor Green
}

# -------------------------------
# Init struktur + logg
# -------------------------------
Initialize-ProjectStructure
New-Item -ItemType File -Path $logFile -Force | Out-Null

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Full Audio Encoder-trening (selfsup + venv) " -ForegroundColor Cyan
Write-Host " Prosjektrot: $ProjectRoot" -ForegroundColor Cyan
Write-Host " Loggfil:     $logFile" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

Write-Log "Starter full Audio Encoder-trening..." "INFO"
Write-Log "Prosjektrot: $ProjectRoot" "INFO"
Write-Log "Dataindex:   $dataIndexJsonl" "INFO"
Write-Log "Loggfil:     $logFile" "INFO"

Initialize-Keys

if (-not (Test-Path $dataIndexJsonl)) {
    Write-Log "Fant ikke dataindex JSONL: $dataIndexJsonl" "ERROR"
    throw "Mangler norwegian_raw_wav_index.jsonl – kjør rå-index-scriptet først."
}

# -------------------------------
# Venv
# -------------------------------
Ensure-Directory $envsDir

if (-not (Test-Path $venvDir)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Log "Fant ikke 'python' i PATH. Kan ikke opprette venv." "ERROR"
        throw "Installer Python og sørg for at 'python' er tilgjengelig i PATH."
    }

    Write-Log "Oppretter nytt venv på: $venvDir" "INFO"
    Write-Host "Oppretter venv (kan ta litt tid)..." -ForegroundColor Yellow
    & python -m venv "$venvDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Feil ved opprettelse av venv. Exit code: $LASTEXITCODE" "ERROR"
        throw "Kunne ikke opprette venv."
    }
}
else {
    Write-Log "Venv eksisterer allerede: $venvDir" "INFO"
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Log "Fant ikke venv-python på: $venvPython" "ERROR"
    throw "Noe er galt med venv-installasjonen."
}

Write-Host ">>> Bruker venv-python: $venvPython" -ForegroundColor Green
Write-Log "Bruker venv-python: $venvPython" "INFO"

# -------------------------------
# Avhengigheter
# -------------------------------
Write-Host ""
Write-Host ">>> Installerer/oppdaterer pip + torch + torchaudio + numpy + soundfile i venv..." -ForegroundColor Yellow
Write-Log "Installerer avhengigheter i venv..." "INFO"

& "$venvPython" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Log "Feil ved pip upgrade. Exit code: $LASTEXITCODE" "ERROR"
    throw "pip install feilet."
}

& "$venvPython" -m pip install torch torchaudio numpy soundfile
if ($LASTEXITCODE -ne 0) {
    Write-Log "Feil ved torch/torchaudio/numpy/soundfile install. Exit code: $LASTEXITCODE" "ERROR"
    throw "avhengigheter install feilet."
}

Write-Log "Avhengigheter OK i venv." "INFO"
Write-Host ">>> Avhengigheter ferdig installert." -ForegroundColor Green

# -------------------------------
# Python-treningsscript (med PROGRESS)
# -------------------------------
$pythonScriptContent = @'
import os
import json
import argparse
from datetime import datetime

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

import torchaudio
from torchaudio.functional import resample as ta_resample
import soundfile as sf

def parse_args():
    p = argparse.ArgumentParser(description="Self-supervised Audio Encoder training for Norwegian Speech Base")
    p.add_argument("--data_index", type=str, required=True,
                   help="Path til norwegian_raw_wav_index.jsonl")
    p.add_argument("--output_dir", type=str, required=True,
                   help="Hvor modell og logger skal lagres")
    p.add_argument("--sample_rate", type=int, default=16000)
    p.add_argument("--clip_duration", type=float, default=2.0,
                   help="Kliplengde i sekunder for hver trenings-sample")
    p.add_argument("--batch_size", type=int, default=32)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()

class NorwegianRawAudioDataset(Dataset):
    def __init__(self, index_path, sample_rate=16000, clip_duration=2.0, split="train"):
        self.sample_rate = sample_rate
        self.clip_samples = int(sample_rate * clip_duration)
        self.items = []

        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                if obj.get("split", "train") == split:
                    wav_path = obj.get("original_path")
                    if wav_path and os.path.isfile(wav_path):
                        self.items.append(wav_path)

        if len(self.items) == 0:
            raise RuntimeError(f"Ingen wav-filer funnet for split='{split}' i {index_path}")

    def __len__(self):
        return len(self.items)

    def _load_audio(self, path):
        wav_np, sr = sf.read(path, always_2d=True)  # [T, C]
        wav_np = wav_np.T  # [C, T]
        wav = torch.from_numpy(wav_np).float()

        if wav.size(0) > 1:
            wav = wav.mean(dim=0, keepdim=True)

        if sr != self.sample_rate:
            wav = ta_resample(wav, orig_freq=sr, new_freq=self.sample_rate)

        return wav  # [1, T]

    def _random_crop(self, wav):
        T = wav.size(1)
        if T >= self.clip_samples:
            start = torch.randint(0, T - self.clip_samples + 1, (1,)).item()
            return wav[:, start:start+self.clip_samples]
        else:
            pad = self.clip_samples - T
            return F.pad(wav, (0, pad))

    def _augment(self, wav):
        wav = wav.clone()
        gain = 0.9 + 0.2 * torch.rand(1).item()
        wav = wav * gain
        noise_level = 0.01 * torch.rand(1).item()
        noise = noise_level * torch.randn_like(wav)
        wav = wav + noise
        return wav

    def __getitem__(self, idx):
        path = self.items[idx]
        wav = self._load_audio(path)
        wav = self._random_crop(wav)
        aug1 = self._augment(wav)
        aug2 = self._augment(wav)
        return aug1, aug2

class ConvEncoder(nn.Module):
    def __init__(self, in_channels=1, hidden_dim=256, proj_dim=128):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Conv1d(128, hidden_dim, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.proj = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, proj_dim),
        )

    def forward(self, x):
        h = self.conv(x)
        h = self.pool(h).squeeze(-1)
        z = self.proj(h)
        z = F.normalize(z, dim=-1)
        return h, z

def nt_xent_loss(z1, z2, temperature=0.1):
    batch_size = z1.size(0)
    z = torch.cat([z1, z2], dim=0)
    sim = torch.matmul(z, z.t())
    mask = torch.eye(2*batch_size, dtype=torch.bool, device=z.device)
    sim = sim.masked_fill(mask, -9e15)
    sim = sim / temperature

    targets = torch.arange(batch_size, 2*batch_size, device=z.device)
    targets = torch.cat([targets, torch.arange(0, batch_size, device=z.device)], dim=0)
    loss = F.cross_entropy(sim, targets)
    return loss

def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    device = torch.device(args.device)

    log_path = os.path.join(args.output_dir, "train_log.txt")
    print(f"[INFO] Starter trening. Logg: {log_path}", flush=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"=== Start {datetime.now().isoformat()} ===\n")
        lf.write(f"Args: {args}\n")

    dataset = NorwegianRawAudioDataset(
        index_path=args.data_index,
        sample_rate=args.sample_rate,
        clip_duration=args.clip_duration,
        split="train"
    )
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True,
                            num_workers=2, drop_last=True)

    model = ConvEncoder().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    total_steps = len(dataloader) * args.epochs
    global_step = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0

        for i, (aug1, aug2) in enumerate(dataloader, start=1):
            aug1 = aug1.to(device)
            aug2 = aug2.to(device)

            _, z1 = model(aug1)
            _, z2 = model(aug2)

            loss = nt_xent_loss(z1, z2, temperature=0.1)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            global_step += 1

            if i % 50 == 0 or i == len(dataloader):
                avg_loss = running_loss / i
                pct = 100.0 * (global_step / total_steps)
                msg = (f"[EPOCH {epoch}/{args.epochs}] "
                       f"step {i}/{len(dataloader)} "
                       f"({pct:.2f}% total) "
                       f"loss={avg_loss:.4f}")
                print(msg, flush=True)
                print(f"PROGRESS:{pct:.4f}", flush=True)
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(msg + "\n")

        ckpt_path = os.path.join(args.output_dir, f"audio_encoder_epoch{epoch}.pt")
        torch.save({"epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict()}, ckpt_path)
        ck_msg = f"[INFO] Lagret checkpoint: {ckpt_path}"
        print(ck_msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(ck_msg + "\n")

    final_path = os.path.join(args.output_dir, "audio_encoder_final.pt")
    torch.save(model.state_dict(), final_path)
    end_msg = f"[INFO] Ferdig trening. Lagret final model til {final_path}"
    print(end_msg, flush=True)
    print("PROGRESS:100.0", flush=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(end_msg + "\n")
        lf.write(f"=== Slutt {datetime.now().isoformat()} ===\n")

if __name__ == "__main__":
    main()
'@

Ensure-Directory $scriptsDir
if (Test-Path $pythonScriptPath) {
    $bakName = "train_audio_encoder_selfsup.py.bak_{0}" -f $timestamp
    Move-Item -Path $pythonScriptPath -Destination (Join-Path $rollbackDir $bakName) -Force
    Write-Log "Eksisterende $pythonScriptPath flyttet til rollback ($bakName)." "WARN"
}
$pythonScriptContent | Set-Content -Path $pythonScriptPath -Encoding UTF8
Write-Log "Skrev oppdatert Python-treningsscript til $pythonScriptPath" "INFO"

# -------------------------------
# Start Python med PROGRESS-parsing
# -------------------------------
Write-Host ""
Write-Host ">>> Starter Python-trening via venv..." -ForegroundColor Cyan
Write-Host ">>> Loggfil (FBL): $logFile" -ForegroundColor Green
Write-Host ">>> Python-script: $pythonScriptPath" -ForegroundColor Green
Write-Host ">>> Modell mappe:  $audioModelDir" -ForegroundColor Green
Write-Host ">>> Venv python:   $venvPython" -ForegroundColor Green
Write-Host ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $venvPython
$psi.Arguments = "`"$pythonScriptPath`" --data_index `"$dataIndexJsonl`" --output_dir `"$audioModelDir`""
$psi.WorkingDirectory = $ProjectRoot
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()

$overallActivity = "Audio Encoder trening (Python)"
$progress = 0.0
$lastOutputTime = Get-Date
$spinnerChars = "/-\|"
$spinnerIndex = 0

while (-not $proc.HasExited) {

    $hadOutput = $false

    while (-not $proc.StandardOutput.EndOfStream) {
        $line = $proc.StandardOutput.ReadLine()
        if ($line) {
            $hadOutput = $true
            $lastOutputTime = Get-Date

            if ($line -match "^PROGRESS:(\d+(\.\d+)?)$") {
                $progress = [double]$matches[1]
                Write-Progress -Activity $overallActivity `
                               -Status ("{0:N2}% fullført" -f $progress) `
                               -PercentComplete $progress
            }
            else {
                Write-Host $line
            }
        }
        else { break }
    }

    while (-not $proc.StandardError.EndOfStream) {
        $err = $proc.StandardError.ReadLine()
        if ($err) {
            $hadOutput = $true
            $lastOutputTime = Get-Date
            Write-Host "[PYTHON ERR] $err" -ForegroundColor Red
        }
        else { break }
    }

    $elapsed = (Get-Date) - $lastOutputTime
    if (-not $hadOutput -and $elapsed.TotalSeconds -ge 5) {
        $spinnerIndex = ($spinnerIndex + 1) % $spinnerChars.Length
        $spinner = $spinnerChars[$spinnerIndex]
        $status = ("Kjører... {0} (ingen ny output siste {1:N0}s)" -f $spinner, $elapsed.TotalSeconds)
        Write-Progress -Activity $overallActivity `
                       -Status $status `
                       -PercentComplete $progress
    }

    Start-Sleep -Milliseconds 100
}

while (-not $proc.StandardOutput.EndOfStream) {
    $line = $proc.StandardOutput.ReadLine()
    if ($line) {
        if ($line -match "^PROGRESS:(\d+(\.\d+)?)$") {
            $progress = [double]$matches[1]
            Write-Progress -Activity $overallActivity `
                           -Status ("{0:N2}% fullført" -f $progress) `
                           -PercentComplete $progress
        } else {
            Write-Host $line
        }
    }
}
while (-not $proc.StandardError.EndOfStream) {
    $err = $proc.StandardError.ReadLine()
    if ($err) {
        Write-Host "[PYTHON ERR] $err" -ForegroundColor Red
    }
}

Write-Progress -Activity $overallActivity -Status "Fullført" -Completed

if ($proc.ExitCode -eq 0) {
    Write-Log "Python-trening fullført med exit code 0." "INFO"
} else {
    Write-Log "Python-trening avsluttet med exit code $($proc.ExitCode)." "ERROR"
}

Protect-LogFile -Path $logFile

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " Full Audio Encoder-trening script fullført." -ForegroundColor Green
Write-Host " Loggfil (FBL): $logFile" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

