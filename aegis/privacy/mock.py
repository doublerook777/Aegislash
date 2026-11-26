"""MOCK for contracts/privacy.md. Placeholders for every type, the contract's example
answer for the example DOB, fail-closed [REDACTED] for unknown types, KeyError for an
unknown record_id."""
from __future__ import annotations

from aegis.link import pseudonym
from aegis.types import TYPES, Finding, RecordResult, Replacement

_KEEP = ("CONDITION", "DISTRICT", "GENDER")


def plan(results: list[RecordResult], keys: dict[str, str | None]) -> dict:
    return {"keys": {r["record_id"]: keys.get(r["record_id"]) for r in results}}


def replace(plan: dict, record_id: str, finding: Finding) -> Replacement:
    key = plan["keys"][record_id]  # KeyError for unknown record_id (contract error case)
    t = finding["type"]
    if t not in TYPES:
        return {"text": "[REDACTED]", "status": "sanitized"}
    if t in _KEEP:
        return {"text": None, "status": "sanitized"}
    if t in ("PATIENT_NAME", "MRN") and key:
        return {"text": pseudonym(key), "status": "sanitized"}
    if t == "DOB" and finding["text"] == "12/04/1977":
        return {"text": "03/07/1977", "status": "generalized"}
    if t in ("DOB", "DATE", "AGE", "VILLAGE", "PIN"):
        return {"text": f"[{t}]", "status": "generalized"}
    label = {"PATIENT_NAME": "PATIENT", "RELATIVE_NAME": "RELATIVE"}.get(t, t)
    return {"text": f"[{label}]", "status": "sanitized"}


def stats(plan: dict) -> dict:
    return {"records_generalized": 0, "records_suppressed": 0}
