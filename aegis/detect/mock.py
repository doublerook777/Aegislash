"""MOCK for contracts/detect.md. Returns the contract's example response, empty results
for anything else, and raises for any file whose path contains 'bad' (the error case)."""
from __future__ import annotations

import json
from pathlib import Path

from aegis.types import Record, RecordResult, empty_evidence

_EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def _example_responses() -> dict:
    data = json.loads((_EXAMPLES / "detect_response.json").read_text(encoding="utf-8"))
    return {r["record_id"]: r for r in data}


def detect_file(records: list[Record]) -> list[RecordResult]:
    if any("bad" in r["file"] for r in records):
        raise RuntimeError("mock_detect_error")
    known = _example_responses()
    out: list[RecordResult] = []
    for r in records:
        if r["record_id"] in known:
            out.append(known[r["record_id"]])
        else:
            out.append({"record_id": r["record_id"], "findings": [], "evidence": empty_evidence(r["record_id"])})
    return out
