"""Identifiers found by their shape: phone, Aadhaar, ABHA, PAN, email, insurance, MRN.

All functions take *folded* text (see normalize.fold), so Devanagari digits work too.
Boundaries use "not a letter or digit" instead of \\b, so file names with "_" still match.
"""
from __future__ import annotations

import re

from aegis.detect.normalize import digits
from aegis.detect.spans import PRIORITY, Cand

_L = r"(?<![A-Za-z0-9])"   # left boundary
_R = r"(?![A-Za-z0-9])"    # right boundary

EMAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ABHA_ADDR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._]*@(?:abdm|sbx|ndhm|abha)" + _R, re.I)
ABHA_NUM = re.compile(_L + r"\d{2}([- ])\d{4}\1\d{4}\1\d{4}(?!\d)")
AADHAAR_MASKED = re.compile(r"(?<![A-Za-z0-9])(?:[Xx*•]{4}[- ]?){2}\d{4}(?!\d)")
# grouped 4-4-4 (the two separators may differ: "1234-5678 9012") or not grouped at all
AADHAAR = re.compile(_L + r"(?<![\d][- /.])[2-9]\d{3}(?:[- ]\d{4}[- ]\d{4}|\d{8})(?![- /.]?\d)" + _R)
PAN = re.compile(_L + r"[A-Z]{5}\d{4}[A-Z]" + _R, re.I)
INSURANCE = re.compile(
    _L + r"(?:[A-Z]{2,10}-POL(?:[-/]\d+){1,4}|PMJAY(?:[-/ ]?[A-Z]{2,3})?(?:[-/]\d{2,4})?[-/ ]?\d{6,}"
    r"|(?:POL|POLICY|INS|TPA|MEDI|CGHS|ESIC?)(?:[-/][A-Z]{2,5})?(?:[-/]\d+){1,4})" + _R, re.I)

_PHONE_BODY = (r"(?:[6-9]\d{4}[- .]?\d{5}"            # 98765 43210
               r"|[6-9]\d{2}[- .]\d{3}[- .]\d{4}"      # 987-654-3210
               r"|[6-9]\d{3}[- .]\d{3}[- .]\d{3}"       # 9876-543-210
               r"|[6-9]\d\.\d{2}\.\d{2}\.\d{4}"            # 98.76.54.3210
               r"|[6-9]\d(?: \d{2}){4}"                          # 98 76 54 32 10
               r"|[6-9]\d(?:\.\d{2}){4})")                      # 98.76.54.32.10
PHONE = re.compile(r"(?<![A-Za-z0-9])(?:(?:\(\+?91\)|\+91|0091|91(?=[- ])|0)[- .]{0,2})?"
                   + _PHONE_BODY + r"(?!\d|[-/]\d|[A-Za-z])")

# "(912) 455-7781", "934/221/6650": brackets round the first three digits, or slashes between 3-3-4
PHONE_GROUPED = re.compile(r"(?<![A-Za-z0-9/])(?:\+91[- .]?)?(?:\([6-9]\d{2}\)[- .]?\d{3}[- .]?\d{4}|[6-9]\d{2}/\d{3}/\d{4})"
                           r"(?!\d|[-/]\d|[A-Za-z])")
# after "+91" the ten digits may be grouped any way: "+91/9788/002233"
PHONE_INTL = re.compile(r"(?<![A-Za-z0-9])\+91[- ./]{0,2}[6-9](?:[- ./]?\d){9}(?!\d|[-/]\d|[A-Za-z])")
# landlines: an STD code starting with 0, then the number, 10 or 11 digits in all
# ("0512-2345678", "(0581) 456789", "022 2567 8901")
LANDLINE = re.compile(r"(?<![A-Za-z0-9/.-])(?:\(0[1-9]\d{1,3}\)[- ]?\d{6,8}|0[1-9]\d{1,3}-\d{6,8}"
                      r"|0[1-9]\d[- ]\d{4}[- ]\d{4})(?!\d|[-/.]\d|[A-Za-z])")

# hospital record numbers. Bill / visit / sample / claim numbers are NOT patient identifiers.
_NOT_MRN_PREFIX = {"BL", "BILL", "INV", "OPD", "OP", "AMB", "HD", "LAB", "POL", "PMJAY", "TPA", "INS", "REF", "VISIT",
                   "RX", "RPT", "CLM", "ORD", "TXN", "DOC", "ICD", "COVID", "LOINC", "ISO", "FHIR"}
