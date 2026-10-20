# DTS-Monaco — Windows packaging

This directory holds the tools that turn the DTS-Monaco source into a
standalone Windows executable (`dtm.exe`) you can hand to a customer.

## What's here

| File | What it does |
| --- | --- |
| `WIN_BUILD.md` | Step-by-step Windows build instructions — read this first |
| `make_windows_exe.sh` | Build `dtm.exe` from Linux, using Wine as the host |
| `dts_monaco_windows.spec` | PyInstaller spec (one-folder + one-file) |
| `README.md` | This file |

The installer lives in the parent `installer/` directory:

| File | What it does |
| --- | --- |
| `dts-monaco.nsi` | NSIS installer script |
| `notes.md` | NSIS build notes |

## Quick path: from a Windows machine

1. Install Python 3.10+ and make sure "Add to PATH" is ticked.
2. Run `build_windows.bat` from the DTS-Monaco folder — it's a double-clickable
   script that sets up the venv, installs dependencies, builds `dtm.exe`, and
   pauses so you can read the output.
3. Copy `dtm.exe` to a clean machine and test it.

## Quick path: from Linux (Wine)

If you need a Windows `dtm.exe` from a Linux box:

```bash
# full steps in packaging/WIN_BUILD.md
./packaging/make_windows_exe.sh
```

The finished exe lands in `build/dist/dtm.exe`.

## Why there are two scripts

PyInstaller can't cross-compile, so one script alone wouldn't work on both
platforms. `build_windows.bat` is for when you're on Windows, and
`make_windows_exe.sh` is for when you're on Linux (with Wine). Pick the host
you're already on.
