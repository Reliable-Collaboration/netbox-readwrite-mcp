"""Slow, randomly salted intent fingerprints, separate from fast evidence hashes."""

import hashlib
import hmac
import secrets

from .store import digest, encode


def fingerprint(value, previous=None):
    # Old immutable journals retain their original representation for replay only.
    # New intents never create an unsalted credential verification oracle.
    if previous is not None and len(previous) == 64:
        return digest(value)
    salt = secrets.token_bytes(16) if previous is None else bytes.fromhex(previous.split(":")[1])
    if len(salt) != 16 or (previous is not None and not previous.startswith("scrypt-v1:")):
        raise ValueError("Invalid intent fingerprint")
    result = hashlib.scrypt(encode(value).encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864)
    return "scrypt-v1:" + salt.hex() + ":" + result.hex()


def matches(value, previous):
    return hmac.compare_digest(fingerprint(value, previous), previous)


def redact_passwords(value):
    """Remove known password fields, including nested bulk payloads, from durable intent."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key in {"password", "old_password", "new_password1", "new_password2"}
            else redact_passwords(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_passwords(item) for item in value]
    return value