MRN_SHAPES = [
    # "IP#NICU-26-419"; and hospital/branch/year/number: "APH/PUN/26/88104"
    re.compile(_L + r"(?:IP|IPD|UHID)#(?=(?:[A-Z/-]*\d){3})(?:[A-Z0-9]{1,6}[-/]){0,4}\d{3,}" + _R, re.I),
    re.compile(_L + r"[A-Z]{2,5}/[A-Z]{2,5}/(?:\d{2}|\d{4})/\d{4,8}(?![-/]?\d)" + _R),
    # a record-number prefix, then any mix of short blocks: MRN-BLR-77102, IPD#26/88310, MRN#KMC-44812-A, IPD-2023-045
    re.compile(_L + r"(?:UHID|MRN|MRD|CRN|IPD)(?:#[ ]?|[-/])(?=(?:[A-Z/-]*\d){4})(?:[A-Z0-9]{1,6}[-/]){0,4}\d{3,}"
               r"(?:[-/][A-Z](?![A-Za-z0-9]))?" + _R, re.I),
    re.compile(_L + r"[A-Z]{2,5}[-/ ]?(?:IPD|IP|UHID|MRN|CR|REG)[-/ ]?(?:\d{2,4}[-/])?\d{4,}(?![-/]?\d)" + _R, re.I),
    re.compile(_L + r"(?:UHID|MRN|MRD|CRN|CR|REG|IPD|IP|ADM)(?:[-/ ]?(?:NO|ID)\.?)?[-/ ]?(?:\d{2,4}[-/])?\d{5,}(?![-/]?\d)" + _R, re.I),
    re.compile(_L + r"[A-Z]{2,5}[/-](?:\d{2}|\d{4})[/-]\d{4,8}(?![-/]?\d)" + _R),
    re.compile(_L + r"[A-Z]{3,5}(?:19|20)\d{2}[-/]\d{4,}" + _R),
    re.compile(_L + r"[A-Z]{3,5}[-/]\d{6,}(?![-/]?\d)" + _R),
]


# A number announced by its label, whatever its format ("Rec# : HOSP/2023/07/00123", "Aadhaar No: 1111-2222-3333").
_SEP = r"\.?\s*[:#=\-]*\s*"
_LABELLED = [
    ("MRN", re.compile(
        r"(?<![A-Za-z])(?i:uhid|mrn|c\.? ?r\.? ?no|reg(?:istration|n)?\.? ?(?:no|id|number)|rec(?:ord)?\.? ?(?:no#?|id|#)"
        r"|hosp(?:ital)?\.? ?(?:no|id)|pt\.? ?id|patient (?:id|no)|ipd? ?no|admission (?:no|number)|file no)" + _SEP
        + r"(?P<v>#?(?=[A-Za-z/\-]*\d[A-Za-z/\-]*\d)[A-Za-z0-9](?:[A-Za-z0-9/\-]{1,28}[A-Za-z0-9]))")),
    ("MRN", re.compile(r"(?:आईपीडी|आईपी|यूएचआईडी|पंजीकरण)(?: ?(?:नंबर|नं\.?|संख्या|क्रमांक))?" + _SEP
                       + r"(?P<v>(?=[A-Z/\-]*\d(?:[A-Z/\-]*\d){2})[A-Z0-9](?:[A-Z0-9/\-]{1,28}[A-Z0-9]))")),
    ("AADHAAR", re.compile(r"(?:(?i:aadh?aa?r|adhar)|आधार)(?i: ?(?:card)? ?(?:no|number|id)?)" + _SEP
                           + r"(?P<v>\d{4}[ -]?\d{4}[ -]?\d{4})(?!\d)")),
    ("ABHA_NUMBER", re.compile(r"(?:(?i:abha|health ?id)|एबीएचए)(?i: ?(?:id|no|number)?)" + _SEP
                               + r"(?P<v>\d(?:[ -]?\d){11,15})(?!\d)")),
    ("PHONE", re.compile(r"(?:(?<![A-Za-z])(?i:mob(?:ile)?|ph(?:one)?|contact(?: no)?|tel|whatsapp|call(?:ed)? on)"
                         r"|मोबाइल|फ़ोन|फोन|संपर्क|\((?:H|M|R|O)(?=:))" + _SEP + r"(?P<v>\+?\d(?:[ .\-/]?\d){9,12})(?!\d)")),
]


