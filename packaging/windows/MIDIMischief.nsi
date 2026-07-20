; Build with: makensis /DVERSION=0.1.0 /DDIST_DIR=dist MIDIMischief.nsi
Unicode True
!include "MUI2.nsh"

!ifndef VERSION
!define VERSION "0.1.0"
!endif
!ifndef DIST_DIR
!define DIST_DIR "dist"
!endif

Name "MIDIMischief"
OutFile "${DIST_DIR}\\MIDIMischief-${VERSION}-windows-x64-setup.exe"
InstallDir "$PROGRAMFILES64\\MIDIMischief"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "MIDIMischief" SecMain
  SetOutPath "$INSTDIR"
  File "${DIST_DIR}\\MIDIMischief.exe"
  CreateDirectory "$SMPROGRAMS\\MIDIMischief"
  CreateShortcut "$SMPROGRAMS\\MIDIMischief\\MIDIMischief.lnk" "$INSTDIR\\MIDIMischief.exe" "gui"
  CreateShortcut "$DESKTOP\\MIDIMischief.lnk" "$INSTDIR\\MIDIMischief.exe" "gui"
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\MIDIMischief" "DisplayName" "MIDIMischief"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\MIDIMischief" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\MIDIMischief" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\\MIDIMischief.lnk"
  Delete "$SMPROGRAMS\\MIDIMischief\\MIDIMischief.lnk"
  RMDir "$SMPROGRAMS\\MIDIMischief"
  Delete "$INSTDIR\\MIDIMischief.exe"
  Delete "$INSTDIR\\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\MIDIMischief"
SectionEnd
