@echo off
rem Merker 200 segmenter fra Stortinget Speech Corpus med bokmal som fasit (noen minutter pa RTX 4080).
rem Resultat: build\ssc\trial (labels.jsonl, rejected.jsonl, summary.json)
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_ssc.ps1 -Mode Trial
set "NSB_FAIL=%ERRORLEVEL%"
popd
pause
exit /b %NSB_FAIL%
