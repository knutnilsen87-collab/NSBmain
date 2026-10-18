@echo off
rem Maler stromming i nsb-engine (ca. 30-45 minutter pa RTX 4080 + CPU):
rem   ventetid fra ord til tekst, hvor ofte teksten endres, WER strom mot hel lydfil,
rem   og om usikre ord faktisk er feil oftere.
rem Resultater: eval\results\streaming
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_streaming.ps1 %*
set "NSB_RC=%ERRORLEVEL%"
echo.
if "%NSB_RC%"=="0" (echo Ferdig. Se eval\results\streaming\RUN.log) else (echo Minst ett steg feilet. Se eval\results\streaming\RUN.detail.log)
popd
pause
exit /b %NSB_RC%
