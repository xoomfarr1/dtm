# DTS-Monaco

An open-source diagnostic toolchain for vehicle ECUs — a free, safe alternative to commercial boxes like Softing DTS Monaco.

You install it when you need to actually talk to a car's computer. Plug in a
CAN adapter and it lets you:

- Read fault codes (DTCs) from the ECU
- Read and write variant coding — SA codes, parameters, the stored settings
- Flash ECU firmware (SF11 / SF03 upload)
- Monitor the bus — watch every CAN message go by
- Run diagnostic routines

It's built on Python 3.10+, `python-can` (so the hardware doesn't dictate your
workflow), `PySide6` (a simple Windows GUI), and the `UDS` (ISO 14229) protocol
stack.

## What's in here

```text
src/dts_monaco/
  __init__.py          Package metadata
  __main__.py          CLI entry point (python -m dts_monaco)
  config.py            Settings + project file model
  hardware/            Hardware abstraction (PT3G-VCI, USB dongle)
    base.py            CanHardwareAdapter contract
    pt3gvci.py         PT3G-VCI via Actia PDU API (Windows)
    usb_dongle.py      USB dongle via python-can
  protocols/           Protocol stack
    can.py             CAN 2.0A/B + CAN FD framing
    iso_tp.py          ISO 15765-2 transport (multi-frame)
    uds.py             UDS (ISO 14229) client
  data/                Vehicle data parsing
    smr_d.py           SMR-D / ODX parser (CBF + SMR-D)
  logic/               Business logic (sessions, diagnostics, coding)
    engine.py          LogicEngine (session lifecycle)
    variant_coding.py  Variant coding + seed/key compute
    flashing.py        Bus monitor + flash programmer
    logger.py          Bus frame logger (SQLite)
    diagnostics.py     Fault code reading / clearing
  gui/                 Simple Windows GUI (caveman-friendly, ELI5)
    simple_window.py   Main window with tabs + tutorial
```

## Get it running (development)

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[gui,dev]"
python -m dts_monaco
```

## Using it, day to day

1. Launch the app.
2. Press "1. Connect to my car" to connect to your vehicle.
3. Pick a function from the tabs — read fault codes, read / write car settings,
   watch the car talk (bus monitor), or flash ECU software.
4. Press "Done" to exit.

## Legal

- This open-source tool provides the *communication stack* and *tooling*.
- The proprietary data files (CBF/SMR-D with vehicle-specific coding tables)
  are **licensed separately** by the manufacturer (e.g., Softing, Mercedes).
  You source the appropriate vehicle data files through proper channels
  (e.g., your vehicle's OEM diagnostics package).
- For educational and professional engineering use. Always back up your files
  before making changes.

## What you need

- Windows 10/11 (for the end-user GUI)
- A CAN adapter: PT3G-VCI or USB-to-CAN dongle
- Python 3.10+ (for development)

## Building the Windows executable

The end-user deliverable is a standalone Windows executable (`dtm.exe`) built
with PyInstaller. PyInstaller **never cross-compiles**, so the exe has to be
built on a Windows machine — never from Linux.

### Build it on Windows

```powershell
# 1. Create and populate the environment
python -m venv venv
venv\Scripts\activate
pip install -e ".[gui]"
pip install pyinstaller

# 2. Build the one-file GUI executable
pyinstaller ^
  --noconfirm --onefile --windowed ^
  --name dtm ^
  --collect-all dts_monaco ^
  --hidden-import dts_monaco.config ^
  --paths venv\Lib\site-packages ^
  src\dts_monaco\__main__.py
```

Notes:

- `--windowed` suppresses the console window for the GUI app.
- `--paths` points PyInstaller at the virtualenv's site-packages so the
  editable install's dependencies (python-can, py-uds, pydantic) are bundled.
- PySide6 and its Qt plugins often need extra runtime hooks to locate the
  platform plugin. Use a PySide6-compatible `pyinstaller-hooks-contrib` and
  validate the produced exe on a clean Windows 10/11 machine before shipping.

### Build scripts (for Windows)

- `build_windows.bat` — double-clickable script that sets up the venv, installs
  dependencies, runs PyInstaller, and verifies the build.
- `build/dts_monaco.spec` — PyInstaller spec file for one-file builds.

## Packaging — the Windows toolchain

DTS-Monaco is distributed as a standalone Windows executable (`dtm.exe`). PyInstaller
can't cross-compile from Linux, so the build has to run on Windows.

The Windows toolchain lives in the `packaging/` directory and mirrors the
structure used by mbtools-open:

```text
packaging/
  WIN_BUILD.md              — Step-by-step Windows build instructions
  make_windows_exe.sh       — Shell script to build dtm.exe from Linux (Wine)
  dts_monaco_windows.spec   — PyInstaller spec (one-folder + one-file)
  README.md                 — This file (packaging guide)
```

The installer lives in the parent `installer/` directory:

```text
installer/
  dts-monaco.nsi     — NSIS installer script
  notes.md           — NSIS build instructions
```
