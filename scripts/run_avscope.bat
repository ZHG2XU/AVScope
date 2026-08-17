@echo off
for %%I in ("%~dp0..") do set "AVSCOPE_ROOT=%%~fI"
set "PYTHONPATH=%AVSCOPE_ROOT%"
set "TEMP=%AVSCOPE_ROOT%\tmp"
set "TMP=%AVSCOPE_ROOT%\tmp"
call "%~dp0run_avscope_qt.bat" %*
