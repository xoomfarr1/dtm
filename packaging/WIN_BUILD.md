# Windows build instructions for DTS-Monaco
# ============================================================================
# Last updated: 2026-10-18
# ============================================================================

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
# PyInstaller cannot cross-compile from Linux, so the Windows build must run
# on a Windows machine. This document explains two methods:
#
#   1. The simple method (build_windows.bat) — run a pre-built batch script
#   2. The manual method — follow these steps manually
#
# ---------------------------------------------------------------------------
# Method 1: The simple method (recommended)
# ---------------------------------------------------------------------------
# 1. Copy build_windows.bat to your Windows machine (e.g., C:\Users\test1\dtm)
# 2. Open a Command Prompt in that folder
# 3. Run: build_windows.bat
#
# The script will:
#   - Check Python is available
#   - Create a virtual environment (if needed)
#   - Install dependencies
#   - Build dtm.exe using PyInstaller
#   - Pause at the end so you can read the output
#
# ---------------------------------------------------------------------------
# Method 2: Manual build
# ---------------------------------------------------------------------------
# 1. On Windows, open a Command Prompt (cmd.exe)
# 2. Navigate to the DTS-Monaco folder:
#       cd C:\Users\test1\dtm
# 3. Create a virtual environment:
#       python -m venv venv
# 4. Activate it:
#       venv\Scripts\activate
# 5. Install dependencies:
#       pip install -e ".[gui,dev]"
#       pip install pyinstaller
# 6. Run PyInstaller:
#       pyinstaller --noconfirm --onefile --windowed --name dtm --collect-all dts_monaco --hidden-import dts_monaco.config --paths venv\Lib\site-packages src\dts_monaco\__main__.py
# 7. The output will be in build\exe\dtm\dtm.exe (one-folder) or build\dist\dtm.exe (one-file)
#
# ---------------------------------------------------------------------------
# Troubleshooting
# ---------------------------------------------------------------------------
# Error: "Python not found"
#   Install Python 3.10+ from https://python.org/downloads and check "Add to PATH"
#
# Error: "pip install -e" fails
#   Make sure you have an internet connection. The -e flag installs the package
#   in editable mode, which requires access to PyPI.
#
# Error: PyInstaller cannot find PySide6 plugins
#   Ensure you ran: pip install -e ".[gui,dev]" — this installs PySide6 and its dependencies.
#
# Error: The program can't start (missing DLL)
#   Install the Microsoft Visual C++ Redistributable from:
#   https://aka.ms/vs/17/release/vc_redist.x64.exe
#
# Error: Missing vehicle data folders
#   DTS-Monaco requires data folders for vehicle configuration. Copy them to:
#   C:\DTS_Monaco_Data\
#
# ---------------------------------------------------------------------------
# NSIS installer (optional)
# ---------------------------------------------------------------------------
# If you want to create a Windows installer, you need NSIS (Nullsoft
# Scriptable Install System). Download it from https://nsis.sourceforge.io/
#
# 1. Install NSIS (default settings)
# 2. Open the installer script: packaging/installer/dts-monaco.nsi
# 3. Compile it from the NSIS terminal:
#       cd C:\Program Files\NSIS\Bin
#       makensis.exe dts-monaco.nsi
# 4. The installer (dts-monaco_installer.exe) will be in the output directory
#
# See packaging/installer/notes.md for a complete guide.
# ============================================================================
