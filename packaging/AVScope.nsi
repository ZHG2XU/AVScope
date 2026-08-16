Unicode true
; NSIS MUI uses a fixed dialog layout. Let Windows scale the complete window so
; fonts, controls, and the branded bitmap stay aligned at 125%/150% DPI.
ManifestDPIAware false
!ifdef AVSCOPE_INSTALLER_PREVIEW
RequestExecutionLevel user
SetCompress off
!else
RequestExecutionLevel admin
SetCompressor /SOLID lzma
SetCompressorDictSize 32
!endif
CRCCheck on

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"
!include "WinVer.nsh"
!include "x64.nsh"

!define APP_NAME "AVScope"
!define APP_VERSION "0.2.0"
!define APP_PUBLISHER "AVScope"
!define APP_EXE "AVScope.exe"
!define APP_REG_KEY "Software\AVScope"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AVScope"
!define SOURCE_DIR "${__FILEDIR__}\..\dist\AVScopeQt"

Name "${APP_NAME} ${APP_VERSION}"
Caption "${APP_NAME} 安装向导"
!ifdef AVSCOPE_INSTALLER_PREVIEW
OutFile "${__FILEDIR__}\..\tmp\AVScope-Installer-Preview.exe"
!else
OutFile "${__FILEDIR__}\..\dist\AVScope-Setup.exe"
!endif
InstallDir "$PROGRAMFILES64\AVScope"
InstallDirRegKey HKLM "${APP_REG_KEY}" "InstallDir"
Icon "${__FILEDIR__}\..\qt\resources\avscope.ico"
UninstallIcon "${__FILEDIR__}\..\qt\resources\avscope.ico"
BrandingText "AVScope · Media Intelligence"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "0.2.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "AVScope"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "FileDescription" "AVScope 音视频工程分析工具安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright © 2026 AVScope"

!define MUI_ICON "${__FILEDIR__}\..\qt\resources\avscope.ico"
!define MUI_UNICON "${__FILEDIR__}\..\qt\resources\avscope.ico"
!define MUI_FONT "Microsoft YaHei UI"
!define MUI_FONTSIZE 9
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "确定要退出 AVScope 安装向导吗？"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${__FILEDIR__}\assets\installer-header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "${__FILEDIR__}\assets\installer-header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${__FILEDIR__}\assets\installer-welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${__FILEDIR__}\assets\installer-welcome.bmp"
!define MUI_WELCOMEPAGE_TITLE "欢迎使用 AVScope"
!define MUI_WELCOMEPAGE_TEXT "洞察每一帧、每一个包。$\r$\n$\r$\nAVScope 是面向音视频工程排障的专业分析工作台。$\r$\n$\r$\n安装程序将引导你完成部署。"
!define MUI_DIRECTORYPAGE_TEXT_TOP "选择 AVScope 的安装位置。建议保留默认目录，便于统一管理应用和后续更新。"
!define MUI_FINISHPAGE_TITLE "AVScope 已准备就绪"
!define MUI_FINISHPAGE_TEXT "安装已完成。现在可以开始分析媒体文件、码流与网络抓包。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 AVScope"
!define MUI_FINISHPAGE_LINK "访问 AVScope 项目主页"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/ZHG2XU/AVScope"
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_UNFINISHPAGE_NOAUTOCLOSE

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom OptionsPageCreate OptionsPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

Var OptionsDialog
Var DesktopShortcutCheckbox
Var StartMenuShortcutCheckbox
Var DesktopShortcutState
Var StartMenuShortcutState

Function .onInit
  SetRegView 64
  SetShellVarContext all
  StrCpy $DesktopShortcutState ${BST_CHECKED}
  StrCpy $StartMenuShortcutState ${BST_CHECKED}

  ${IfNot} ${RunningX64}
    StrCpy $INSTDIR "$PROGRAMFILES\AVScope"
    SetRegView 32
  ${EndIf}
FunctionEnd

Function OptionsPageCreate
  !insertmacro MUI_HEADER_TEXT "打造你的 AVScope 工作台" "选择安装完成后需要创建的快捷入口"

  nsDialogs::Create 1018
  Pop $OptionsDialog
  ${If} $OptionsDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 2u 100% 20u "快速访问"
  Pop $0
  CreateFont $1 "Microsoft YaHei UI" 11 600
  SendMessage $0 ${WM_SETFONT} $1 1

  ${NSD_CreateLabel} 0 25u 100% 24u "为常用入口创建快捷方式。你可以稍后手动删除，不会影响 AVScope 本体。"
  Pop $0

  ${NSD_CreateCheckbox} 0 61u 100% 16u "在桌面创建 AVScope 快捷方式"
  Pop $DesktopShortcutCheckbox
  ${NSD_SetState} $DesktopShortcutCheckbox $DesktopShortcutState

  ${NSD_CreateCheckbox} 0 86u 100% 16u "在开始菜单创建 AVScope 快捷方式"
  Pop $StartMenuShortcutCheckbox
  ${NSD_SetState} $StartMenuShortcutCheckbox $StartMenuShortcutState

  ${NSD_CreateLabel} 0 124u 100% 36u "安装范围：此计算机上的所有用户$\r$\n默认位置：$INSTDIR"
  Pop $0
  SetCtlColors $0 0x5B6472 transparent

  nsDialogs::Show
FunctionEnd

Function OptionsPageLeave
  ${NSD_GetState} $DesktopShortcutCheckbox $DesktopShortcutState
  ${NSD_GetState} $StartMenuShortcutCheckbox $StartMenuShortcutState
FunctionEnd

Section "AVScope" SecMain
  SetRegView 64
  ${IfNot} ${RunningX64}
    SetRegView 32
  ${EndIf}
  SetShellVarContext all
  SetOverwrite on
  SetOutPath "$INSTDIR"
!ifdef AVSCOPE_INSTALLER_PREVIEW
  File /oname=AVScope.exe "${SOURCE_DIR}\AVScope.exe"
!else
  File /r "${SOURCE_DIR}\*.*"
!endif

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "${APP_REG_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayName" "AVScope"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoRepair" 1

  ${If} $DesktopShortcutState == ${BST_CHECKED}
    CreateShortCut "$DESKTOP\AVScope.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  ${EndIf}

  ${If} $StartMenuShortcutState == ${BST_CHECKED}
    CreateDirectory "$SMPROGRAMS\AVScope"
    CreateShortCut "$SMPROGRAMS\AVScope\AVScope.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortCut "$SMPROGRAMS\AVScope\卸载 AVScope.lnk" "$INSTDIR\Uninstall.exe"
  ${EndIf}
SectionEnd

Function un.onInit
  SetRegView 64
  SetShellVarContext all
  ${IfNot} ${RunningX64}
    SetRegView 32
  ${EndIf}
FunctionEnd

Section "Uninstall"
  SetRegView 64
  ${IfNot} ${RunningX64}
    SetRegView 32
  ${EndIf}
  SetShellVarContext all

  Delete "$DESKTOP\AVScope.lnk"
  Delete "$SMPROGRAMS\AVScope\AVScope.lnk"
  Delete "$SMPROGRAMS\AVScope\卸载 AVScope.lnk"
  RMDir "$SMPROGRAMS\AVScope"

  DeleteRegKey HKLM "${APP_UNINSTALL_KEY}"
  DeleteRegKey HKLM "${APP_REG_KEY}"

  RMDir /r "$INSTDIR"
SectionEnd
