"""ISO 15765-2 (ISO-TP) transport layer.

This is the "truck" the CAN "road" uses. Long messages or large data
transfers are split into a sequence of small CAN frames, then re-assembled
on the other side. UDS (ISO 14229) rides on top of ISO-TP.

The two modes of operation:
  - Normal frames (single / first frame): used for small messages (<= 7 data bytes)
  - Extended frames (multi-frame): PSI (protocol service indication)
    0x10 = first frame, 0x20 = consecutive frame, 0x30 = flow control

ISO 15765-2 (2.0A) frame formats:

  Single frame:     0xxxxxxx  DL = number of data bytes that follow
  First frame:      10xxxxxx  BS = block size (data bytes per block)
  Consecutive:      0010xxxx  block = block counter
  Flow control:     0011xxxx  sub-function, BS (7 bits), timeout (8 bits)
"""

from __future__ import annotations

# --- ISO-TP control bytes (PSI)
PHONE_FIRST_FRAME = 0x10
PHONE_CON_SEC_FRAME = 0x20
PHONE_FLOW_CONTROL = 0x30

# Flow control sub-function codes
FC_BLOCK_SORRY = 0x00
FC_BLOCK_NORMAL = 0x40
FC_BLOCK_FLOW = 0x80

# --- ISO-TP constants
MAX_DATA_BYTES = 7          # data bytes per frame (2.0A normal format)
MAX_FIRST_FRAME_DATA = 7    # first frame can carry 0-7 data bytes


def split_message(data: bytes, max_payload: int = MAX_DATA_BYTES) -> list[bytes]:
    """Break a payload into ISO-TP multi-frame chunks (payloads only).

    Each chunk is a plain bytestring that the caller wraps into a CAN frame
    with the appropriate protocol service indication (PSI) byte.
    """
    if not data:
        return []
    return [data[i:i + max_payload] for i in range(0, len(data), max_payload)]


def encode_iso_tp(payload: bytes, max_payload: int = MAX_DATA_BYTES) -> list[bytes]:
    """Encode a payload into a list of ISO-TP 2.0A frames.

    Each returned frame is a complete ISO-TP frame (with its PSI header)
    that the caller can wrap directly into a CAN frame.

    Format (normal, 2.0A):
      first frame : 0x10 | (BS & 0x0F), then up to 7 payload bytes
      consecutive: 0x20 | (block & 0x0F), then payload bytes
    """
    if not payload:
        return []
    frames = []
    total = len(payload)
    # --- first frame ---------------------------------------------------
    first_len = min(max_payload, total)
    frames.append(
        bytes([PHONE_FIRST_FRAME | (first_len & 0x0F)]) + payload[:first_len]
    )
    # --- consecutive frames ----------------------------------------------
    offset = first_len
    block = 1
    while offset < total:
        n = min(max_payload, total - offset)
        frames.append(
            bytes([PHONE_CON_SEC_FRAME | (block & 0x0F)]) + payload[offset:offset + n]
        )
        offset += n
        block += 1
    return frames


def decode_iso_tp_frames(frames: list[bytes]) -> bytes:
    """Reassemble a list of received ISO-TP 2.0A frames into the original payload.

    Validates the frame sequence and returns the concatenated payload data.
    Raises ValueError on malformed sequences (missing or out-of-order blocks).

    ISO 15765-2 2.0A uses a 4-bit block counter in consecutive frames, so
    block numbers wrap modulo 16. The decoder therefore tracks the expected
    block with modular arithmetic.
    """
    if not frames:
        return b""
    payload = bytearray()
    prev_block = 0
    first = frames[0]
    # --- first frame ------------------------------------------------------
    if len(first) == 0 or (first[0] & 0xF0) != PHONE_FIRST_FRAME:
        raise ValueError("First ISO-TP frame must start with 0x10 (first frame)")
    data_len = first[0] & 0x0F
    payload.extend(first[1:1 + data_len])
    # prev_block stays 0 (first frame represents block 0)
    # --- consecutive frames -------------------------------------------------
    for fr in frames[1:]:
        if len(fr) < 2:
            raise ValueError("Consecutive frame missing block counter")
        if (fr[0] & 0xF0) != PHONE_CON_SEC_FRAME:
            raise ValueError("Frame must be a consecutive frame (0x20)")
        block = fr[0] & 0x0F
        expected = (prev_block + 1) & 0x0F
        if block != expected:
            raise ValueError(
                f"Missing or reordered block: expected 0x{expected:01X}, got 0x{block:01X}"
            )
        payload.extend(fr[1:])
        prev_block = block
    return bytes(payload)


def pack_iso_tp_first_frame(payload: bytes) -> bytes:
    """Build a single ISO-TP first frame from a payload chunk (<= 7 bytes).

    Returns: 0x10 | BS, then the payload bytes.
    """
    if not payload:
        return b""
    return bytes([PHONE_FIRST_FRAME | (len(payload) & 0x0F)]) + payload


def pack_iso_tp_cons_sec_frame(block: int, data: bytes) -> bytes:
    """Build a single ISO-TP consecutive frame.

    block : block counter (0, 1, 2, ...)
    data  : the payload bytes carried in this block
    """
    return bytes([PHONE_CON_SEC_FRAME | (block & 0x0F)]) + data


def pack_iso_tp_flow_control(fc_block: int, block_size: int, timeout: int) -> bytes:
    """Build an ISO-TP flow-control frame.

    fc_block   : one of FC_BLOCK_SORRY, FC_BLOCK_NORMAL, FC_BLOCK_FLOW
    block_size : how many frames the sender may transmit before waiting
    timeout    : how long (ms) the sender has to respond
    """
    return bytes(
        [PHONE_FLOW_CONTROL | (fc_block & 0x0F), block_size & 0x7F, timeout & 0xFF]
    )
