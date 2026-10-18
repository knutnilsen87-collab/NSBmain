@echo off
rem Starter talemotoren lokalt og apner testsiden i nettleseren (Edge eller Chrome).
rem Stopp med Ctrl+C.
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_engine.ps1 %*
popd
pause
