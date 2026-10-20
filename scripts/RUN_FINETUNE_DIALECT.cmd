@echo off
rem Forste treningsforsok: distil-turbo pa dialekt og nynorsk. Tar flere timer pa RTX 4080.
rem Kan avbrytes (lukk vinduet) og startes igjen; fortsetter fra siste checkpoint.
rem Fremdrift: runs\dialekt_v1\RUN.log og runs\dialekt_v1\state.json
pushd "%~dp0"
cd ..
set "NSB_PS="
where pwsh >NUL 2>NUL && set "NSB_PS=pwsh"
if not defined NSB_PS set "NSB_PS=powershell"
"%NSB_PS%" -NoProfile -ExecutionPolicy Bypass -File scripts\run_finetune_dialect.ps1 %*
set "NSB_RC=%ERRORLEVEL%"
echo.
if "%NSB_RC%"=="0" (echo Ferdig. Se runs\dialekt_v1\RUN.log) else (echo Stoppet. Se runs\dialekt_v1\RUN.detail.log. Kjor igjen for a fortsette.)
popd
pause
exit /b %NSB_RC%
