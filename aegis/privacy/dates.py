"""Per-patient secret date shifting with input-format preservation."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re

_DEVA_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")
_ASCII_TO_DEVA = str.maketrans("0123456789", "०१२३४५६७८९")

_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
_MONTH_FULL = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_LOOKUP: dict[str, int] = {}
for _idx in range(1, 13):
    _MONTH_LOOKUP[_MONTH_ABBR[_idx].casefold()] = _idx
    _MONTH_LOOKUP[_MONTH_FULL[_idx].casefold()] = _idx
_MONTH_LOOKUP["sept"] = 9

# Regexes for supported date/datetime representations
_ISO_DT_RX = re.compile(
    r"^(\d{4})([/-])(\d{1,2})\2(\d{1,2})"
    r"((?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?)$"
)
_NUM_DATE_RX = re.compile(
    r"^(\d{1,2})([/.-])(\d{1,2})\2(\d{2,4})"
    r"((?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)?)$"
)
_DMY_MON_RX = re.compile(
    r"^(\d{1,2})([-\s])([A-Za-z]+)\2(\d{2,4})"
    r"((?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)?)$"
)
_COMPACT_RX = re.compile(r"^((?:18|19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(\d{4}(?:\d{2})?)?$")
_MDY_MON_RX = re.compile(
    r"^([A-Za-z]+)\s+(\d{1,2})(,?\s*)(\d{4})"
    r"((?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)?)$"
)


def shift_days(shift_key: str, secret_bytes: bytes, max_days: int = 180) -> int:
    """Compute a deterministic, non-zero per-key shift in [-max_days, +max_days].

    Uses HMAC-SHA256 domain-separated with ``shift|`` so date shifts differ from
    pseudonym HMACs and change completely under a different RAKSHA_SECRET.
    """
    m = max(1, int(max_days))
    digest = hmac.new(secret_bytes, b"shift|" + shift_key.encode("utf-8"), hashlib.sha256).digest()
    idx = int.from_bytes(digest[:4], "big") % (2 * m)
    return idx - m if idx < m else idx - m + 1


def _parse_norm_iso(norm: str | None) -> dt.date | None:
    if not norm:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", norm.strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _expand_year(y: int, two_digit: bool, ref: dt.date | None) -> int:
    if not two_digit:
        return y
    if ref is not None and ref.year % 100 == y:
        return ref.year
    return 2000 + y if y <= 35 else 1900 + y


def _format_year(year: int, two_digit: bool) -> str:
    return f"{year % 100:02d}" if two_digit else f"{year:04d}"


def _format_month_word(month: int, orig_word: str) -> str:
    is_full = len(orig_word) > 4
    base = _MONTH_FULL[month] if is_full else _MONTH_ABBR[month]
    if orig_word.isupper():
        return base.upper()
    if orig_word.islower():
        return base.lower()
    return base


def _safe_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def shift_date_text(text: str, norm: str | None, offset_days: int) -> str | None:
    """Shift a date or datetime string by ``offset_days`` preserving its exact format.

    Returns ``None`` if the input cannot be parsed and reproduced safely.
    """
    if not text:
        return None
    has_deva = any("\u0966" <= ch <= "\u096f" for ch in text)
    ascii_text = text.translate(_DEVA_TO_ASCII).strip()
    lead_ws = text[: len(text) - len(text.lstrip())]
    trail_ws = text[len(text.rstrip()) :]
    ref_date = _parse_norm_iso(norm)

    shifted_out: str | None = None

    # 1. ISO date / datetime: YYYY-MM-DD[T HH:MM:SS+ZZ:ZZ]
    m = _ISO_DT_RX.match(ascii_text)
    if m:
        y_s, sep, m_s, d_s, suffix = m.groups()
        parsed = ref_date or _safe_date(int(y_s), int(m_s), int(d_s))
        if parsed is not None:
            new_d = parsed + dt.timedelta(days=offset_days)
            ms = f"{new_d.month:02d}" if len(m_s) == 2 else str(new_d.month)
            ds = f"{new_d.day:02d}" if len(d_s) == 2 else str(new_d.day)
            shifted_out = f"{new_d.year:04d}{sep}{ms}{sep}{ds}{suffix}"

    # 2. Numeric DD/MM/YYYY or MM/DD/YYYY (with optional time suffix)
    if shifted_out is None:
        m = _NUM_DATE_RX.match(ascii_text)
        if m:
            p1_s, sep, p2_s, y_s, suffix = m.groups()
            p1, p2, y_raw = int(p1_s), int(p2_s), int(y_s)
            two_digit = len(y_s) == 2
            year = _expand_year(y_raw, two_digit, ref_date)

            if ref_date is not None:
                parsed = ref_date
                is_mdy = (p1 == ref_date.month and p2 == ref_date.day and p1 != p2)
            else:
                if p1 > 12 and p2 <= 12:
                    is_mdy = False
                elif p2 > 12 and p1 <= 12:
                    is_mdy = True
                else:
                    is_mdy = False
                parsed = _safe_date(year, p1, p2) if is_mdy else _safe_date(year, p2, p1)

            if parsed is not None:
                new_d = parsed + dt.timedelta(days=offset_days)
                d_fmt = f"{new_d.day:02d}" if len(p1_s if not is_mdy else p2_s) == 2 else str(new_d.day)
                m_fmt = f"{new_d.month:02d}" if len(p2_s if not is_mdy else p1_s) == 2 else str(new_d.month)
                y_fmt = _format_year(new_d.year, two_digit)
                first, second = (m_fmt, d_fmt) if is_mdy else (d_fmt, m_fmt)
                shifted_out = f"{first}{sep}{second}{sep}{y_fmt}{suffix}"

    # 3. Day-first with month word: 13-Jan-2026 / 13 January 2026
    if shifted_out is None:
        m = _DMY_MON_RX.match(ascii_text)
        if m:
            d_s, sep, mon_word, y_s, suffix = m.groups()
            mon_num = _MONTH_LOOKUP.get(mon_word.casefold())
            if mon_num is not None:
                two_digit = len(y_s) == 2
                year = _expand_year(int(y_s), two_digit, ref_date)
                parsed = ref_date or _safe_date(year, mon_num, int(d_s))
                if parsed is not None:
                    new_d = parsed + dt.timedelta(days=offset_days)
                    d_fmt = f"{new_d.day:02d}" if len(d_s) == 2 else str(new_d.day)
                    mon_fmt = _format_month_word(new_d.month, mon_word)
                    y_fmt = _format_year(new_d.year, two_digit)
                    shifted_out = f"{d_fmt}{sep}{mon_fmt}{sep}{y_fmt}{suffix}"

    # 4. Month-first with month word: Jan 13, 2026 / January 13, 2026
    if shifted_out is None:
        m = _MDY_MON_RX.match(ascii_text)
        if m:
            mon_word, d_s, mid_sep, y_s, suffix = m.groups()
            mon_num = _MONTH_LOOKUP.get(mon_word.casefold())
            if mon_num is not None:
                parsed = ref_date or _safe_date(int(y_s), mon_num, int(d_s))
                if parsed is not None:
                    new_d = parsed + dt.timedelta(days=offset_days)
                    mon_fmt = _format_month_word(new_d.month, mon_word)
                    d_fmt = f"{new_d.day:02d}" if len(d_s) == 2 else str(new_d.day)
                    shifted_out = f"{mon_fmt} {d_fmt}{mid_sep}{new_d.year:04d}{suffix}"

    # 5. Compact YYYYMMDD[HHMM[SS]] (HL7 v2 DT / TS): the shifted date, same length
    if shifted_out is None:
        m = _COMPACT_RX.match(ascii_text)
        if m:
            y_s, m_s, d_s, rest = m.groups()
            parsed = ref_date or _safe_date(int(y_s), int(m_s), int(d_s))
            if parsed is not None:
                new_d = parsed + dt.timedelta(days=offset_days)
                shifted_out = f"{new_d.year:04d}{new_d.month:02d}{new_d.day:02d}{rest or ''}"

    if shifted_out is None:
        return None
    if has_deva:
        shifted_out = shifted_out.translate(_ASCII_TO_DEVA)
    return f"{lead_ws}{shifted_out}{trail_ws}"
