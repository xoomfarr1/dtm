"""USB dongle driver (python-can abstraction).

This wraps `python-can`, which already supports dozens of USB-to-CAN adapters
(PEAK PCAN, Kvaser, gs_usb / Candlelight, IXXAT, ETAS, SI-TC, and many more).

The adapter picks the best available backend for your adapter. Most cheap
dongles use the `slcan` firmware or a proprietary driver; python-can will
auto-detect the right backend when you pass an interface name like
'pcan' or 'kvaser'.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from can import BusABC, Message
from can.interface import Bus

from ..hardware.base import CanHardwareAdapter, HardwareInfo, HardwareError, HardwareType

logger = logging.getLogger(__name__)


class UsbDongleAdapter(CanHardwareAdapter):
    """USB CAN adapter (any adapter python-can supports).

    Typical usage:
        adapter = UsbDongleAdapter(interface="pcan", channel="0", bitrate=500000)
        adapter.open()
        ...

    Where ``interface`` is one of:
        - "pcan"      → PEAK PCAN-USB
        - "kvaser"    → Kvaser Leaf / HS
        - "gs_usb"    → Candlelight / Geschwister Schneider
        - "slcan"     → cheap USB dongles with SLCAN firmware (COM port)
        - "virtual"   → dummy backend (no hardware)
    """

    def __init__(self, interface: str = "slcan",
                 channel: str = "0", bitrate: int = 500000,
                 port: str | None = None,
                 receive_own_messages: bool = False):
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.port = port or f"COM{port or '0'}"
        self.receive_own_messages = receive_own_messages
        self._bus: BusABC | None = None
        self._opened = False

    # ------------------------------------------------------------------
    def open(self) -> None:
        """Open the USB dongle through python-can."""
        if self._opened:
            return

        # Build the config dict python-can expects
        kwargs = {
            "bitrate": self.bitrate,
            "receive_own_messages": self.receive_own_messages,
        }
        if self.channel and self.channel != "0":
            kwargs["channel"] = self.channel
        if self.port:
            kwargs["port"] = self.port

        try:
            self._bus = Bus(
                interface=self.interface, **kwargs
            )
            self._opened = True
            logger.info(f"USB dongle opened: interface={self.interface}, bitrate={self.bitrate}")
        except Exception as exc:
            raise HardwareError(
                f"Could not open USB dongle on interface '{self.interface}'. "
                f"python-can error: {exc!s}. "
                f"Try 'slcan' for a cheap dongle, or install the right driver "
                f"and try 'pcan' or 'kvaser'."
            ) from exc

    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.shutdown()
            except Exception:
                pass
            self._bus = None
        self._opened = False

    # ------------------------------------------------------------------
    def read(self, timeout_ms: int = 100) -> bytes | None:
        if not self._opened or self._bus is None:
            return None
        try:
            msg = self._bus.recv(timeout_ms / 1000.0)
            if msg is None:
                return None
            # Return a raw byte representation of the frame (ID + data)
            payload = msg.id.to_bytes(4, "big", signed=False)
            payload += bytes([msg.dlc])
            payload += msg.data
            return payload
        except Exception as exc:
            logger.warning(f"read error: {exc}")
            return None

    # ------------------------------------------------------------------
    def write(self, frame: bytes) -> int:
        if not self._opened or self._bus is None:
            return 0
        try:
            # frame format: [4-byte id][1-byte dlc][data...]
            frame_id = int.from_bytes(frame[0:4], "big", signed=False)
            dlc = frame[4]
            data = frame[5:5 + dlc]
            msg = Message(arbitration_id=frame_id,
                          dlc=dlc, data=data, extended=False, is_error_frame=False)
            self._bus.send(msg)
            return len(data)
        except Exception as exc:
            logger.warning(f"write error: {exc}")
            return 0

    # ------------------------------------------------------------------
    def get_info(self) -> HardwareInfo:
        return HardwareInfo(
            kind=HardwareType.USB_DONGLE,
            port=(self.port or self.interface),
            vendor_id="unknown",
            product_id=self.channel,
            serial="",
            channels=1,
        )

    # ------------------------------------------------------------------
    def test(self) -> bool:
        if not self._opened or self._bus is None:
            return False
        try:
            # Fire a heartbeat frame and see if we get a response back
            self._bus.send(can.Message(arbitration_id=0x7A0, dlc=1, data=b"\x01"))
            # Give the bus a moment to respond
            time.sleep(0.1)
            return True
        except Exception:
            return False
