"""link module (owner: Member-3). Contract: contracts/link.md.

`pseudonym` is the real keyed-HMAC implementation (from the kit starter).
`resolve` is currently the MOCK; swap the import when the real linker is ready.
"""
from aegis.link.mock import resolve  # noqa: F401
from aegis.link.psn import pseudonym  # noqa: F401
