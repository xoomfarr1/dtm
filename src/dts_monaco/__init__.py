"""dts-monaco — open-source engineering diagnostic toolchain.

A Windows application that lets you talk to vehicle ECUs over CAN / UDS:
read fault codes, do variant coding, flash firmware, monitor the bus,
and run test sequences — using open standards (UDS ISO 14229, CAN FD).

This is the *logic* layer. The user-friendly GUI lives in ``dts_monaco.gui``.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dts-monaco")
except PackageNotFoundError:
    __version__ = "0.1.dev"

__all__ = ["__version__"]
