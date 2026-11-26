"""link module (owner: Member-3). Contract: contracts/link.md.

Provides cross-script record linkage (`resolve`) and keyed HMAC pseudonyms (`pseudonym`).
"""
from aegis.link.psn import pseudonym  # noqa: F401
from aegis.link.resolver import resolve  # noqa: F401
