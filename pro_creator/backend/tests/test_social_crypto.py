import base64
import hashlib
import hmac

from app.config import JWT_SECRET
from app.services.social_publish import _decrypt_secret, _encrypt_secret


def _legacy_encrypt(value: str) -> str:
    salt = "0123456789abcdef0123456789abcdef"
    seed = hashlib.sha256(f"{JWT_SECRET}::{salt}".encode("utf-8")).digest()
    raw = value.encode("utf-8")
    stream = bytearray()
    counter = 0
    while len(stream) < len(raw):
        stream.extend(hmac.new(seed, f"{salt}:{counter}".encode("utf-8"), hashlib.sha256).digest())
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(raw, bytes(stream[: len(raw)])))
    return f"{salt}:{base64.urlsafe_b64encode(cipher).decode('utf-8')}"


def test_social_secret_round_trip_uses_authenticated_v2_format() -> None:
    encrypted = _encrypt_secret("sensitive-token")
    assert encrypted is not None
    assert encrypted.startswith("v2:")
    assert _decrypt_secret(encrypted) == "sensitive-token"


def test_social_secret_tamper_is_rejected() -> None:
    encrypted = _encrypt_secret("sensitive-token")
    assert encrypted is not None
    tampered = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")
    assert _decrypt_secret(tampered) is None


def test_social_secret_legacy_rows_remain_readable() -> None:
    legacy = _legacy_encrypt("legacy-token")
    assert _decrypt_secret(legacy) == "legacy-token"
