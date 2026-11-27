"""Text normalising: digit folding, look-alike letters, hidden characters, Devanagari -> Latin.

`fold` changes characters one-for-one, so an offset found in the folded text is the same
offset in the original. Never add a rule to `fold` that changes the length of the text.
`visible` does shorten text; it returns the original position of every character it keeps.
"""
from __future__ import annotations

import html
import re
import unicodedata

_FOLD = {}
for _zero in (0x0966, 0xFF10, 0x09E6, 0x0A66, 0x0AE6):  # Devanagari, fullwidth, Bengali, Gurmukhi, Gujarati
    for _i in range(10):
        _FOLD[_zero + _i] = str(_i)
for _c in "‐‑‒–—―−":
    _FOLD[ord(_c)] = "-"
for _c in "\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000":
    _FOLD[ord(_c)] = " "
_FOLD[ord("’")] = "'"
_FOLD[ord("‘")] = "'"
# accented Latin letters are matched as their base letter ("í" -> "i"); name patterns are plain A-Z
for _n in range(0x00C0, 0x0250):
    _base = unicodedata.normalize("NFD", chr(_n))[0]
    if _base != chr(_n) and _base.isascii() and _base.isalpha():
        _FOLD[_n] = _base

DEVA = re.compile(r"[ऀ-ॿ]")


# Cyrillic and Greek letters that look like Latin ones. Only replaced inside a word that also has real Latin
# letters, so a micro sign or a word written wholly in another script is left alone.
_LOOKALIKE = str.maketrans("аеорсухіјѕԁһӏАВЕЅІЈКМНОРСТУХ" "οαιΑΒΕΖΗΙΚΜΝΟΡΤΥΧ",
                           "aeopcyxijsdhlABESIJKMHOPCTYX" "oaiABEZHIKMNOPTYX")
_WORD = re.compile(r"[A-Za-z\u0370-\u03ff\u0400-\u052f]+")


def _unmask(m: re.Match) -> str:
    word = m.group(0)
    return word.translate(_LOOKALIKE) if re.search(r"[A-Za-z]", word) else word


def fold(s: str) -> str:
    s = s.translate(_FOLD)
    return s if s.isascii() else _WORD.sub(_unmask, s)


# zero-width characters, direction marks and soft hyphens; also accents typed as separate marks after a letter
_HIDDEN = re.compile(r"[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]|(?<=[A-Za-z])[\u0300-\u036f]+")


def visible(s: str) -> tuple[str, list[int] | None]:
    """`s` without hidden characters, and where each kept character was in `s` (None: nothing removed)."""
    if s.isascii() or not _HIDDEN.search(s):
        return s, None
    dropped = {i for m in _HIDDEN.finditer(s) for i in range(m.start(), m.end())}
    kept = [i for i in range(len(s)) if i not in dropped]
    return "".join(s[i] for i in kept), kept


_PCT_RUN = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
_UNI_ESC = re.compile(r"\\u(?:\{([0-9A-Fa-f]{1,6})\}|([0-9A-Fa-f]{4}))")
_HTML_ENT = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")


