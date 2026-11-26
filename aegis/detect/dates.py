"""Dates, date of birth and age.

A file is either day-first or month-first. We decide once per file from every date in it
(a 13+ in one position settles it), so "03/04/2026" is read correctly.
"""
from __future__ import annotations

import datetime as _dt
import re

from aegis.detect.spans import Cand

_MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
_MONTH_RE = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
             r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")

_YEAR = r"(?:18|19|20)\d{2}"
ISO = re.compile(r"(?<![\d])(" + _YEAR + r")-(\d{1,2})-(\d{1,2})(?!\d)")
YMD_SLASH = re.compile(r"(?<![\d/])(" + _YEAR + r")([/.])(\d{1,2})\2(\d{1,2})(?![\d/])")
NUMERIC = re.compile(r"(?<![\d./-])(\d{1,2})([/.-])(\d{1,2})\2(" + _YEAR + r"|\d{2})(?![\d/-]|\.\d)")
# "12 Mar 1830 hrs" is a time of day, not the year 1830 (only the 18xx years need this guard: they never were dates here)
_YEAR_WORDS = r"(?:(?:19|20)\d{2}|18\d{2}(?! ?(?:hrs?\b|hours|h\b))|'?\d{2})"
TEXT_DMY = re.compile(r"(?<![\d])(\d{1,2})(?:st|nd|rd|th)?[ -](" + _MONTH_RE + r")\b\.?(?:[ ,-]+(" + _YEAR_WORDS + r")(?!\d))?", re.I)
TEXT_MDY = re.compile(r"\b(" + _MONTH_RE + r")\.? (\d{1,2})(?:st|nd|rd|th)?(?!\d)(?:,? ((?:19|20)\d{2}|18\d{2}(?! ?(?:hrs?\b|hours|h\b))))?", re.I)

_DOB_BEFORE = re.compile(r"(?:\bd\.?o\.?b\b|date of birth|birth ?date|\bborn(?: on)?\b|जन्म[^\n:]{0,20})\W{0,6}$", re.I)


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return _dt.date(y, m, d).isoformat()
    except ValueError:
        return None


def _year(s: str) -> int:
    y = int(s.lstrip("'"))
    return y if y > 99 else (2000 + y if y <= 40 else 1900 + y)


def day_first(texts: list[str], hints: list[str]) -> bool:
    """True = 12/04 means 12 April. `hints` are headers such as 'DOB (MM/DD/YYYY)'."""
    for h in hints:
        h = h.upper()
        if "MM/DD" in h or "MM-DD-Y" in h:
            return False
        if "DD/MM" in h or "DD-MM" in h:
            return True
    dmy = mdy = 0
    for t in texts:
        for m in NUMERIC.finditer(t):
            a, b = int(m.group(1)), int(m.group(3))
            dmy += a > 12 >= b
            mdy += b > 12 >= a
    return dmy >= mdy


def parse_dates(text: str, dmy: bool) -> list[tuple[int, int, str]]:
    """(start, end, ISO) for every full date in folded text."""
    out = []
    for m in ISO.finditer(text):
        iso = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            out.append((m.start(), m.end(), iso))
    for m in YMD_SLASH.finditer(text):
        iso = _iso(int(m.group(1)), int(m.group(3)), int(m.group(4)))
        if iso:
            out.append((m.start(), m.end(), iso))
    for m in NUMERIC.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(3)), _year(m.group(4))
        if m.group(2) == "." and len(m.group(4)) == 2:
            continue  # version numbers and decimals
        d, mo = (a, b) if dmy else (b, a)
        iso = _iso(y, mo, d) or _iso(y, d, mo)
        if iso:
            out.append((m.start(), m.end(), iso))
    for m in TEXT_DMY.finditer(text):
        y = _year(m.group(3)) if m.group(3) else 2026
        iso = _iso(y, _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        if iso:
            out.append((m.start(), m.end(), iso))
    for m in TEXT_MDY.finditer(text):
        y = int(m.group(3)) if m.group(3) else 2026
        iso = _iso(y, _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        if iso:
            out.append((m.start(), m.end(), iso))
    return out


def find_dates(text: str, dmy: bool, is_dob_field: bool = False) -> list[Cand]:
    out = []
    for s, e, iso in parse_dates(text, dmy):
        dob = is_dob_field or bool(_DOB_BEFORE.search(text[max(0, s - 40):s]))
        out.append(Cand(s, e, "DOB" if dob else "DATE", iso, "patient" if dob else None))
    return out


_SEX = r"(?:male|female|transgender|other|पुरुष|महिला|[MF])"
AGE_PATTERNS = [
    # "52 Yrs/F", "27 yrs, female", "48 Y / F", "65/F", "47 वर्ष / महिला"
    re.compile(r"(?<![\d./-])(\d{1,3}) ?(?:yrs?\.?|years?|y|वर्ष|साल)? ?[/,|] ?" + _SEX + r"(?![A-Za-z])", re.I),
    re.compile(r"(?<![\d./-])(\d{1,3})[- ]?(?:year|yr)s?[- ]old", re.I),
    re.compile(r"\b(?:aged|age) ?:?[- ]?(\d{1,3})(?![\d./-])", re.I),
    re.compile(r"(?:आयु|उम्र) ?:? ?(\d{1,3})(?!\d)"),
]


def find_ages(text: str) -> list[Cand]:
    out = []
    for p in AGE_PATTERNS:
        for m in p.finditer(text):
            if 0 < int(m.group(1)) <= 120:
                out.append(Cand(m.start(1), m.end(1), "AGE", str(int(m.group(1))), "patient"))
    return out
