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

from aegis.detect.normalize import decode_view, fold, visible
from aegis.io.formats import find_runs

DIGIT_TYPES = ("PHONE", "AADHAAR", "ABHA_NUMBER", "MRN", "INSURANCE_ID", "OTHER_ID")
LITERAL_TYPES = ("EMAIL", "PAN", "ABHA_ADDRESS", "INSURANCE_ID", "OTHER_ID")
NAME_TYPES = ("PATIENT_NAME", "RELATIVE_NAME")

_DIGIT_RUN = re.compile(r"(?<![0-9०-९])[0-9०-९](?:[0-9०-९]|[ \-./](?=[0-9०-९])){4,}")
_UUID_RX = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_ISO_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# a word is letters/digits/Devanagari; "_" separates words ("Agustín_Fonseca" in a file name is two words)
_TOKEN = re.compile(r"(?:[^\W_]|[ऀ-ॿ])+")
# a name right after a doctor's title ("Dr. R. Suresh Pandey") is the doctor, who is kept; detect protects the same span
_DOCTOR_TITLE = re.compile(r"(?:\b(?:dr|doctor|prof)\b\.?|डॉ\.?|डा\.|डॉक्टर)[ \t]*(?:[A-Za-z]\.[ \t]*){0,2}$", re.IGNORECASE)
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_MAX_NAME_TOKENS = 8
REDACTED = "[REDACTED]"


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", fold(visible(s)[0])).casefold()


def _digits(s: str) -> str:
    return "".join(c for c in s.translate(_DEVA_DIGITS) if c.isdigit())


class LeakGate:
    def __init__(self) -> None:
        self.digits: set[str] = set()
        self.literals: set[str] = set()
        self.names: set[tuple[str, ...]] = set()
        self._literal_rx: re.Pattern[str] | None = None
        self._name_lens: tuple[int, ...] = ()
        self.hits = 0

    def add(self, ftype: str, text: str, norm: str | None) -> None:
        if ftype in DIGIT_TYPES:
            d = _digits(norm or text)
            if len(d) >= 6:
                self.digits.add(d)
        if ftype in LITERAL_TYPES:
            t = _fold(decode_view(text)[0]).strip()
            if len(t) >= 6 and not t.isdigit():
                self.literals.add(t)
        if ftype in NAME_TYPES:
            decoded = decode_view(text)[0]
            toks = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(visible(decoded)[0]))
            if 2 <= len(toks) <= _MAX_NAME_TOKENS and sum(map(len, toks)) >= 6:
                self.names.add(toks)
                # "Fonseca, Agustín" (surname first) is also written "Agustín Fonseca"
                last, comma, given = decoded.partition(",")
                if comma:
                    rest = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(visible(given)[0]))
                    head = tuple(_fold(m.group(0)) for m in _TOKEN.finditer(visible(last)[0]))
                    if rest and head and len(rest + head) <= _MAX_NAME_TOKENS:
                        self.names.add(rest + head)

    def finalize(self) -> None:
        self._literal_rx = (re.compile("|".join(re.escape(x) for x in sorted(self.literals, key=lambda s: (-len(s), s))),
                                       re.IGNORECASE) if self.literals else None)
        self._name_lens = tuple(sorted({len(t) for t in self.names}, reverse=True))

    # ------------------------------------------------------------------ scrubbing
    def _digit_hit(self, run: str) -> bool:
        d = _digits(run)
        if d in self.digits:
            return True
        if _ISO_DATE_RX.fullmatch(run):
            return False
        return (len(d) > 10 and d[-10:] in self.digits) or (len(d) > 6 and d[-6:] in self.digits and len(d) <= 8)

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
        dec_text, dec_spans = decode_view(value)
        vis_text, vis_kept = visible(dec_text)
        found = find(fold(vis_text))
        if not found:
            return value
        if vis_kept is not None:
            mapped = []
            for s, e in found:
                end_dec = vis_kept[e - 1] + 1
                while end_dec < len(dec_text) and "\u0300" <= dec_text[end_dec] <= "\u036f":
                    end_dec += 1
                mapped.append((vis_kept[s], end_dec))
            found = mapped
        if dec_spans is not None:
            found = [(dec_spans[s][0], dec_spans[e - 1][1]) for s, e in found]
        last = len(value) + 1
        for s, e in reversed(found):
            if e > last:
                continue
            value = value[:s] + REDACTED + value[e:]
            last = s
            self.hits += 1
        return value

    def _digit_spans(self, text: str) -> list[tuple[int, int]]:
        uuids = [(m.start(), m.end()) for m in _UUID_RX.finditer(text)] if "-" in text else []
        return [
            m.span() for m in _DIGIT_RUN.finditer(text)
            if not any(s <= m.start() and m.end() <= e for s, e in uuids) and self._digit_hit(m.group(0))
        ]

    def _name_spans(self, text: str) -> list[tuple[int, int]]:
        toks = [(m.start(), m.end(), _fold(m.group(0))) for m in _TOKEN.finditer(text)]
        lens = self._name_lens or tuple(sorted({len(t) for t in self.names}, reverse=True))
        spans, i = [], 0
        while i < len(toks):
            for n in lens:
                if i + n <= len(toks) and tuple(t[2] for t in toks[i:i + n]) in self.names:
                    if not _DOCTOR_TITLE.search(text[max(0, toks[i][0] - 16):toks[i][0]]):
                        spans.append((toks[i][0], toks[i + n - 1][1]))
                    i += n
                    break
            else:
                i += 1
        return spans

    # ------------------------------------------------------------------ verification
    def contains_leak(self, text: str) -> bool:
        """True when a known identifier is in `text`, also inside escapes and inside a base64 run of readable text."""
        view = fold(visible(decode_view(text)[0])[0])
        if self.digits and self._digit_spans(view):
            return True
        if self._literal_rx is not None and self._literal_rx.search(view):
            return True
        if self.names and self._name_spans(view):
            return True
        return any(self.contains_leak(dec) for _a, _b, dec, _f in find_runs(text))
