"""Text normalising: digit folding, look-alike letters, hidden characters, Devanagari -> Latin.

`fold` changes characters one-for-one, so an offset found in the folded text is the same
offset in the original. Never add a rule to `fold` that changes the length of the text.
`visible` does shorten text; it returns the original position of every character it keeps.
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
for _c in "    ":
    _FOLD[ord(_c)] = " "
_FOLD[ord("’")] = "'"
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
