"""ISO 15765-2 (ISO-TP) transport layer.

This is the "truck" the CAN "road" uses. Long messages or large data
transfers are split into a sequence of small CAN frames, then re-assembled
on the other side. UDS (ISO 14229) rides on top of ISO-TP.

The two modes of operation:
  - Normal frames (single CAN frame): used for small messages (<= 7 bytes data)
  - Extended frames (multi-frame): PSI (protocol service indication)
    0x10 = first frame, 0x20 = consecutive frame, 0x30 = flow control

We keep the ISO-TP logic here so neither the CAN layer nor the UDS layer
needs to know about the low-level framing.
"""

from __future__ import annotations

from .can import CanFrame

# --- ISO-TP control bytes (PSI)
PHONE_FIRST_FRAME = 0x10
PHONE_CON_SEC_FRAME = 0x20
PHONE_FLOW_CONTROL = 0x30

# Flow control sub-function codes
FC_BLOCK_SORRY = 0x00
FC_BLOCK_NORMAL = 0x40
FC_BLOCK_FLOW = 0x80

# --- ISO-TP protocol data units (what the other side says)
# We don't need to parse the other side's ISO-TP frames in detail here -
# the UDS client handles that. This module just does the framing.


def split_message(data: bytes, max_payload: int = 7) -> list[bytes]:
    """Break a payload into ISO-TP multi-frame chunks.

    Each chunk is a plain bytestring that the caller wraps into a CAN frame.
    """
    if not data:
        return []
    # In normal frames the data field is the max length we can fit.
    # For simplicity we chunk at max_payload (typical 7 for first frame,
    # 7 for consecutive). Keep it simple: chunk into chunks of 7.
    chunks = []
    for i in range(0, len(data), max_payload):
        chunk = data[i:i + max_payload]
        chunks.append(chunk)
    return chunks


def pack_iso_tp_first_frame(payload: bytes) -> bytes:
    """Make the first frame of a multi-frame transmission.

    In ISO-TP the first frame carries the first 0-7 bytes of payload.
    For this standalone tool we just return the payload chunked at 7 bytes.
    The real encoder wraps this in a CAN frame with PSI = 0x10.
    """
    return payload


def pack_iso_tp_flow_control(fc_block: int, block_size: int, timeout: int) -> bytes:
    """Build the flow control response the ECU wants to see.

    block_size = how many frames the client may send before waiting
    timeout    = how long (ms) the client has to respond
    """
    return bytes([FC_BLOCK_FLOW, block_size & 0x7F, timeout & 0xFF])


def pack_iso_tp_cons_sec_frame(block: int, count: int) -> bytes:
    """Consecutive frame (the ECU asks for the next bytes)."""
    return bytes([PHONE_CON_SEC_FRAME, block, count & 0xFF])
