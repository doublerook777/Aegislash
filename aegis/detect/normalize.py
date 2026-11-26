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
for _c in "    ":
    _FOLD[ord(_c)] = " "
_FOLD[ord("’")] = "'"

DEVA = re.compile(r"[ऀ-ॿ]")


def fold(s: str) -> str:
    return s.translate(_FOLD)


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
