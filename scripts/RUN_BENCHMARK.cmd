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
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\rotate_signing_key.ps1
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 %*
set "NSB_RC=%ERRORLEVEL%"
echo.
if "%NSB_RC%"=="0" (echo Ferdig. Se eval\results\BENCHMARK.md) else (echo Feilet med kode %NSB_RC%. Se eval\results\RUN.log og RUN_STATUS.json)
popd
pause
exit /b %NSB_RC%
