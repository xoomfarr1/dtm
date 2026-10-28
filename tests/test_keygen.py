import os
import time

from dts_monaco.keygen import generate_key, parse_key, verify_key


def test_roundtrip():
    key = generate_key(edition="pro", days=30)
    assert verify_key(key) is True
    lic = parse_key(key)
    assert lic is not None
    assert lic.edition == "pro"
    assert lic.expiry > 0


def test_invalid():
    assert verify_key("AAAAA-BBBBB-CCCCC") is False
    assert parse_key("AAAAA-BBBBB-CCCCC") is None


def test_never_expires():
    key = generate_key(days=0)
    assert verify_key(key) is True
    lic = parse_key(key)
    assert lic is not None
    assert lic.expiry == 0
    assert not lic.is_expired()


def test_tampered():
    key = generate_key()
    parts = key.split("-")
    parts[-1] = "ZZZZZ"
    assert verify_key("-".join(parts)) is False
