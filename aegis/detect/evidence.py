"""Turn one record's findings into the identity clues that `link` uses (contracts/types.md)."""
from __future__ import annotations

import re

from aegis.types import STRONG_ID_TYPES, Evidence, Finding, empty_evidence

_HOSPITALS = (("snj", r"\bSNJ[-/]|sanjeevani"), ("jjh", r"\bJJH[-/]|jeevan ?jyoti"),
              ("asr", r"arogya"), ("dhh", r"\bDHH|district hospital hardoi"))
# file-name hints, only used when the content names no hospital
_HOSPITAL_HINTS = (("snj", "sanjeevani"), ("jjh", "jeevanjyoti"), ("asr", "arogya"), ("dhh", "dhh"))


_MALE_HONORIFIC = r"(?:sahab|saheb|bhai)\b"
_FEMALE_HONORIFIC = r"(?:behenji|behanji|behen|didi|amma)\b"


def _implied_gender(mentions: list[dict], text: str) -> str | None:
    """"S/o" means the patient is a son; "Shahid sahab" is a man, "Anita behenji" a woman."""
    for m in mentions:
        if m["relation"] in ("S/o", "D/o", "W/o"):
            return "M" if m["relation"] == "S/o" else "F"
    for m in mentions:
        if m["role"] == "patient":
            after = rf"{re.escape(m['text'])} +"
            if re.search(after + _MALE_HONORIFIC, text, re.I):
                return "M"
            if re.search(after + _FEMALE_HONORIFIC, text, re.I):
                return "F"
    return None


def hospital_code(text: str, file: str) -> str | None:
    hits = [(m.start(), code) for code, pat in _HOSPITALS for m in [re.search(pat, text, re.I)] if m]
    if hits:
        return min(hits)[1]
    return next((code for code, hint in _HOSPITAL_HINTS if hint in file.casefold()), None)


def build(record_id: str, findings: list[Finding], meta: dict, text: str, file: str) -> Evidence:
    """`meta[(path, start)]` = (script, relation, name_part) for name findings."""
    ev = empty_evidence(record_id)
    names: dict[tuple, dict] = {}
    first, last = [], []
    for f in findings:
        t, norm = f["type"], f["norm"]
        if t in ("PATIENT_NAME", "RELATIVE_NAME") and norm:
            script, relation, part = meta[(f["path"], f["start"])]
            role = "relative" if t == "RELATIVE_NAME" else "patient"
            mention = {"text": f["text"], "norm": norm, "script": script, "role": role,
                       "relation": relation if role == "relative" else None}
            if part == "first_name" and role == "patient":
                first.append(mention)
            elif part == "last_name" and role == "patient":
                last.append(mention)
            else:
                names.setdefault((norm, role), mention)
        elif t in STRONG_ID_TYPES and norm:
            if {"type": t, "norm": norm} not in ev["ids"]:
                ev["ids"].append({"type": t, "norm": norm})
        elif t == "DOB" and ev["dob"] is None:
            ev["dob"] = norm
        elif t == "AGE" and ev["age"] is None and norm:
            ev["age"] = int(norm)
        elif t == "GENDER" and ev["gender"] is None:
            ev["gender"] = norm
        elif t in ("VILLAGE", "DISTRICT", "PIN"):
            key = t.lower()
            if ev[key] is None:
                ev[key] = norm
    # join "first name" + "last name" columns into one mention
    if first or last:
        parts = (first[:1] or []) + (last[:1] or [])
        joined = {"text": " ".join(p["text"] for p in parts), "norm": " ".join(p["norm"] for p in parts),
                  "script": parts[0]["script"], "role": "patient", "relation": None}
        names = {(joined["norm"], "patient"): joined, **names}
    ev["names"] = list(names.values())
    if ev["gender"] is None:
        ev["gender"] = _implied_gender(ev["names"], text)
    ev["hospital"] = hospital_code(text, file)
    return ev
