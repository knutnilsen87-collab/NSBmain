@echo off
rem Viser innholdet i Stortinget Speech Corpus: felt, timer, talere og malform.
rem Laster ingen modell og tar noen sekunder. Resultat: build\ssc\INSPECT.json
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_ssc.ps1 -Mode Inspect
set "NSB_FAIL=%ERRORLEVEL%"
popd
pause
exit /b %NSB_FAIL%
