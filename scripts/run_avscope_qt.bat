@echo off
set "AVSCOPE_ROOT=G:\AVScope"
set "AVSCOPE_PYTHON=E:\DevelopmentEnvironment\python\python.exe"
set "TEMP=G:\AVScope\tmp"
set "TMP=G:\AVScope\tmp"
set "PATH=E:\QT\6.9.0\mingw_64\bin;E:\QT\Tools\mingw1310_64\bin;%PATH%"

if exist "G:\AVScope\dist\AVScopeQt\AVScope.exe" (
  start "" "G:\AVScope\dist\AVScopeQt\AVScope.exe" %*
) else (
  start "" "G:\AVScope\build\qt6\bin\AVScope.exe" %*
)
