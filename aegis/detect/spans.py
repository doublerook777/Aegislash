"""A candidate is a possible finding. Many rules propose candidates; `resolve` keeps a
non-overlapping set, where the higher priority wins, then the longer span."""
from __future__ import annotations

from typing import NamedTuple, Optional

# higher number wins when two candidates overlap
PRIORITY = {
    "ABHA_ADDRESS": 100, "EMAIL": 99, "ABHA_NUMBER": 98, "AADHAAR_MASKED": 97, "INSURANCE_ID": 96,
    "PAN": 95, "MRN": 94, "AADHAAR": 93, "PHONE": 90, "OTHER_ID": 88, "DOB": 85, "DATE": 80, "PIN": 75,
    "HOUSE": 70, "LANDMARK": 69, "VILLAGE": 68, "LOCALITY": 67, "RELATIVE_NAME": 65, "PATIENT_NAME": 64,
    "AGE": 55, "DISTRICT": 12, "GENDER": 11, "CONDITION": 10,
}
PROPAGATED = 40  # priority for values copied from elsewhere in the file


class Cand(NamedTuple):
    start: int
    end: int
    type: str
    norm: Optional[str] = None
    role: Optional[str] = None
    prio: Optional[int] = None
    relation: Optional[str] = None  # S/o, D/o, W/o, C/O (relatives only; used for Evidence)
    hinglish: bool = False
    full_name: Optional[str] = None  # names inside one structured field (HL7 family^given): the whole name's norm


def resolve(cands: list[Cand]) -> list[Cand]:
    ranked = sorted(cands, key=lambda c: (-(c.prio if c.prio is not None else PRIORITY[c.type]),
                                          -(c.end - c.start), c.start, c.type, c.norm or ""))
    kept: list[Cand] = []
    for c in ranked:
        if c.end > c.start and all(c.end <= k.start or c.start >= k.end for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c.start)
