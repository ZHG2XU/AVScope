Unicode true
Name "AVScope"
OutFile "G:\AVScope\dist\AVScope-Setup.exe"
InstallDir "G:\AVScopeInstalled\AVScope"
RequestExecutionLevel user

!define APP_NAME "AVScope"
!define APP_EXE "AVScope.exe"
!define SOURCE_DIR "G:\AVScope\dist\AVScopeQt"

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
