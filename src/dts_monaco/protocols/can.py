"""CAN bus framing: CAN 2.0A / CAN 2.0B and CAN FD.

A CAN frame is:
  [Start Of Frame]  [Identifer 11 or 29 bits]  [RTR]  [DLC 0-8/0-64]  [Data 0-64/0-256]  [CRC]

We treat frames as plain bytes and hide all the bit-wrangling behind
simple helpers. You will almost never need to touch these raw bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

# ---------------------------------------------------------------- constants
class FrameType(IntEnum):
    DATA = 0x00
    REMOTE_REQUEST = 0x01
    ERROR_FRAME = 0x02
    OVERLOAD_FRAME = 0x03
    SRR = 0x04

# CAN 2.0B is the default "heavy" frame with a 29-bit identifier.
CAN_ID_STANDARD = 11   # 11-bit identifier
CAN_ID_EXTENDED = 29   # 29-bit identifier

# ------------------------------------------------- frame dataclass
@dataclass
class CanFrame:
    """One CAN message, ready to send or ready to parse."""

    identifier: int          # 11-bit or 29-bit (keep under 0x80000000 for standard)
    dlc: int = 0             # data length code 0..64 (CAN FD) / 0..8 (CAN 2.0B)
    data: bytes = b""
    is_remote: bool = False
    is_error: bool = False
    extended: bool = False   # True = CAN 2.0B 29-bit
    brs: bool = False        # CAN FD: bit-rate switch
    rtr: bool = False        # remote request flag

    def __post_init__(self) -> None:
        if not (0 <= self.dlc <= 64):
            raise ValueError("DLC must be 0..64")
        if len(self.data) > self.dlc:
            # Truncate to match DLC - it is the hard limit.
            self.data = self.data[: self.dlc]

    # ------------------------------------------------------------ helpers
    @property
    def data_len(self) -> int:
        return len(self.data)

    @property
    def byte_count(self) -> int:
        """How many bytes this frame will actually occupy on the wire."""
        return self.data_len + 4  # header + data; CRC not counted here

    @classmethod
    def build(cls, identifier: int, data: bytes, extended: bool = False,
              brs: bool = False, rtr: bool = False) -> "CanFrame":
        dlc = min(len(data), 64)
        return cls(identifier=identifier, dlc=dlc, data=data,
                   extended=extended, brs=brs, rtr=rtr)

    @classmethod
    def dummy(cls, identifier: int, length: int, extended: bool = False) -> "CanFrame":
        """A zero-filled frame with a given DLC (useful for remote requests)."""
        return cls(identifier=identifier, dlc=length, data=b"\x00" * length,
                   extended=extended, is_remote=True)

    # ------------------------------------------------------------ encode
    def encode(self) -> bytes:
        """Turn this frame into the raw bytes that go on the wire."""
        msg = bytearray()
        identifier = self.identifier & 0x1FFFFFFF

        # Start-of-frame
        msg.append(0x00)

        if self.extended:
            msg[0] |= 0x80  # IDE bit
            # 29-bit identifier goes in bytes 1-3
            msg[1] = (identifier >> 18) & 0xFF
            msg[2] = (identifier >> 10) & 0xFF
            msg[3] = (identifier >> 2) & 0xFF
        else:
            msg[0] |= identifier >> 3  # bits 0..17

        # RTR control
        if self.is_remote:
            msg[0] |= 0x40
        elif self.rtr:
            msg[0] |= 0x20

        # DLC
        if self.extended:
            msg[0] |= 0x04  # ESI
        msg[0] |= (self.dlc & 0x0F) << 4

        # Data
        msg += self.data[: self.dlc]

        return bytes(msg)

    # ------------------------------------------------------------ decode
    @classmethod
    def decode(cls, raw: bytes) -> "CanFrame":
        """Parse a raw CAN frame into a structured object."""
        if len(raw) < 4:
            raise ValueError("Wire frame is too short to parse")
        idx = 0
        byte0 = raw[idx]
        idx += 1

        is_extended = bool(byte0 & 0x80)
        is_remote = bool(byte0 & 0x40)
        is_error = bool(byte0 & 0x02)

        # identifier
        if is_extended:
            identifier = ((byte0 & 0x07) << 18) | (raw[idx] << 10) | (raw[idx+1] << 2) | (raw[idx+2] >> 6)
            dlc = (raw[idx+2] & 0x03) << 2
            idx += 3
        else:
            identifier = ((byte0 >> 3) & 0x7FF)
            dlc = (byte0 >> 4) & 0x0F
            idx += 1

        # DLC is capped at 64 for CAN FD, 8 for classic CAN
        dlc = min(dlc, 64)
        data = raw[idx:idx + dlc]
        # Pad if the frame reports DLC more than the actual data (unlikely but safe)
        data = data.ljust(dlc, b"\x00") if len(data) < dlc else data

        return cls(
            identifier=identifier,
            dlc=dlc,
            data=data,
            is_remote=is_remote,
            is_error=is_error,
            extended=is_extended,
        )

    def __str__(self) -> str:
        return (f"CanFrame(id={self.identifier:#06x}, len={self.data_len}, "
                f"ext={self.extended}, rtr={self.is_remote})")


def format_can_id(identifier: int, extended: bool) -> str:
    """Human-readable identifier with a hint about the ECU (series letters)."""
    if extended:
        return f"{identifier:#010x} (29-bit)"
    return f"{identifier:#05x} (11-bit)"
