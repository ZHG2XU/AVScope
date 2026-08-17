@echo off
for %%I in ("%~dp0..") do set "AVSCOPE_ROOT=%%~fI"
if not defined AVSCOPE_PYTHON set "AVSCOPE_PYTHON=python"
set "TEMP=%AVSCOPE_ROOT%\tmp"
set "TMP=%AVSCOPE_ROOT%\tmp"
if not exist "%TEMP%" mkdir "%TEMP%"

if exist "%AVSCOPE_ROOT%\dist\AVScopeQt\AVScope.exe" (
  start "" "%AVSCOPE_ROOT%\dist\AVScopeQt\AVScope.exe" %*
) else if exist "%AVSCOPE_ROOT%\build\qt6\bin\AVScope.exe" (
  start "" "%AVSCOPE_ROOT%\build\qt6\bin\AVScope.exe" %*
) else (
  start "" "%AVSCOPE_PYTHON%" "%AVSCOPE_ROOT%\run_avscope.py" %*
)
