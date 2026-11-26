"""HL7 v2 messages saved as plain text: a field gets its role from its segment and position, not from words.

A message is a run of segments (PID|..., NK1|...) separated by \\r, \\n or \\r\\n; it starts with "MSH|" followed by the
encoding characters (default "^~\\&": component, repetition, escape, sub-component). Every field is split on "|", each
repetition on "~", each component on "^", each sub-component on "&". Only the fields below carry personal data; MSH,
OBR / OBX values, codes, units, ranges, PV1 locations and time stamps are never touched. Candidates cover single
components, so the separators stay where they are and the segment keeps its number of fields.
"""
from __future__ import annotations

import re

from aegis.detect import ids
from aegis.detect.normalize import digits, norm_name
from aegis.detect.spans import PRIORITY, Cand

_START = re.compile(r"(?:^|[\r\n\x0b])[ \t]*MSH\|", re.M)
_SEGMENT = re.compile(r"[^\r\n\x0b\x1c]+")
_SEG_NAME = re.compile(r"[A-Z][A-Z0-9]{2}\|")
_DEFAULT_ENC = "^~\\&"

# segment -> {field number: what the field holds}
#   id: CX identifier list      name / kin: XPN name (patient / relative)     addr: XAD      phone: XTN
#   dob: date of birth          sex: administrative sex                      natid: national id (SSN, licence)
#   place: birth place          policy: insurance policy / member number
# (a guarantor or an insured person is written as a relative: the patient is not known to be the same person)
_FIELDS = {
    "PID": {2: "id", 3: "id", 4: "id", 5: "name", 6: "kin", 7: "dob", 8: "sex", 9: "name", 11: "addr",
            13: "phone", 14: "phone", 19: "natid", 20: "natid", 23: "place"},
    "NK1": {2: "kin", 4: "addr", 5: "phone", 6: "phone", 16: "dob"},
    "GT1": {3: "kin", 4: "kin", 5: "addr", 6: "phone", 7: "phone", 12: "natid", 19: "dob"},
    "IN1": {16: "kin", 18: "dob", 19: "addr", 36: "policy", 49: "id"},
    "IN2": {2: "natid", 63: "policy"},
}
_HIGH = 200     # above every free-text rule: the position in the segment is the strongest evidence there is
_NAME_LABEL = {"name": ("PATIENT_NAME", "patient"), "kin": ("RELATIVE_NAME", "relative")}
_ID_SHAPES = ("AADHAAR", "ABHA_NUMBER", "PAN", "INSURANCE_ID")


def is_message(text: str) -> bool:
    return "MSH|" in text and _START.search(text) is not None


def _pieces(text: str, start: int, end: int, sep: str):
    """(start, end) of each part of text[start:end] split on `sep`."""
    pos = start
    for part in text[start:end].split(sep):
        yield pos, pos + len(part)
        pos += len(part) + 1


