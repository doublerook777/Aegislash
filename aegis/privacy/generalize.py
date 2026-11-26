"""Quasi-identifier generalization (ages, PINs, locations) and risk tiering."""
from __future__ import annotations

import re

_DEVA_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")
_AGE_NUM_RX = re.compile(r"^([^\d-]*)(-?\d+)(.*)$")


def parse_age_int(text: str, norm: str | None = None) -> int | None:
    """Extract integer age from normalized or raw finding text."""
    for candidate in (norm, text):
        if not candidate:
            continue
        cleaned = candidate.translate(_DEVA_TO_ASCII).strip()
        m = re.search(r"(-?\d+)", cleaned)
        if m:
            return int(m.group(1))
    return None


def generalize_age(
    text: str,
    norm: str | None,
    band_width: int = 5,
    elderly_threshold: int = 85,
) -> tuple[str, str]:
    """Return ``(replacement_text, status)`` preserving style (e.g. ``48/M`` -> ``45-49/M``)."""
    age = parse_age_int(text, norm)
    if age is None or age < 0 or age > 130:
        return "[AGE]", "suppressed"

    if age >= elderly_threshold:
        band_str = f"{elderly_threshold}+"
    else:
        w = max(1, int(band_width))
        lo = (age // w) * w
        hi = min(elderly_threshold - 1, lo + w - 1) if elderly_threshold > 0 else lo + w - 1
        band_str = f"{lo}-{hi}"

    ascii_text = text.translate(_DEVA_TO_ASCII)
    m = _AGE_NUM_RX.match(ascii_text)
    if m:
        prefix, num_s, suffix = m.groups()
        raw_prefix = text[: len(prefix)]
        raw_suffix = text[len(prefix) + len(num_s) :] if len(text) >= len(prefix) + len(num_s) else suffix
        return f"{raw_prefix}{band_str}{raw_suffix}", "generalized"
    return band_str, "generalized"


def generalize_pin(text: str, suppress: bool = False) -> tuple[str, str]:
    """Generalize a 6-digit PIN to ``XXX***``, or suppress to ``[PIN]``."""
    if suppress:
        return "[PIN]", "suppressed"
    digits = "".join(ch for ch in text.translate(_DEVA_TO_ASCII) if ch.isdigit())
    if len(digits) < 3:
        return "[PIN]", "suppressed"
    return f"{digits[:3]}***", "generalized"


def _title_place(name: str) -> str:
    return " ".join(w.capitalize() for w in name.strip().split())


def generalize_village(district: str | None, suppress: bool = False) -> tuple[str, str]:
    """Generalize a village name to its district name if available, else ``[VILLAGE]``."""
    if not suppress and district and district.strip():
        return _title_place(district), "generalized"
    return "[VILLAGE]", "suppressed"
