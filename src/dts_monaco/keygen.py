"""License-key generator for dts-monaco.

Generates and verifies signed license keys bound to an edition, an
expiry date, a serial, a registered user name, and a hardware id
(dongle serial / machine id). Keys are HMAC-SHA256 signed over a
canonical JSON payload and base32-encoded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
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
    name: str = ""
    hardware_id: str = ""

    def is_expired(self, now: int | None = None) -> bool:
        if self.expiry == 0:
            return False
        now = now if now is not None else int(time.time())
        return now > self.expiry

    def matches_hardware(self, hardware_id: str) -> bool:
        if not self.hardware_id:
            return True
        return self.hardware_id == hardware_id


def get_hardware_id() -> str:
    """Best-effort hardware id for the current machine."""
    try:
        for path in ("/etc/machine-id", "/sys/class/dmi/id/product_uuid"):
            try:
                with open(path) as fh:
                    val = fh.read().strip()
                    if val:
                        return val
            except OSError:
                pass
    except Exception:
        pass
    return format(uuid.getnode(), "x")


def _payload_bytes(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: bytes) -> bytes:
    return hmac.new(_secret(), payload, hashlib.sha256).digest()[:12]


def generate_key(
    edition: str = "pro",
    days: int = 365,
    serial: int | None = None,
    name: str = "",
    hardware_id: str | None = None,
) -> str:
    if serial is None:
        serial = int(time.time()) & 0xFFFFFFFF
    expiry = int(time.time()) + days * 86400 if days > 0 else 0
    if hardware_id is None:
        hardware_id = get_hardware_id()
    data = {
        "edition": edition,
        "expiry": expiry,
        "serial": serial,
        "name": name,
        "hardware_id": hardware_id,
    }
    payload = _payload_bytes(data)
    sig = _sign(payload)
    raw = payload + b"." + sig
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    groups = [b32[i:i + 5] for i in range(0, len(b32), 5)]
    return "-".join(groups)


def parse_key(key: str) -> License | None:
    b32 = key.replace("-", "").replace(" ", "").upper()
    pad = "=" * ((8 - len(b32) % 8) % 8)
    try:
        raw = base64.b32decode(b32 + pad)
    except Exception:
        return None
    if b"." not in raw:
        return None
    payload, sig = raw.rsplit(b".", 1)
    if len(sig) != 12:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return License(
        edition=data.get("edition", ""),
        expiry=int(data.get("expiry", 0)),
        serial=int(data.get("serial", 0)),
        name=data.get("name", ""),
        hardware_id=data.get("hardware_id", ""),
    )


def verify_key(key: str, hardware_id: str | None = None) -> bool:
    lic = parse_key(key)
    if lic is None:
        return False
    if lic.is_expired():
        return False
    if hardware_id is None:
        hardware_id = get_hardware_id()
    if not lic.matches_hardware(hardware_id):
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
    g.add_argument("--name", default="")
    g.add_argument("--hardware-id", default=None, dest="hardware_id")
    v = sub.add_parser("verify", help="verify a license key")
    v.add_argument("key")
    v.add_argument("--hardware-id", default=None, dest="hardware_id")
    args = p.parse_args(argv)
    if args.cmd == "generate":
        print(generate_key(edition=args.edition, days=args.days, serial=args.serial,
                          name=args.name, hardware_id=args.hardware_id))
        return 0
    if args.cmd == "verify":
        lic = parse_key(args.key)
        if lic is None:
            print("INVALID (bad signature or format)")
            return 1
        if lic.is_expired():
            print(f"EXPIRED (edition={lic.edition}, expiry={lic.expiry})")
            return 1
        hid = args.hardware_id if args.hardware_id is not None else get_hardware_id()
        if not lic.matches_hardware(hid):
            print(f"HARDWARE MISMATCH (key={lic.hardware_id}, this={hid})")
            return 1
        print(f"VALID (edition={lic.edition}, expiry={lic.expiry}, serial={lic.serial}, "
              f"name={lic.name}, hardware_id={lic.hardware_id})")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
