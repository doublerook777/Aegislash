"""Text normalising: digit folding, script detection, Devanagari -> Latin.

`fold` changes characters one-for-one, so an offset found in the folded text is the same
offset in the original. Never add a rule here that changes the length of the text.
"""
from __future__ import annotations

import re
import unicodedata

_FOLD = {}
for _zero in (0x0966, 0xFF10, 0x09E6, 0x0A66, 0x0AE6):  # Devanagari, fullwidth, Bengali, Gurmukhi, Gujarati
    for _i in range(10):
        _FOLD[_zero + _i] = str(_i)
for _c in "‐‑‒–—―−":
    _FOLD[ord(_c)] = "-"
for _c in " \u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000":
    _FOLD[ord(_c)] = " "
_FOLD[ord("’")] = "'"
_FOLD[ord("‘")] = "'"

# 1-to-1 Cyrillic/Greek homoglyph and Latin diacritic folding (preserves string length & offsets)
_HOMOGLYPHS = {
    "а": "a", "А": "A", "в": "B", "В": "B", "е": "e", "Е": "E", "ё": "e", "Ё": "E",
    "з": "3", "З": "3", "і": "i", "І": "I", "ї": "i", "Ї": "I", "к": "k", "К": "K",
    "м": "m", "М": "M", "н": "H", "Н": "H", "о": "o", "О": "O", "р": "p", "Р": "P",
    "с": "c", "С": "C", "т": "t", "Т": "T", "у": "y", "У": "Y", "х": "x", "Х": "X",
    "α": "a", "Α": "A", "β": "B", "Β": "B", "ε": "e", "Ε": "E", "ζ": "Z", "Ζ": "Z",
    "η": "n", "Η": "H", "ι": "i", "Ι": "I", "κ": "k", "Κ": "K", "μ": "m", "Μ": "M",
    "ν": "v", "Ν": "N", "ο": "o", "Ο": "O", "ρ": "p", "Ρ": "P", "ς": "c", "τ": "t",
    "Τ": "T", "υ": "u", "Υ": "Y", "χ": "x", "Χ": "X",
}
for _src, _dst in _HOMOGLYPHS.items():
    _FOLD[ord(_src)] = _dst

for _src, _dst in (
    ("áàâäãåāăą", "a"), ("éèêëēĕėęě", "e"), ("íìîïĩīĭįı", "i"),
    ("óòôöõøōŏő", "o"), ("úùûüũūŭůűų", "u"), ("ñńņň", "n"),
    ("çćĉċč", "c"), ("ýÿŷ", "y"), ("śŝşš", "s"), ("źżž", "z"),
    ("řŕŗ", "r"), ("ťţŧ", "t"), ("ďđ", "d"), ("łĺļľ", "l"), ("ğĝġģ", "g"),
):
    for _ch in _src:
        _FOLD[ord(_ch)] = _dst
        if _ch.upper() != _ch and len(_ch.upper()) == 1:
            _FOLD[ord(_ch.upper())] = _dst.upper()

_ZW_STRIP = frozenset("\u200b\ufeff\u00ad")
_ZW_JOIN = frozenset("\u200c\u200d")
DEVA = re.compile(r"[ऀ-ॿ]")


def fold(s: str) -> str:
    return s.translate(_FOLD)


def strip_evasion_with_map(s: str) -> tuple[str, list[int] | None]:
    """Strip zero-width obfuscation (and non-Devanagari combining marks) while returning an offset map.

    Returns ``(clean, idx_map)`` where ``idx_map`` is ``None`` on the fast path (nothing stripped),
    or a list of original character indices for every character in ``clean``.
    """
    if not any(c in _ZW_STRIP or c in _ZW_JOIN or (unicodedata.combining(c) and not ("\u0900" <= c <= "\u097f")) for c in s):
        return s, None
    out_chars: list[str] = []
    idx_map: list[int] = []
    n = len(s)
    for i, ch in enumerate(s):
        if ch in _ZW_STRIP:
            continue
        if ch in _ZW_JOIN:
            prev_deva = i > 0 and "\u0900" <= s[i - 1] <= "\u097f"
            next_deva = i + 1 < n and "\u0900" <= s[i + 1] <= "\u097f"
            if not (prev_deva and next_deva):
                continue
        if unicodedata.combining(ch) and not ("\u0900" <= ch <= "\u097f"):
            continue
        out_chars.append(ch)
        idx_map.append(i)
    return "".join(out_chars), idx_map


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
    return " ".join(re.sub(r"[^a-z ]+", " ", to_latin(s).casefold()).split())


def script_of(s: str) -> str:
    return "deva" if DEVA.search(s) else "latin"
