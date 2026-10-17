@echo off
rem Maler egne opptak med tre modeller, med og uten VAD.
rem Kjor etter RECORD_DICTATION.cmd og eventuelt RECORD_INTERVIEW.cmd (avhor ma vaere verifisert).
rem Resultater: eval\results\opptak. Samlet tabell: eval\results\BENCHMARK.md
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
set "NSB_FAIL=0"
echo [1/2] Juridisk diktat
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -OutPrefix opptak -Testsets legal_dictation_v1 -Models nb-whisper-large-distil-turbo-beta,nb-whisper-large,whisper-large-v3
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix opptak -TestsetSuffix _vad -Vad -Testsets legal_dictation_v1 -Models nb-whisper-large-distil-turbo-beta
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"
echo [2/2] Simulerte avhor (bare verifiserte)
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix opptak -Testsets simulated_interview_v1 -Models nb-whisper-large-distil-turbo-beta,nb-whisper-large,whisper-large-v3
if not "%ERRORLEVEL%"=="0" echo Ingen verifiserte avhor ennaa, eller malingen feilet. Se eval\results\opptak\RUN.log
echo.
if "%NSB_FAIL%"=="0" (echo Ferdig. Se eval\results\BENCHMARK.md) else (echo Diktatmalingen feilet. Se eval\results\opptak\RUN.log)
popd
pause
exit /b %NSB_FAIL%
