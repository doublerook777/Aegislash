"""MOCK for contracts/link.md. Returns the contract's example mapping for the example
evidence, None for every other record, and raises secret_missing without RAKSHA_SECRET."""
from __future__ import annotations

import json
from pathlib import Path

from aegis.link.psn import secret
from aegis.types import Evidence

_EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def resolve(evidence: list[Evidence]) -> dict[str, str | None]:
    secret()  # raises RuntimeError("secret_missing") when unset, exactly like the real one
    known = json.loads((_EXAMPLES / "link_response.json").read_text(encoding="utf-8"))
    return {e["record_id"]: known.get(e["record_id"]) for e in evidence}
