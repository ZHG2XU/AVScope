Unicode true
Name "AVScope"
OutFile "..\dist\AVScope-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\AVScope"
RequestExecutionLevel user
Icon "..\qt\resources\avscope.ico"
UninstallIcon "..\qt\resources\avscope.ico"

!define APP_NAME "AVScope"
!define APP_EXE "AVScope.exe"
!define SOURCE_DIR "..\dist\AVScopeQt"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
SectionEnd
