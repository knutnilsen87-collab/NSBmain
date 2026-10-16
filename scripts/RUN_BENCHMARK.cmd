@echo off
rem Roterer signeringsnokkelen og kjorer NSB-malestokken pa GPU.
rem Fremdrift: eval\results\RUN.log og eval\results\RUN_STATUS.json
cd /d "%~dp0.."
where pwsh >/dev/null 2>/dev/null || (echo PowerShell 7 ^(pwsh^) mangler. Installer fra https://aka.ms/powershell && pause && exit /b 1)
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\rotate_signing_key.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 %*
echo.
echo Ferdig. Se eval\results\BENCHMARK.md
pause
