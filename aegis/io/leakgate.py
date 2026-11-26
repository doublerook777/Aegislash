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

from aegis.detect.normalize import decode_view
from aegis.io.formats import find_runs

DIGIT_TYPES = ("PHONE", "AADHAAR", "ABHA_NUMBER", "MRN", "INSURANCE_ID", "OTHER_ID")
LITERAL_TYPES = ("EMAIL", "PAN", "ABHA_ADDRESS", "INSURANCE_ID", "OTHER_ID")
NAME_TYPES = ("PATIENT_NAME", "RELATIVE_NAME")

_DIGIT_RUN = re.compile(r"(?<![0-9०-९])[0-9०-९](?:[0-9०-९]|[ \-./](?=[0-9०-९])){4,}")
# a word is letters/digits/Devanagari; "_" separates words ("Agustín_Fonseca" in a file name is two words)
_TOKEN = re.compile(r"(?:[^\W_]|[ऀ-ॿ])+")
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
            toks = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(decode_view(text)[0]))
            if 2 <= len(toks) <= 4 and sum(map(len, toks)) >= 6:
                self.names.add(toks)
                # "Fonseca, Agustín" (surname first) is also written "Agustín Fonseca"
                last, comma, given = decode_view(text)[0].partition(",")
                if comma:
                    rest = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(given))
                    head = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(last))
                    if rest and head and len(rest + head) <= 4:
                        self.names.add(rest + head)

    def finalize(self) -> None:
        self._literal_rx = (re.compile("|".join(re.escape(x) for x in sorted(self.literals, key=lambda s: (-len(s), s))),
                                       re.IGNORECASE) if self.literals else None)

    # ------------------------------------------------------------------ scrubbing
    def _digit_hit(self, run: str) -> bool:
        d = _digits(run)
        return d in self.digits or (len(d) > 10 and d[-10:] in self.digits) or (len(d) > 6 and d[-6:] in self.digits and len(d) <= 8)

    def scrub(self, value: str) -> str:
        """Return value with every known identifier replaced. Escapes ("%20", "\\u0932", "&#2354;") are read first and a
        hit is replaced as a whole, escape sequences included."""
        if not value:
            return value
        out = value
        if self.digits:
            out = self._replace(out, self._digit_spans)
        if self._literal_rx is not None:
            out = self._replace(out, lambda t: [m.span() for m in self._literal_rx.finditer(t)])
        if self.names:
            out = self._replace(out, self._name_spans)
        return out

    def _replace(self, value: str, find) -> str:
        text, spans = decode_view(value)
        found = find(text)
        if not found:
            return value
        if spans is not None:
            found = [(spans[s][0], spans[e - 1][1]) for s, e in found]
        last = len(value) + 1
        for s, e in reversed(found):
            if e > last:
                continue
            value = value[:s] + REDACTED + value[e:]
            last = s
            self.hits += 1
        return value

    def _digit_spans(self, text: str) -> list[tuple[int, int]]:
        return [m.span() for m in _DIGIT_RUN.finditer(text) if self._digit_hit(m.group(0))]

    def _name_spans(self, text: str) -> list[tuple[int, int]]:
        toks = [(m.start(), m.end(), _fold(m.group(0))) for m in _TOKEN.finditer(text)]
        spans, i = [], 0
        while i < len(toks):
            for n in (4, 3, 2):
                if i + n <= len(toks) and tuple(t[2] for t in toks[i:i + n]) in self.names:
                    spans.append((toks[i][0], toks[i + n - 1][1]))
                    i += n
                    break
            else:
                i += 1
        return spans

    # ------------------------------------------------------------------ verification
    def contains_leak(self, text: str) -> bool:
        """True when a known identifier is in `text`, also inside escapes and inside a base64 run of readable text."""
        view = decode_view(text)[0]
        if self.digits and self._digit_spans(view):
            return True
        if self._literal_rx is not None and self._literal_rx.search(view):
            return True
        if self.names and self._name_spans(view):
            return True
        return any(self.contains_leak(dec) for _a, _b, dec, _f in find_runs(text))
