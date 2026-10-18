"""Command-line entry point.

Run with::

    python -m dts_monaco
    dtm                # if installed as a console script

Starts the simple Windows GUI (caveman-friendly, step-by-step).
"""

from __future__ import annotations

import sys
from PySide6 import QtWidgets

from . import __version__
from .config import Settings, load_settings
from .gui.simple_window import SimpleWindow


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0 = success)."""
    settings = load_settings()
    print(f"dts-monaco {__version__}")
    print(f"settings: {settings.model_dump()}")

    # PySide6 requires a QApplication for any GUI. Create one if none exists
    # (so the module can also be imported headlessly for tests).
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # The GUI is the only runner right now — the logic is hidden inside
    # the window so the user never has to type a command.
    window = SimpleWindow(settings)
    window.show()
    window.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
