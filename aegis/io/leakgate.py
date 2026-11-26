"""Final leak gate (io-internal safety net).

Every direct identifier that detect found anywhere in the dataset is remembered (in memory
only). Before anything is written, every output value, key, header and file name is scanned
for those values; hits are replaced. This also propagates a phone or Aadhaar found in one file
to every other file where detection missed it. After serialization the text is verified once
more; a file that still contains a known identifier is quarantined instead of written.
"""
from __future__ import annotations

import re
import unicodedata

DIGIT_TYPES = ("PHONE", "AADHAAR", "ABHA_NUMBER", "MRN", "INSURANCE_ID", "OTHER_ID")
LITERAL_TYPES = ("EMAIL", "PAN", "ABHA_ADDRESS", "INSURANCE_ID", "OTHER_ID")
NAME_TYPES = ("PATIENT_NAME", "RELATIVE_NAME")

_DIGIT_RUN = re.compile(r"(?<![0-9०-९])[0-9०-९](?:[0-9०-९]|[ \-./](?=[0-9०-९])){4,}")
_TOKEN = re.compile(r"[\wऀ-ॿ]+")
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
REDACTED = "[REDACTED]"


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def _digits(s: str) -> str:
    return "".join(c for c in s.translate(_DEVA_DIGITS) if c.isdigit())


class LeakGate:
    def __init__(self) -> None:
        self.digits: set[str] = set()
        self.literals: set[str] = set()
        self.names: set[tuple[str, ...]] = set()
        self.hits = 0

    def add(self, ftype: str, text: str, norm: str | None) -> None:
        if ftype in DIGIT_TYPES:
            d = _digits(norm or text)
            if len(d) >= 6:
                self.digits.add(d)
        if ftype in LITERAL_TYPES:
            t = _fold(text).strip()
            if len(t) >= 6 and not t.isdigit():
                self.literals.add(t)
        if ftype in NAME_TYPES:
            toks = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(text))
            if 2 <= len(toks) <= 4 and sum(map(len, toks)) >= 6:
                self.names.add(toks)

    def finalize(self) -> None:
        self._literal_rx = (re.compile("|".join(re.escape(x) for x in sorted(self.literals, key=lambda s: (-len(s), s))),
                                       re.IGNORECASE) if self.literals else None)

    # ------------------------------------------------------------------ scrubbing
    def _digit_hit(self, run: str) -> bool:
        d = _digits(run)
        return d in self.digits or (len(d) > 10 and d[-10:] in self.digits) or (len(d) > 6 and d[-6:] in self.digits and len(d) <= 8)

    def scrub(self, value: str) -> str:
        """Return value with every known identifier replaced."""
        if not value:
            return value
        out = value
        if self.digits:
            out = _DIGIT_RUN.sub(lambda m: self._count(REDACTED) if self._digit_hit(m.group(0)) else m.group(0), out)
        if self._literal_rx is not None:
            out = self._literal_rx.sub(lambda m: self._count(REDACTED), out)
        if self.names:
            out = self._scrub_names(out)
        return out

    def _count(self, s: str) -> str:
        self.hits += 1
        return s

    def _scrub_names(self, value: str) -> str:
        toks = [(m.start(), m.end(), _fold(m.group(0))) for m in _TOKEN.finditer(value)]
        spans, i = [], 0
        while i < len(toks):
            for n in (4, 3, 2):
                if i + n <= len(toks) and tuple(t[2] for t in toks[i:i + n]) in self.names:
                    spans.append((toks[i][0], toks[i + n - 1][1]))
                    i += n
                    break
            else:
                i += 1
        for s, e in reversed(spans):
            value = value[:s] + REDACTED + value[e:]
            self.hits += 1
        return value

    # ------------------------------------------------------------------ verification
    def contains_leak(self, text: str) -> bool:
        if self.digits and any(self._digit_hit(m.group(0)) for m in _DIGIT_RUN.finditer(text)):
            return True
        if self._literal_rx is not None and self._literal_rx.search(text):
            return True
        if self.names:
            before = self.hits
            scrubbed = self._scrub_names(text)
            self.hits = before
            return scrubbed != text
        return False
