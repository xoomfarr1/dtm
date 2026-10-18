# DTS-Monaco NSIS Installer — Build Notes
# ============================================================================
# Purpose: Step-by-step guide to compile the NSIS installer for DTS-Monaco.
#
# Prerequisites:
#   1. NSIS (Nullsoft Scriptable Install System) installed on your Windows
#      machine. Download from: https://nsis.sourceforge.io/
#   2. Build the DTS-Monaco executable with PyInstaller first.
#      See WIN_BUILD.md for build instructions.
#
# ---------------------------------------------------------------------------
# Step 1: Build the executable
# ---------------------------------------------------------------------------
# On your Windows machine:
#   1. Open Command Prompt in the DTS-Monaco folder
#   2. Run: build_windows.bat
#   3. The executable will be at: build\exe\dtm\dtm.exe
#
# ---------------------------------------------------------------------------
# Step 2: Prepare the installer source
# ---------------------------------------------------------------------------
; The NSIS script expects the following structure:
;
;   DTS-Monaco/
;     dist\
;       dtm\
;         dtm.exe          (the built executable)
;     README.md
;     LICENSE
;     packaging\docs\    (documentation files)
;     installer\
;       dts-monaco.nsi   (installer script)
;       banner.bmp       (installer banner image)
;       uninstaller.exe  (uninstaller stub)
;
; You can copy the built executable and files to the installer source
; folder before compiling.
;
; ---------------------------------------------------------------------------
; Step 3: Compile the installer
; ---------------------------------------------------------------------------
; The easiest way to compile NSIS scripts is to use the NSIS Qt GUI:
;   1. Open NSISQt.exe
;   2. Open dts-monaco.nsi
;   3. Click "Compile"
;   4. The installer (dts-monaco_installer.exe) will be created in the output
;      directory
;
; Alternatively, use the command line:
;   cd "C:\Program Files\NSIS\Bin"
;   makensis.exe dts-monaco.nsi
;
; ---------------------------------------------------------------------------
; Step 4: Test the installer
; ---------------------------------------------------------------------------
; 1. Run the installer on a clean Windows machine (or a virtual machine)
; 2. Follow the installation prompts
; 3. Launch DTS-Monaco from the Start Menu
; 4. Verify the application works as expected
; 5. Test the uninstaller:
;      Start Menu > DTS-Monaco > Uninstall DTS-Monaco
;
; ---------------------------------------------------------------------------
; Common issues
; ---------------------------------------------------------------------------
; Error: "ERROR: cannot open file: dist\dtm\dtm.exe"
;   Solution: Build the executable first, then compile the installer.
;
; Error: "missing banner.bmp"
;   Solution: Create a simple BMP image (320x100) for the installer banner,
;   or remove the banner.bmp references from the NSIS script.
;
; Error: "uninstaller.exe not found"
;   Solution: Build the installer with the uninstaller stub. The uninstaller
;   is generated automatically by NSIS when you use the "WriteUninstaller"
;   command.
;
; ---------------------------------------------------------------------------
; Optional: Create a portable version
; ---------------------------------------------------------------------------
; If you want a portable version (no installer), just copy the dtm.exe and
; any required data folders to a USB drive or zip them up. The PyInstaller
; one-folder build (build\exe\dtm\) is already portable — just copy the
; folder to the target machine and run dtm.exe.
;
; ---------------------------------------------------------------------------
; Notes
; ---------------------------------------------------------------------------
; This installer is a starting point. For production, you may want to:
;   - Add a custom uninstaller UI
;   - Include a license agreement
;   - Add a checkbox to create a desktop shortcut
;   - Include a version-check feature
;   - Add support for automatic updates
;
; The mbtools-open project has a similar installer script for reference.
; ============================================================================
