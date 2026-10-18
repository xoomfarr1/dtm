#!/bin/bash
# ============================================================================
# DTS-Monaco — Standalone Windows desktop executable recipe
# ============================================================================
# Purpose: Build a standalone Windows executable (dtm.exe) from this Linux
# source tree. PyInstaller cannot cross-compile, so this script prepares the
# environment and invokes PyInstaller on Windows, OR runs on Linux with
# Wine to produce a Windows self-contained executable.
#
# Usage:
#   Option A — On Windows (recommended):
#     1. Open this folder in a terminal
#     2. Run: make_windows_exe.bat
#
#   Option B — From Linux (Wine required):
#     1. Install Wine on Linux
#     2. Run: bash make_windows_exe.sh
#
# The output (dtm.exe) is placed in build/console/ (one-folder) or
# build/exe/ (one-file), depending on the script configuration.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit these to suit your build machine
# ---------------------------------------------------------------------------
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
VENV_NAME="${VENV_NAME:-venv}"
BUILD_DIR="build"
CONSOLE_DIR="${BUILD_DIR}/console"
EXE_DIR="${BUILD_DIR}/exe"
SPEC_FILE="packaging/dts_monaco_windows.spec"
ICON_FILE="src/dts_monaco/gui/icon.png"

# ---------------------------------------------------------------------------
# Helper: print usage
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 [options]"
  echo "  --help               Show this help message"
  echo "  --onefile            Build one-file executable (slower startup, larger size)"
  echo "  --onefolder          Build one-folder bundle (faster startup, smaller size)"
  echo "  --skip-pip           Skip installing Python dependencies (assumes they are installed)"
  exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
ONE_FILE=false
ONE_FOLDER=true
SKIP_PIP=false

for arg in "$@"; do
  case "$arg" in
    --onefile) ONE_FILE=true; ONE_FOLDER=false ;;
    --onefolder) ONE_FILE=false; ONE_FOLDER=true ;;
    --skip-pip) SKIP_PIP=true ;;
    --help) usage ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

echo "=== DTS-Monaco Windows Build ==="
echo "Build mode: $([ "$ONE_FILE" = true ] && echo 'one-file' || echo 'one-folder')"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Check prerequisites
# ---------------------------------------------------------------------------
echo "[1/5] Checking prerequisites..."
if ! command -v python3 &> /dev/null; then
  echo "ERROR: python3 not found. Install Python 3.10+ and ensure it is in PATH."
  exit 1
fi

PYTHON_BIN=$(command -v python3)
echo "Found Python: $PYTHON_BIN"

# ---------------------------------------------------------------------------
# Step 2: Create virtual environment
# ---------------------------------------------------------------------------
echo "[2/5] Creating virtual environment..."
if [ -d "$VENV_NAME" ]; then
  echo "Virtual environment already exists. Re-using it."
else
  $PYTHON_BIN -m venv "$VENV_NAME"
fi

source "$VENV_NAME/bin/activate"

# ---------------------------------------------------------------------------
# Step 3: Install dependencies
# ---------------------------------------------------------------------------
if [ "$SKIP_PIP" = false ]; then
  echo "[3/5] Installing Python dependencies..."
  pip install --upgrade pip
  pip install -e ".[gui,dev]"
  pip install pyinstaller
else
  echo "[3/5] Skipping pip install (--skip-pip)."
fi

# ---------------------------------------------------------------------------
# Step 4: Build the executable
# ---------------------------------------------------------------------------
echo "[4/5] Building executable..."

# Ensure build directories exist
mkdir -p "$CONSOLE_DIR"
mkdir -p "$EXE_DIR"

# PyInstaller command
PYINSTALLER_ARGS=(
  --noconfirm
  --clean
  --distpath "$EXE_DIR"
  --workpath "$BUILD_DIR/work"
  --specpath "$BUILD_DIR"
  --name dtm
  --collect-all dts_monaco
  --hidden-import dts_monaco.config
  --hidden-import dts_monaco.protocols.can
  --hidden-import dts_monaco.protocols.iso_tp
  --hidden-import dts_monaco.protocols.uds
  --hidden-import dts_monaco.hardware.pt3gvci
  --hidden-import dts_monaco.hardware.usb_dongle
  --hidden-import dts_monaco.logic.engine
  --hidden-import dts_monaco.logic.variant_coding
  --hidden-import dts_monaco.logic.flashing
  --hidden-import dts_monaco.logic.logger
  --hidden-import dts_monaco.data.smr_d
  --hidden-import dts_monaco.explain
  --hidden-import can
  --hidden-import can.interfaces
  --hidden-import can.interfaces.base
  --hidden-import py_uds
  --hidden-import pydantic
  --hidden-import pydantic_core
  --paths venv/Lib/site-packages
  src/dts_monaco/__main__.py
)

# Remove console flag for one-file, keep it for one-folder
if [ "$ONE_FILE" = true ]; then
  PYINSTALLER_ARGS+=(--onefile)
else
  PYINSTALLER_ARGS+=(--onedir)
fi

if [ -f "$ICON_FILE" ]; then
  PYINSTALLER_ARGS+=(--icon "$ICON_FILE")
fi

# Run PyInstaller
python -m PyInstaller "${PYINSTALLER_ARGS[@]}"

# ---------------------------------------------------------------------------
# Step 5: Report result
# ---------------------------------------------------------------------------
echo "[5/5] Build complete!"
echo ""
echo "Output location:"
if [ "$ONE_FILE" = true ]; then
  echo "  One-file: $EXE_DIR/dts_monaco.spec"
  echo "  Executable: $EXE_DIR/dist/dts_monaco.exe"
else
  echo "  Bundle: $EXE_DIR/dist/dtm/"
  echo "  Executable: $EXE_DIR/dist/dtm/dtm.exe"
fi
echo ""
echo "Next steps:"
echo "  1. Test dts_monaco.exe on a Windows machine (not this one)"
echo "  2. Copy any vehicle data folders to C:\\DTS_Monaco_Data\\"
echo "  3. Distribute the folder or create a Windows installer (NSIS)"
echo ""
echo "Done."
