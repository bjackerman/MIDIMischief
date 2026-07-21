; Build with: makensis /DVERSION=0.1.0 /DDIST_DIR=dist MIDIMischief.nsi
;
; Note: the .nsi paths are written with single backslashes here. NSIS
; treats ${VAR}\\file as "VAR with trailing backslash" + "file", which
; makes the path a UNC path on Windows (e.g. \\server\share). The fix
; used to be: use forward slashes everywhere. The cleaner fix used
; here: define DIST_DIR with a trailing backslash, and reference
; ${DIST_DIR}file without an extra separator.
Unicode True
!include "MUI2.nsh"

!ifndef VERSION
!define VERSION "0.1.0"
!endif
!ifndef DIST_DIR
!define DIST_DIR "dist"
!endif
!ifndef DIST_DIR_SLASH
!define DIST_DIR_SLASH "${DIST_DIR}\"
!endif

Name "MIDIMischief"
OutFile "${DIST_DIR_SLASH}MIDIMischief-${VERSION}-windows-x64-setup.exe"
InstallDir "$PROGRAMFILES64\MIDIMischief"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "MIDIMischief" SecMain
  SetOutPath "$INSTDIR"
  File "${DIST_DIR_SLASH}MIDIMischief.exe"
  CreateDirectory "$SMPROGRAMS\MIDIMischief"
  CreateShortcut "$SMPROGRAMS\MIDIMischief\MIDIMischief.lnk" "$INSTDIR\MIDIMischief.exe" "gui"
  CreateShortcut "$DESKTOP\MIDIMischief.lnk" "$INSTDIR\MIDIMischief.exe" "gui"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIDIMischief" "DisplayName" "MIDIMischief"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIDIMischief" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIDIMischief" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\MIDIMischief.lnk"
  Delete "$SMPROGRAMS\MIDIMischief\MIDIMischief.lnk"
  RMDir "$SMPROGRAMS\MIDIMischief"
  Delete "$INSTDIR\MIDIMischief.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIDIMischief"
SectionEnd