def _verhoeff_ok(num: str) -> bool:
    d = ("0123456789", "1234067895", "2340178956", "3401289567", "4012395678",
         "5987604321", "6598710432", "7659821043", "8765932104", "9876543210")
    p = ("0123456789", "1576283094", "5803796142", "8916043527", "9453126870",
         "4286573901", "2793806415", "7046913258")
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = int(d[c][int(p[i % 8][int(ch)])])
    return c == 0


def phone_norm(s: str) -> str:
    d = digits(s)
    return d[-10:] if len(d) > 10 else d


def find_ids(text: str) -> list[Cand]:
    out: list[Cand] = []
    for m in ABHA_ADDR.finditer(text):
        out.append(Cand(m.start(), m.end(), "ABHA_ADDRESS", m.group(0).casefold()))
    for m in EMAIL.finditer(text):
        end = m.end() - 1 if m.group(0).endswith(".") else m.end()
        out.append(Cand(m.start(), end, "EMAIL", text[m.start():end].casefold()))
    for m in ABHA_NUM.finditer(text):
        out.append(Cand(m.start(), m.end(), "ABHA_NUMBER", digits(m.group(0))))
    for m in AADHAAR_MASKED.finditer(text):
        out.append(Cand(m.start(), m.end(), "AADHAAR_MASKED", digits(m.group(0))))
    for m in AADHAAR.finditer(text):
        d = digits(m.group(0))
        # "91 + mobile" is also 12 digits: only call it Aadhaar if grouped 4-4-4 or the checksum fits
        looks_phone = d.startswith("91") and d[2] in "6789" and m.group(0).isdigit() and not _verhoeff_ok(d)
        if not looks_phone:
            out.append(Cand(m.start(), m.end(), "AADHAAR", d))
    for kind, pattern in _LABELLED:
        for m in pattern.finditer(text):
            value = m.group("v")
            norm = phone_norm(value) if kind == "PHONE" else digits(value)
            out.append(Cand(m.start("v"), m.end("v"), kind, norm, "patient"))
    for m in PAN.finditer(text):
        out.append(Cand(m.start(), m.end(), "PAN", m.group(0).upper()))
    for m in INSURANCE.finditer(text):
        out.append(Cand(m.start(), m.end(), "INSURANCE_ID", re.sub(r"[^A-Z0-9]", "", m.group(0).upper())))
    for m in PHONE.finditer(text):
        out.append(Cand(m.start(), m.end(), "PHONE", phone_norm(m.group(0))))
    for m in PHONE_GROUPED.finditer(text):
        out.append(Cand(m.start(), m.end(), "PHONE", phone_norm(m.group(0))))
    for m in PHONE_INTL.finditer(text):
        out.append(Cand(m.start(), m.end(), "PHONE", phone_norm(m.group(0))))
    for m in LANDLINE.finditer(text):
        d = digits(m.group(0))
        if 10 <= len(d) <= 11:
            out.append(Cand(m.start(), m.end(), "PHONE", phone_norm(m.group(0))))
    # a 12-digit mobile written without "+": 919876543210
    for m in re.finditer(_L + r"91[6-9]\d{9}(?!\d)", text):
        out.append(Cand(m.start(), m.end(), "PHONE", m.group(0)[2:], prio=PRIORITY["AADHAAR"] - 1))
    for shape in MRN_SHAPES:
        for m in shape.finditer(text):
            prefix = re.match(r"[A-Za-z]+", m.group(0)).group(0).upper()
            if prefix in _NOT_MRN_PREFIX:
                continue
            # "DHH-IPD-00591" must not also yield a "BL/26/..." style sub-match from inside a bill number
            before = text[:m.start()].rstrip("-/")
            if re.search(r"(?:BL|OPD|OP|BILL|INV)$", before, re.I):
                continue
            out.append(Cand(m.start(), m.end(), "MRN", digits(m.group(0))))
    return out
