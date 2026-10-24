@echo off
rem Maler vakt mot gjentakelsesloekker for dialekt_v1 (ca. 20-30 minutter pa RTX 4080).
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_loopguard.ps1 %*
set "NSB_RC=%ERRORLEVEL%"
echo.
if "%NSB_RC%"=="0" (echo Ferdig. Si ferdig til Claude.) else (echo Stoppet. Se eval\results\loopvakt_v1\RUN.detail.log)
popd
pause
exit /b %NSB_RC%
