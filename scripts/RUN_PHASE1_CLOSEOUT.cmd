@echo off
rem Lukker de malbare punktene i fase 1 (ca. 1,5 time pa RTX 4080 + CPU):
rem   1. Nynorsk dekodet som nynorsk: NB Samtale med malform fra manifestet (GPU)
rem   2. Minnebruk pa GPU: NPSC test, 100 setninger, alle fem modeller
rem   3. CPU-ytelse og minne: NPSC test, 100 setninger, int8, fire modeller
rem Resultater: eval\results\maalform, eval\results\gpu_minne, eval\results\cpu
rem Samlet tabell: eval\results\BENCHMARK.md
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "NSB_PS=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined NSB_PS set "NSB_PS=powershell"
echo Bruker %NSB_PS% i %CD%
set "NSB_FAIL=0"

echo.
echo [1/3] Nynorsk som nynorsk (GPU)
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -OutPrefix maalform -TestsetSuffix _maalform -LanguageFromMeta -Testsets nb_samtale_test -Models nb-whisper-large-distil-turbo-beta,nb-whisper-large,whisper-large-v3
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"

echo.
echo [2/3] Minnebruk pa GPU
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix gpu_minne -TestsetSuffix _100 -Limit 100 -Testsets npsc_test_20170207
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"

echo.
echo [3/3] CPU int8
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_benchmark.ps1 -SkipSetup -OutPrefix cpu -TestsetSuffix _100 -Limit 100 -Device cpu -ComputeType int8 -Testsets npsc_test_20170207 -Models nb-whisper-large-distil-turbo-beta,nb-whisper-small,nb-whisper-large,whisper-large-v3
if not "%ERRORLEVEL%"=="0" set "NSB_FAIL=1"

echo.
if "%NSB_FAIL%"=="0" (echo Ferdig. Se eval\results\BENCHMARK.md) else (echo Minst ett steg feilet. Se RUN.log i eval\results\maalform, gpu_minne og cpu)
popd
pause
exit /b %NSB_FAIL%
