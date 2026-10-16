@echo off
rem Roterer signeringsnokkelen og kjorer NSB-malestokken pa GPU.
rem Fremdrift: eval\results\RUN.log og eval\results\RUN_STATUS.json
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "NSB_PS=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined NSB_PS set "NSB_PS=powershell"
echo Bruker %NSB_PS% i %CD%
if not exist security\pubkeys\REVOKED.json "%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\rotate_signing_key.ps1
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 %*
echo.
echo Ferdig. Se eval\results\BENCHMARK.md
popd
pause
