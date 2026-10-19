; ============================================================================
; DTS-Monaco Windows Installer (NSIS)
; ============================================================================
; Purpose: Create a professional Windows installer for DTS-Monaco.
; This installer packages the standalone dtm.exe executable and required
; data folders into a single .exe file that users can run on any Windows PC.
;
; Usage:
;   1. Copy this entire 'installer_source' folder to your Windows machine
;   2. Open Command Prompt in that folder
;   3. Run: makensis.exe dts-monaco.nsi
;   4. The installer will be in the same folder
; ============================================================================

; ---------------------------------------------------------------------------
; Installer metadata
; ---------------------------------------------------------------------------
Name "DTS-Monaco"
OutFile "dts-monaco_installer.exe"
Unicode true
InstallDir "$PROGRAMFILES\DTS-Monaco"
InstallDirRegKey HKCU "Software\DTS-Monaco" "InstallDir"
RequestExecutionLevel admin

; ---------------------------------------------------------------------------
; Version info
; ---------------------------------------------------------------------------
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "DTS-Monaco"
VIAddVersionKey "CompanyName" "DTS-Monaco Contributors"
VIAddVersionKey "FileDescription" "DTS-Monaco - Open-source vehicle ECU diagnostics"
VIAddVersionKey "ProductVersion" "1.0.0"
VIAddVersionKey "LegalCopyright" "Copyright (C) 2026 DTS-Monaco Contributors"
VIAddVersionKey "Comments" "Open-source replacement for Softing DTS Monaco"

; ---------------------------------------------------------------------------
; Installer sections
; ---------------------------------------------------------------------------
Section "Install DTS-Monaco"
  ; Create the uninstall registry key
  WriteRegStr HKCU "Software\DTS-Monaco" "InstallDir" "$INSTDIR"

  ; Copy the executable and required files
  SetOutPath "$INSTDIR"
  File /r "installer_source\dtm\**" ; Adjust path based on one-folder or one-file build
  File "README.md"
  File "LICENSE"

  ; Create desktop shortcut
  CreateShortcut "$DESKTOP\DTS-Monaco.lnk" "$INSTDIR\dtm.exe"
  SetShellVarContext current
  CreateShortcut "$SMPROGRAMS\DTS-Monaco\DTS-Monaco.lnk" "$INSTDIR\dtm.exe"
  CreateShortcut "$SMPROGRAMS\DTS-Monaco\Uninstall DTS-Monaco.lnk" "$INSTDIR\Uninstall.exe"
  SetShellVarContext all

  ; Write uninstaller script
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Save install location in registry for repair
  WriteRegStr HKCU "Software\DTS-Monaco" "Version" "1.0.0"

  ; Show a message box on success
  DetailPrint "DTS-Monaco installed to: $INSTDIR"
  MessageBox MB_OK "DTS-Monaco has been installed successfully."
SectionEnd

; ---------------------------------------------------------------------------
; Uninstaller section
; ---------------------------------------------------------------------------
Section "Uninstall"
  ; Remove the executable and files
  RmDir /r "$INSTDIR"

  ; Remove desktop and start menu shortcuts
  Delete "$DESKTOP\DTS-Monaco.lnk"
  RMDir "$SMPROGRAMS\DTS-Monaco"

  ; Remove registry keys
  DeleteRegKey HKCU "Software\DTS-Monaco"

  ; Show a message box on success
  DetailPrint "DTS-Monaco has been uninstalled."
  MessageBox MB_OK "DTS-Monaco has been uninstalled successfully."
SectionEnd

; ---------------------------------------------------------------------------
; Installer finalization
; ---------------------------------------------------------------------------
; Create uninstaller stub
Section "Uninstaller stub"
  ; This section is called by the uninstaller
  SetOutPath "$INSTDIR"
  File /r "Uninstall.exe"
SectionEnd

; ---------------------------------------------------------------------------
; Before install - check admin rights
; ---------------------------------------------------------------------------
Function .onInit
  ; Check for admin privileges
  Push 0
  System::Call "shell32::IsUserAnAdmin(i 0, *r0)"
  Exch $0
  StrCmp $0 1 0 + 2 + 1
    MessageBox MB_ICONEXCLAMATION | MB_OK "This installer requires administrator privileges."
    Abort
  StrCmp $0 1 0 + 1
    MessageBox MB_ICONEXCLAMATION | MB_OK "This installer requires administrator privileges."
    Abort
  Pop
FunctionEnd
