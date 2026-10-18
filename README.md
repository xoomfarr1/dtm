# dts-monaco
An open-source engineering diagnostic toolchain for vehicle ECUs, designed as
a free, safe alternative to the commercial Softing DTS Monaco.

It lets you talk to vehicle computers (ECUs) over CAN/UDS:
- Read fault codes (DTCs)
- Read and write variant coding (SA codes, parameters)
- Flash ECU firmware (SF11/SF03 upload)
- Monitor the bus (see every CAN message)
- Run diagnostic routines

Built with:
- Python 3.10+
- python-can (hardware abstraction)
- PySide6 (Windows GUI)
- UDS (ISO 14229) protocol stack

## Project structure
```
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

## Quick start (development)
```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[gui,dev]"
python -m dts_monaco
```

## How to use
1. Launch the app
2. Press "1. Connect to my car" to connect to your vehicle
3. Select a function from the tabs:
   - Read fault codes
   - Read / write car settings
   - Watch the car talk (bus monitor)
   - Flash ECU software
4. Press "Done" to exit

## Legal
- This open-source tool provides the *communication stack* and *tooling*.
- The proprietary data files (CBF/SMR-D with vehicle-specific coding tables)
  are **licensed separately** by the manufacturer (e.g., Softing, Mercedes).
- You must source the appropriate vehicle data files through proper
  channels (e.g., your vehicle's OEM diagnostics package).
- This tool is for educational and professional engineering use.
  Always back up your files before making changes.

## Environment requirements
- Windows 10/11 (for the end-user GUI)
- A CAN adapter: PT3G-VCI or USB-to-CAN dongle
- Python 3.10+ (for development)

## Packaging for Windows

The end-user deliverable is a standalone Windows executable (`dtm.exe`)
built with PyInstaller. PyInstaller **never cross-compiles**, so the exe must
be built on a Windows machine — never from Linux.

### Build on Windows

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

- `build_windows.bat` — double-clickable script that sets up the venv,
  installs dependencies, runs PyInstaller, and verifies the build.
- `build/dts_monaco.spec` — PyInstaller spec file for one-file builds.

## License
GPL-3.0
```

## Development
For information on how to develop on this project, including hardware setup,
protocol implementation, and adding new features, see the
[development guide](docs/DEVELOPMENT.md).

## Project status
- **Phase 1 complete**: Protocol stack (CAN, ISO-TP, UDS), hardware
  abstraction (PT3G-VCI, USB dongle), logic engine, data parser (SMR-D/ODX),
  ELI5 explanation system, and simple Windows GUI.
- **Phase 2**: Hook up to real hardware, implement full UDS service set,
  add SDF/OTX test sequence runner, polish GUI.
# dtm
