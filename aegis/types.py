"""Shared data shapes. This file IS part of the contract (contracts/types.md).

Change rules (SPEC.md): adding an optional key needs only a note in SPEC.md;
changing or removing a key needs sign-off from every module that reads it.

All shapes are plain JSON-serializable dicts. They hold raw PII in memory only:
never print, log, pickle or write them to disk.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

FieldKind = Literal["value", "key", "header", "filename", "text"]
Fmt = Literal["csv", "tsv", "json", "fhir", "text"]
Role = Optional[Literal["patient", "relative"]]

DIRECT_TYPES = (
    "PATIENT_NAME", "RELATIVE_NAME", "PHONE", "AADHAAR", "AADHAAR_MASKED", "ABHA_NUMBER",
    "ABHA_ADDRESS", "EMAIL", "MRN", "PAN", "INSURANCE_ID", "HOUSE", "LOCALITY", "LANDMARK",
    "OTHER_ID",
)
QUASI_TYPES = ("DOB", "DATE", "AGE", "VILLAGE", "PIN")
INFO_TYPES = ("CONDITION", "DISTRICT", "GENDER")
TYPES = DIRECT_TYPES + QUASI_TYPES + INFO_TYPES
STRONG_ID_TYPES = ("PHONE", "AADHAAR", "ABHA_NUMBER", "ABHA_ADDRESS", "EMAIL", "MRN", "PAN", "INSURANCE_ID")


class Field(TypedDict):
    path: str            # col:<i> | /json/pointer | key:<pointer>/<key> | header:<i> | filename | text
    kind: FieldKind
    context: Optional[str]  # column header or JSON key above this value
    value: str           # always text; io restores JSON types on write


class Record(TypedDict):
    record_id: str       # "<input rel path>#<loc>"
    file: str
    loc: str             # row:N | /pointer | doc | @file
    fmt: Fmt
    fields: list[Field]


class Finding(TypedDict):
    path: str
    start: int
    end: int
    type: str            # one of TYPES
    text: str
    norm: Optional[str]
    role: Role


class NameMention(TypedDict):
    text: str
    norm: str
    script: Literal["latin", "deva", "hinglish"]
    role: Literal["patient", "relative"]
    relation: Optional[Literal["S/o", "D/o", "W/o", "C/O"]]


class IdMention(TypedDict):
    type: str            # one of STRONG_ID_TYPES
    norm: str


class Evidence(TypedDict):
    record_id: str
    names: list[NameMention]
    ids: list[IdMention]
    dob: Optional[str]
    age: Optional[int]
    gender: Optional[Literal["M", "F"]]
    village: Optional[str]
    district: Optional[str]
    pin: Optional[str]
    hospital: Optional[str]


class RecordResult(TypedDict):
    record_id: str
    findings: list[Finding]
    evidence: Evidence


class Replacement(TypedDict):
    text: Optional[str]  # None = keep original (only CONDITION, DISTRICT, GENDER)
    status: Literal["sanitized", "generalized", "suppressed"]


def empty_evidence(record_id: str) -> Evidence:
    return {"record_id": record_id, "names": [], "ids": [], "dob": None, "age": None,
            "gender": None, "village": None, "district": None, "pin": None, "hospital": None}
