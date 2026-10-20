# Building DTS-Monaco for Windows
===============================================================================

PyInstaller can't cross-compile, so building the Windows executable has to run
on a Windows machine. This document covers two ways to get from source to a
working `dtm.exe`:

1. **The simple way** — `build_windows.bat`. Double-click it and let the script
   do the heavy lifting.
2. **The manual way** — follow the steps below if you want to see exactly what
   the batch script is doing.

## Method 1: The simple way (recommended)

1. Copy `build_windows.bat` to your Windows machine (e.g. `C:\Users\test1\dtm`).
2. Open a Command Prompt in that folder.
3. Run: `build_windows.bat`

The script will:

- Check Python is available (3.10+).
- Create a virtual environment if you don't have one.
- Install the dependencies.
- Build `dtm.exe` with PyInstaller.
- Pause at the end so you can read the output.

## Method 2: Manual build

1. On Windows, open a Command Prompt (cmd.exe) and navigate to the DTS-Monaco
   folder:
   ```cmd
   cd C:\Users\test1\dtm
   ```
2. Create a virtual environment and activate it:
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies and PyInstaller:
   ```cmd
   pip install -e ".[gui,dev]"
   pip install pyinstaller
   ```
4. Run PyInstaller:
   ```cmd
   pyinstaller --noconfirm --onefile --windowed --name dtm --collect-all dts_monaco --hidden-import dts_monaco.config --paths venv\Lib\site-packages src\dts_monaco\__main__.py
   ```
5. The output will be in `build\exe\dtm\dtm.exe` (one-folder) or
   `build\dist\dtm.exe` (one-file).

## Troubleshooting

### Python not found
Install Python 3.10+ from https://python.org/downloads and check "Add to PATH".

### `pip install -e` fails
You need an internet connection. The `-e` flag installs in editable mode, which
requires access to PyPI.

### PyInstaller can't find the PySide6 plugins
Run `pip install -e ".[gui,dev]"` — it installs PySide6 and its plugins.

### The program can't start (missing DLL)
Install the Microsoft Visual C++ Redistributable from
https://aka.ms/vs/17/release/vc_redist.x64.exe

### Missing vehicle data folders
DTS-Monaco needs configuration data folders. Copy them to `C:\DTS_Monaco_Data\`

### Method 2: NSIS installer (optional)

If you want a Windows installer, you need NSIS (Nullsoft Scriptable Install
System). Download it from https://nsis.sourceforge.io/

1. Install NSIS (default settings).
2. Open `packaging/installer/dts-monaco.nsi` in the NSIS Qt GUI and click
   "Compile". The installer (`dts-monaco_installer.exe`) will appear in the
   output directory.
3. Alternatively, compile from the NSIS terminal:
   ```cmd
   cd "C:\Program Files\NSIS\Bin"
   makensis.exe dts-monaco.nsi
   ```

See `packaging/installer/notes.md` for the full NSIS build guide.