def _cand(typ: str, s: int, e: int, text: str, norm=None, who: str | None = "patient") -> Cand:
    return Cand(s, e, typ, norm, who, prio=_HIGH + PRIORITY[typ] // 10)


def _trim(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def _identifier(text: str, s: int, e: int, other: str) -> list[Cand]:
    value = text[s:e]
    if not re.search(r"[A-Za-z0-9]{2}", value):
        return []
    shaped = [c for c in ids.find_ids(value) if c.type in _ID_SHAPES and c.start == 0 and c.end == len(value)]
    if shaped:
        c = shaped[0]
        return [_cand(c.type, s, e, text, c.norm)]
    d = digits(value)
    return [_cand(other, s, e, text, d if len(d) >= 4 else re.sub(r"[^A-Z0-9]", "", value.upper()))]


def _names(text: str, s: int, e: int, kind: str, seps: tuple[str, str, str, str]) -> list[Cand]:
    """XPN: family^given^middle (suffix, prefix and degree are titles, not names). One candidate per word."""
    comp, rep, _esc, sub = seps
    typ, who = _NAME_LABEL[kind]
    out: list[Cand] = []
    for rs, re_ in _pieces(text, s, e, rep):
        parts = list(_pieces(text, rs, re_, comp))[:3]      # family, given, middle
        words = [[_trim(text, a, b) for a, b in _pieces(text, cs, ce, sub)] for cs, ce in parts]
        words = [[(a, b) for a, b in comp_words if b > a and re.search(r"[^\W\d_]", text[a:b])] for comp_words in words]
        if not any(words):
            continue
        # given names first, the way the evidence and the rest of the file write them
        given_first = [*words[1:], words[0]]
        full = norm_name(" ".join(text[a:b] for ws in given_first for a, b in ws)) or None
        out += [Cand(a, b, typ, None, who, prio=_HIGH + PRIORITY[typ] // 10, full_name=full)
                for ws in words for a, b in ws]
    return out


def _dob(text: str, s: int, e: int) -> list[Cand]:
    m = re.match(r"(\d{4})(\d{2})?(\d{2})?", text[s:e])
    if not m:
        return []
    y, mo, d = m.groups()
    end = s + m.end()
    norm = f"{y}-{mo}-{d}" if mo and d and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 else None
    return [_cand("DOB", s, end, text, norm)]


def _address(text: str, s: int, e: int, seps, who: str) -> list[Cand]:
    """XAD: street^other designation^city^state^zip^country (state and country stay)."""
    comp, rep, _esc, _sub = seps
    out: list[Cand] = []
    for rs, re_ in _pieces(text, s, e, rep):
        for i, (cs, ce) in enumerate(_pieces(text, rs, re_, comp)):
            a, b = _trim(text, cs, ce)
            if b <= a or i not in (0, 1, 2, 4):
                continue
            value = text[a:b]
            if i == 4:
                m = re.search(r"(?<!\d)[1-9]\d{2} ?\d{3}(?!\d)", value)
                if m:
                    out.append(_cand("PIN", a + m.start(), a + m.end(), text, m.group(0).replace(" ", ""), who))
                elif re.search(r"[A-Za-z0-9]{3}", value):
                    out.append(_cand("PIN", a, b, text, None, who))
            elif re.search(r"[^\W_]{2}", value):
                out.append(_cand("HOUSE" if i == 0 else "LOCALITY", a, b, text, None, who))
    return out


def _phones(text: str, s: int, e: int, seps, who: str) -> list[Cand]:
    """XTN: number^use^equipment^email^country^area^local^extension."""
    comp, rep, _esc, _sub = seps
    out: list[Cand] = []
    for rs, re_ in _pieces(text, s, e, rep):
        for i, (cs, ce) in enumerate(_pieces(text, rs, re_, comp)):
            a, b = _trim(text, cs, ce)
            if b <= a or i not in (0, 3, 5, 6):
                continue
            value = text[a:b]
            if i == 3 or "@" in value:
                if "@" in value:
                    out.append(_cand("EMAIL", a, b, text, value.casefold(), who))
            elif len(digits(value)) >= 5 or (i == 6 and len(digits(value)) >= 4):
                out.append(_cand("PHONE", a, b, text, ids.phone_norm(value), who))
    return out


# YYYYMMDDHHMM[SS][.S+][+ZZZZ] with real month, day, hour and minute: a time stamp, not a 12-digit identifier
_STAMP = re.compile(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-3])[0-5]\d(?:[0-5]\d(?:\.\d+)?)?"
                    r"(?:[+-]\d{4})?")


def find(text: str) -> tuple[list[Cand], list[tuple[int, int]]]:
    """(candidates for the personal data of an HL7 v2 message, spans of its time stamps). `text` is the message,
    with any segment separator. A field the message gives no role to, that is a time stamp, is not an identifier."""
    out: list[Cand] = []
    stamps: list[tuple[int, int]] = []
    seps = ("^", "~", "\\", "&")
    seen_msh = False
    for line in _SEGMENT.finditer(text):
        start, end = line.start(), line.end()
        while start < end and text[start] in " \t":
            start += 1
        seg = text[start:end]
        if seg.startswith("MSH|"):
            seen_msh = True
            enc = seg[4:].split("|", 1)[0]
            if len(enc) >= 4 and len(set(enc[:4])) == 4 and "|" not in enc[:4]:
                seps = (enc[0], enc[1], enc[2], enc[3])
            pos = start
            for field in seg.split("|"):
                if _STAMP.fullmatch(field):
                    stamps.append((pos, pos + len(field)))
                pos += len(field) + 1
            continue
        if not seen_msh or not _SEG_NAME.match(seg):
            continue
        wanted = _FIELDS.get(seg[:3], {})
        pos = start + 4
        for n, field in enumerate(seg[4:].split("|"), start=1):
            fs, fe = pos, pos + len(field)
            pos = fe + 1
            kind = wanted.get(n)
            if (kind is None or not field.strip()) and _STAMP.fullmatch(field):
                stamps.append((fs, fe))
            if kind is None or not field.strip():
                continue
            if kind == "id":
                for rs, re_ in _pieces(text, fs, fe, seps[1]):
                    cs, ce = next(_pieces(text, rs, re_, seps[0]))
                    out += _identifier(text, *_trim(text, cs, ce), "MRN")
            elif kind == "policy":
                out += _identifier(text, *_trim(text, fs, fe), "INSURANCE_ID")
            elif kind == "natid":
                out += _identifier(text, *_trim(text, fs, fe), "OTHER_ID")
            elif kind in _NAME_LABEL:
                out += _names(text, fs, fe, kind, seps)
            elif kind == "dob":
                out += _dob(text, *_trim(text, fs, fe))
            elif kind == "sex":
                v = field.strip().casefold()
                if v in ("m", "f", "male", "female"):
                    a, b = _trim(text, fs, fe)
                    out.append(Cand(a, b, "GENDER", v[0].upper(), "patient", prio=_HIGH))
            elif kind == "addr":
                out += _address(text, fs, fe, seps, "relative" if seg[:3] in ("NK1", "GT1") else "patient")
            elif kind == "phone":
                out += _phones(text, fs, fe, seps, "relative" if seg[:3] in ("NK1", "GT1") else "patient")
            elif kind == "place":
                a, b = _trim(text, fs, fe)
                if re.search(r"[^\W\d_]{3}", text[a:b]):
                    out.append(_cand("LOCALITY", a, b, text))
    return out, stamps
