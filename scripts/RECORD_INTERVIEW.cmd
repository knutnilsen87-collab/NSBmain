@echo off
rem Spill inn tre fiktive avhor med to personer. Fasit ma kontrolleres etterpa.
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\record.ps1 -Set avhor %*
set "NSB_RC=%ERRORLEVEL%"
popd
pause
exit /b %NSB_RC%
