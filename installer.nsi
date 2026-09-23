; Build with build-installer.ps1. All integration belongs to the current user.
Unicode true
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "Sections.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "StrFunc.nsh"
${StrLoc}
${UnStrLoc}

!ifndef PRODUCT_NAME
  !define PRODUCT_NAME "Nearlock"
!endif
!ifndef OUTPUT_PATH
  !define OUTPUT_PATH "Nearlock-Setup.exe"
!endif
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define RUN_KEY "Software\Microsoft\Windows\CurrentVersion\Run"

Name "${PRODUCT_NAME}"
Caption "${PRODUCT_NAME} Setup"
OutFile "${OUTPUT_PATH}"
InstallDir "$LOCALAPPDATA\Programs\${PRODUCT_NAME}"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"
BrandingText "Nearlock - A little peace of mind."
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=1033 "ProductName" "${PRODUCT_NAME} Setup"
VIAddVersionKey /LANG=1033 "FileDescription" "Current-user setup for Nearlock"
VIAddVersionKey /LANG=1033 "FileVersion" "1.0.0"
VIAddVersionKey /LANG=1033 "ProductVersion" "1.0.0"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Nearlock"

!define MUI_ICON "assets\nearlock.ico"
!define MUI_UNICON "assets\nearlock.ico"
!define MUI_ABORTWARNING
!define MUI_BGCOLOR "FFFFFF"
!define MUI_TEXTCOLOR "172134"
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Setup will install Nearlock for your Windows account.$\r$\n$\r$\nQuit any running copy of Nearlock from its tray menu before continuing.$\r$\n$\r$\nYour Bluetooth preferences will be preserved. Administrator access and Python are not required."
!define MUI_FINISHPAGE_TITLE "Nearlock is ready"
!define MUI_FINISHPAGE_TEXT "Open Nearlock, choose your Bluetooth device, then enable protection.$\r$\n$\r$\nWindows Hello or your PIN is still required to unlock Windows."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Nearlock.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Nearlock"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Var StartupCommand

; Match Python's list2cmdline, which quotes an executable path only when needed.
!macro StartupCommandFunction PREFIX
Function ${PREFIX}MakeStartupCommand
  StrCpy $StartupCommand "$INSTDIR\Nearlock.exe"
  !if "${PREFIX}" == ""
    ${StrLoc} $0 "$StartupCommand" " " ">"
  !else
    ${UnStrLoc} $0 "$StartupCommand" " " ">"
  !endif
  ${If} $0 != ""
    StrCpy $StartupCommand '$\"$StartupCommand$\"'
  ${EndIf}
  StrCpy $StartupCommand "$StartupCommand --background"
FunctionEnd
!macroend
!insertmacro StartupCommandFunction ""
!insertmacro StartupCommandFunction "un."

; Do not kill the user's process or schedule changes for the next reboot.
!macro RequireClosedFunction PREFIX
Function ${PREFIX}RequireClosed
retry:
  IfFileExists "$INSTDIR\Nearlock.exe" 0 done
  ClearErrors
  FileOpen $0 "$INSTDIR\Nearlock.exe" a
  IfErrors in_use
  FileClose $0
  Goto done
in_use:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Quit Nearlock from its system-tray menu, then click Retry." /SD IDCANCEL IDRETRY retry
  SetErrorLevel 2
  Abort
done:
FunctionEnd
!macroend
!insertmacro RequireClosedFunction ""
!insertmacro RequireClosedFunction "un."

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Nearlock requires 64-bit Windows 11." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin11}
    MessageBox MB_OK|MB_ICONSTOP "Nearlock requires Windows 11 or later." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Section "Nearlock application (required)" AppFiles
  SectionIn RO
  Call RequireClosed
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ClearErrors
  File /r "dist\Nearlock\*.*"
  IfErrors 0 +3
    SetErrorLevel 1
    Abort "Nearlock could not be copied. Check that the destination is writable."
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "1.0.0"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Nearlock"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\Nearlock.exe,0"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "EstimatedSize" ${SIZE_KB}
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\Nearlock.exe"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ${PRODUCT_NAME}.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop shortcut" DesktopShortcut
  CreateShortcut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\Nearlock.exe"
SectionEnd

Section "Start Nearlock when I sign in" Startup
  Call MakeStartupCommand
  WriteRegStr HKCU "${RUN_KEY}" "${PRODUCT_NAME}" "$StartupCommand"
SectionEnd

Section -FinishIntegration
  IfErrors integration_failed
  ${IfNot} ${SectionIsSelected} ${Startup}
    ReadRegStr $0 HKCU "${RUN_KEY}" "${PRODUCT_NAME}"
    ${If} $0 != ""
      DeleteRegValue HKCU "${RUN_KEY}" "${PRODUCT_NAME}"
    ${Else}
      ClearErrors
    ${EndIf}
  ${EndIf}
  IfErrors integration_failed integration_done
integration_failed:
  SetErrorLevel 1
  Abort "Windows could not complete the current-user integration."
integration_done:
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${AppFiles} "The complete app and its runtime. Existing device preferences are kept."
  !insertmacro MUI_DESCRIPTION_TEXT ${DesktopShortcut} "Add a Nearlock shortcut to your desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${Startup} "Launch Nearlock quietly in your tray after you sign in to this Windows account."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  GetFullPathName $1 "$INSTDIR"
  GetFullPathName $2 "$0"
  ${If} $0 == ""
  ${OrIf} $1 != $2
    MessageBox MB_OK|MB_ICONSTOP "This uninstaller does not match the registered Nearlock installation." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  Call un.RequireClosed
FunctionEnd

Section "Uninstall"
  Call un.MakeStartupCommand
  ReadRegStr $0 HKCU "${RUN_KEY}" "${PRODUCT_NAME}"
  ${If} $0 == $StartupCommand
  ${OrIf} $0 == '$\"$INSTDIR\Nearlock.exe$\" --background'
    DeleteRegValue HKCU "${RUN_KEY}" "${PRODUCT_NAME}"
  ${EndIf}
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  ; Generated exact paths: never recursively delete a user-chosen folder.
  !include "${UNINSTALL_LIST}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  ; %LOCALAPPDATA%\Nearlock preferences and logs belong to the user and are retained.
SectionEnd
