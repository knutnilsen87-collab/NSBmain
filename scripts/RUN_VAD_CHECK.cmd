@echo off
rem Maler stemmeaktivitetsdeteksjon (VAD), ca. 25 minutter pa RTX 4080:
rem   1. Stillhet med VAD, alle fem modeller (kravet er 0 av 12)
rem   2. NPSC test, 100 setninger, med VAD: koster VAD ord i tale?
rem   3. NB Samtale med VAD, distil-turbo og NB-Whisper large: samtale har mange pauser
rem Resultater: eval\results\vad
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
set "NSB_FAIL=0"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -OutPrefix vad -TestsetSuffix _vad -Vad -Testsets silence_v1
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix vad -TestsetSuffix _100_vad -Limit 100 -Vad -Testsets npsc_test_20170207 -Models nb-whisper-large-distil-turbo-beta,nb-whisper-large,whisper-large-v3
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix vad -TestsetSuffix _vad -Vad -Testsets nb_samtale_test -Models nb-whisper-large-distil-turbo-beta,nb-whisper-large
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"
echo.
if "%NSB_FAIL%"=="0" (echo Ferdig. Se eval\results\BENCHMARK.md) else (echo Minst ett steg feilet. Se eval\results\vad\RUN.log)
popd
pause
exit /b %NSB_FAIL%
