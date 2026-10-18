@echo off
REM ============================================================================
REM  DTS-Monaco — PyInstaller Windows build script
REM  Run this on Windows (not from Linux — PyInstaller never cross-compiles)
REM ============================================================================

setlocal

echo.
echo ============================================
echo  DTS-Monaco PyInstaller build
echo ============================================
echo.

REM Check Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    echo and ensure "python" is in your PATH.
    pause
    exit /b 1
)

REM Check we're on Windows
if not "%OS%" == "Windows_NT" (
    echo [ERROR] This script must run on Windows (PyInstaller cannot cross-compile).
    pause
    exit /b 1
)

echo [1/4] Checking virtual environment...
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
)

echo [2/4] Installing dependencies...
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -e ".[gui]"
venv\Scripts\python -m pip install pyinstaller

echo [3/4] Building executable...
venv\Scripts\pyinstaller ^
    --noconfirm --onefile --windowed ^
    --name dtm ^
    --collect-all dts_monaco ^
    --hidden-import dts_monaco.config ^
    --paths venv\Lib\site-packages ^
    src\dts_monaco\__main__.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo [4/4] Build complete!
echo.
echo Output directory: dist\dtm\
echo.
echo Next steps:
echo   1. Test dtm.exe on a Windows machine (not this one)
echo   2. Copy any vehicle data folders to C:\DTS_Monaco_Data\
echo   3. Distribute the folder or create a Windows installer
echo.
pause