def _splice(s: str, items: list[tuple[int, int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """`s` with every (start, end, text) of `items` (sorted, not overlapping) replaced by its text; for each
    character of the result the (start, end) it covers in `s`."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for a, b, t in items:
        if a > pos:
            out.append(s[pos:a])
            spans.extend(zip(range(pos, a), range(pos + 1, a + 1)))
        out.append(t)
        spans.extend([(a, b)] * len(t))
        pos = b
    if pos < len(s):
        out.append(s[pos:])
        spans.extend(zip(range(pos, len(s)), range(pos + 1, len(s) + 1)))
    return "".join(out), spans


def _pct_items(s: str) -> list[tuple[int, int, str]]:
    items: list[tuple[int, int, str]] = []
    for m in _PCT_RUN.finditer(s):
        raw = bytes.fromhex(m.group(0).replace("%", ""))
        i = 0
        while i < len(raw):
            b = raw[i]
            n = 1 if b < 0x80 else 2 if 0xC2 <= b <= 0xDF else 3 if 0xE0 <= b <= 0xEF else 4 if 0xF0 <= b <= 0xF4 else 0
            ch = None
            if n and i + n <= len(raw):
                try:
                    ch = raw[i:i + n].decode("utf-8")
                except UnicodeDecodeError:
                    ch = None
            first = m.start() + 3 * i
            if ch is not None and (n > 1 or 0x20 <= b < 0x7F):
                items.append((first, first + 3 * n, ch))
                i += n
            else:
                i += 1
    return items


def _usable(cp: int) -> bool:
    return 0x20 <= cp <= 0x10FFFF and not 0x7F <= cp <= 0x9F and not 0xD800 <= cp <= 0xDFFF and cp != 0xFFFD


def _uni_items(s: str) -> list[tuple[int, int, str]]:
    """"\\u0932" / "\\u{1F600}" written out as text (not JSON-parsed), with surrogate pairs joined. Control characters
    stay as they are."""
    items: list[tuple[int, int, str]] = []
    ms = list(_UNI_ESC.finditer(s))
    i = 0
    while i < len(ms):
        m = ms[i]
        cp = int(m.group(1) or m.group(2), 16)
        end = m.end()
        if 0xD800 <= cp <= 0xDBFF and i + 1 < len(ms) and ms[i + 1].start() == end and ms[i + 1].group(2):
            low = int(ms[i + 1].group(2), 16)
            if 0xDC00 <= low <= 0xDFFF:
                cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)
                end = ms[i + 1].end()
                i += 1
        if _usable(cp):
            items.append((m.start(), end, chr(cp)))
        i += 1
    return items


def _html_items(s: str) -> list[tuple[int, int, str]]:
    items: list[tuple[int, int, str]] = []
    for m in _HTML_ENT.finditer(s):
        t = html.unescape(m.group(0))
        if t != m.group(0) and all(_usable(ord(c)) for c in t):
            items.append((m.start(), m.end(), t))
    return items


def unquote_view(s: str) -> tuple[str, list[tuple[int, int]] | None]:
    """`s` with URL escapes read ("%20" -> " ", "%5C" -> "\\", "%C3%AD" -> "í"), and for every character of the
    result the (start, end) it covers in `s` (None: nothing was decoded). An escape that is not valid UTF-8, or that
    stands for a control character, is left as it is, so "5%DEX" and "%0A" are not touched."""
    if "%" not in s or not _PCT_RUN.search(s):
        return s, None
    items = _pct_items(s)
    return _splice(s, items) if items else (s, None)


def decode_view(s: str) -> tuple[str, list[tuple[int, int]] | None]:
    """The text as a reader sees it once escapes are read: URL escapes ("%20"), "\\u0932" sequences written out in the
    text and HTML entities ("&amp;", "&#2354;"), up to three layers deep ("%5Cu0932"). Returns the text and, for each of
    its characters, the (start, end) it covers in `s` (None: nothing was decoded)."""
    spans: list[tuple[int, int]] | None = None
    for _ in range(3):
        changed = False
        for hint, fn in (("%", _pct_items), ("\\u", _uni_items), ("&", _html_items)):
            if hint not in s:
                continue
            items = fn(s)
            if not items:
                continue
            s, inner = _splice(s, items)
            spans = inner if spans is None else [(spans[a][0], spans[b - 1][1]) for a, b in inner]
            changed = True
        if not changed:
            break
    return s, spans


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", fold(s))


_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh"}
_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o"}
_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॉ": "o"}


def _word_to_latin(word: str) -> str:
    # units: [consonant or "", vowel, vowel_is_inherent]
    units: list[list] = []
    for ch in unicodedata.normalize("NFD", word):
        if ch in _CONS:
            units.append([ch, "a", True])
        elif ch == "़" and units and units[-1][0] in _NUKTA:
            units[-1][0] = "़" + units[-1][0]
        elif ch in _MATRAS and units:
            units[-1][1:] = [_MATRAS[ch], False]
        elif ch == "्" and units:  # virama: no vowel
            units[-1][1:] = ["", False]
        elif ch in _VOWELS:
            units.append(["", _VOWELS[ch], False])
        elif ch in "ंँ":
            units.append(["", "n", False])
    # Hindi drops the inherent "a" at the end of a word and often in the middle (कमला -> kamla)
    if len(units) > 1 and units[-1][2]:
        units[-1][1] = ""
    for i in range(len(units) - 2, 0, -1):
        prev, cur, nxt = units[i - 1], units[i], units[i + 1]
        if cur[2] and cur[1] and prev[1] and nxt[0] and nxt[1]:
            cur[1] = ""
    out = []
    for cons, vowel, _ in units:
        if cons.startswith("़"):
            out.append(_NUKTA[cons[1]])
        elif cons:
            out.append(_CONS[cons])
        out.append(vowel)
    return "".join(out)


def to_latin(s: str) -> str:
    return re.sub(r"[ऀ-ॿ]+", lambda m: _word_to_latin(m.group(0)), s)


def norm_name(s: str) -> str:
    """Casefolded Latin form used in Finding.norm and Evidence."""
    return " ".join(re.sub(r"[^a-z ]+", " ", to_latin(fold(s)).casefold()).split())


def script_of(s: str) -> str:
    return "deva" if DEVA.search(s) else "latin"
