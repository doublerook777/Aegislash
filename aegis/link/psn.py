"""Keyed, non-reversible pseudonyms: HMAC-SHA256 with RAKSHA_SECRET (never a plain hash)."""
from __future__ import annotations

import hashlib
import hmac
import os

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U


def secret() -> bytes:
    s = os.environ.get("RAKSHA_SECRET", "")
    if not s:
        raise RuntimeError("secret_missing")
    return s.encode("utf-8")


def pseudonym(patient_key: str) -> str:
    digest = hmac.new(secret(), b"psn|" + patient_key.encode("utf-8"), hashlib.sha256).digest()
    n = int.from_bytes(digest[:5], "big")
    return "PSN-" + "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in range(6))
