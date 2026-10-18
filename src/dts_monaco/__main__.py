"""Command-line entry point.

Run with::

    python -m dts_monaco
    dtm                # if installed as a console script

Starts the simple Windows GUI (caveman-friendly, step-by-step).
"""

from __future__ import annotations

import sys

from . import __version__
from .config import Settings, load_settings
from .gui.simple_window import SimpleWindow


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0 = success)."""
    settings = load_settings()
    print(f"dts-monaco {__version__}")
    print(f"settings: {settings.model_dump()}")

    # The GUI is the only runner right now — the logic is hidden inside
    # the window so the user never has to type a command.
    app = SimpleWindow(settings)
    app.show()
    app.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
