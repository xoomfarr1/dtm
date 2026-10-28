"""License-key generator for dts-monaco.

Generates and verifies signed license keys using HMAC-SHA256 over a
payload of (edition, expiry, serial). Keys are base32-encoded and
formatted in groups for readability.

This is a *local* key scheme: the signing secret lives in the
``DTS_MONACO_KEY_SECRET`` environment variable (or a default dev
secret). Verification uses the same secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass

DEFAULT_SECRET = b"dts-monaco-dev-secret-change-me"
SECRET_ENV = "DTS_MONACO_KEY_SECRET"


def _secret() -> bytes:
    val = os.environ.get(SECRET_ENV)
    if val:
        return val.encode("utf-8")
    return DEFAULT_SECRET


@dataclass
class License:
    edition: str
    expiry: int  # unix timestamp; 0 = never
    serial: int

    def is_expired(self, now: int | None = None) -> bool:
        if self.expiry == 0:
            return False
        now = now if now is not None else int(time.time())
        return now > self.expiry


def _sign(payload: bytes) -> bytes:
    return hmac.new(_secret(), payload, hashlib.sha256).digest()[:8]


def generate_key(edition: str = "pro", days: int = 365, serial: int | None = None) -> str:
    """Generate a signed license key."""
    if serial is None:
        serial = int(time.time()) & 0xFFFFFFFF
    expiry = int(time.time()) + days * 86400 if days > 0 else 0
    payload = edition.encode() + b"\x00" + struct.pack(">II", expiry, serial)
    sig = _sign(payload)
    raw = payload + sig
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    # format in groups of 5
    groups = [b32[i:i + 5] for i in range(0, len(b32), 5)]
    return "-".join(groups)


def parse_key(key: str) -> License | None:
    """Parse and verify a key. Returns License if valid signature, else None."""
    b32 = key.replace("-", "").replace(" ", "").upper()
    # pad
    pad = "=" * ((8 - len(b32) % 8) % 8)
    try:
        raw = base64.b32decode(b32 + pad)
    except Exception:
        return None
    if len(raw) < 1 + 8 + 8:
        return None
    # payload = edition (variable) ... we stored edition as bytes until \x00
    # reconstruct: find null separator
    null_idx = raw.find(b"\x00")
    if null_idx < 0:
        return None
    edition = raw[:null_idx].decode("utf-8", errors="replace")
    rest = raw[null_idx + 1:]
    if len(rest) < 4 + 4 + 8:
        return None
    expiry, serial = struct.unpack(">II", rest[:8])
    sig = rest[8:16]
    payload = raw[:null_idx + 1 + 8]
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    return License(edition=edition, expiry=expiry, serial=serial)


def verify_key(key: str) -> bool:
    lic = parse_key(key)
    if lic is None:
        return False
    if lic.is_expired():
        return False
    return True


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="dts-monaco-keygen", description="DTS-Monaco license key generator")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate a license key")
    g.add_argument("--edition", default="pro")
    g.add_argument("--days", type=int, default=365)
    g.add_argument("--serial", type=int, default=None)
    v = sub.add_parser("verify", help="verify a license key")
    v.add_argument("key")
    args = p.parse_args(argv)
    if args.cmd == "generate":
        print(generate_key(edition=args.edition, days=args.days, serial=args.serial))
        return 0
    if args.cmd == "verify":
        lic = parse_key(args.key)
        if lic is None:
            print("INVALID (bad signature or format)")
            return 1
        if lic.is_expired():
            print(f"EXPIRED (edition={lic.edition}, expiry={lic.expiry})")
            return 1
        print(f"VALID (edition={lic.edition}, expiry={lic.expiry}, serial={lic.serial})")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())