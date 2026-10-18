"""Hardware abstraction layer.

The tool talks to vehicles through CAN hardware. Different adapters need
different drivers, but the user only ever sees one clean "interface".

Two hardware paths are supported:
  1) PT3G-VCI  -> uses the ACTIA PDU API driver on Windows (the same driver
                   Porsche uses for their PIWIS III diagnostic software).
                   We wrap the native Windows DLL with ctypes and present
                   it as a regular CAN interface.
  2) USB dongle -> uses `python-can` with whatever native backend the dongle
                   supports (PEAK PCAN, gs_usb/Candlelight, Kvaser, etc.).

A "virtual" driver is provided for development and testing, so the tool
runs on any machine before you plug in real hardware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class HardwareError(Exception):
    """Something went wrong talking to the hardware."""


class HardwareType(Enum):
    PT3G_VCI = "pt3g-vci"
    USB_DONGLE = "usb-dongle"
    VIRTUAL = "virtual"


@dataclass
class HardwareInfo:
    """What the tool learned about a plugged-in adapter."""
    kind: HardwareType
    port: str = "unknown"
    vendor_id: str = ""
    product_id: str = ""
    serial: str = ""
    channels: int = 1

    def __str__(self) -> str:
        return f"{self.kind.value} on {self.port}"


class CanHardwareAdapter(ABC):
    """The contract every CAN adapter must fulfill.

    The UDS protocol layer calls only these four methods - it knows nothing
    about the real hardware underneath.
    """

    @abstractmethod
    def open(self) -> None:
        """Plug in the adapter and open the CAN channel."""

    @abstractmethod
    def close(self) -> None:
        """Close the CAN channel."""

    @abstractmethod
    def read(self, timeout_ms: int = 100) -> bytes | None:
        """Return one raw CAN frame, or None if nothing arrived."""

    @abstractmethod
    def write(self, frame: bytes) -> int:
        """Transmit a raw CAN frame. Returns number of bytes sent."""

    @abstractmethod
    def get_info(self) -> HardwareInfo:
        """Return what we know about this adapter."""

    @abstractmethod
    def test(self) -> bool:
        """Send a heartbeat and check the adapter is alive."""
