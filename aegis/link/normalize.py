"""Cross-script normalization and identifier parsing for patient record linkage."""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz.distance import Levenshtein

from aegis.types import IdMention, NameMention

# Titles, honorifics, and kinship markers stripped when comparing names.
HONORIFICS: frozenset[str] = frozenset({
    "ji", "sahab", "saheb", "didi", "behenji", "bahanji", "amma", "bhai", "bhaiya",
    "babu", "chachu", "chacha", "shri", "sri", "smt", "shrimati", "mr", "mrs", "ms",
    "miss", "km", "kumari", "late", "begum", "bi", "kaka", "tau", "mama", "mausi", "bua",
})

# Common Indian name prefix/spelling abbreviations.
ALIASES: dict[str, str] = {
    "md": "mohammad",
    "mohd": "mohammad",
    "mohammed": "mohammad",
    "muhammad": "mohammad",
    "muhammed": "mohammad",
    "sk": "shaikh",
    "shaik": "shaikh",
    "sinh": "singh",
}

# Generic surname/suffix tokens that should not anchor a 1-token vs full-name match alone.
GENERIC_SURNAME_TOKENS: frozenset[str] = frozenset({
    "devi", "kumar", "kumari", "singh", "kaur", "sharma", "sarma", "yadav", "patel",
    "gupta", "khan", "siddiqui", "sidiki", "ansari", "bano", "khatoon", "khatun",
    "begum", "prasad", "lal", "verma", "mishra", "misra", "tiwari", "tivari",
    "pandey", "pande", "chauhan", "chohan", "chaudhary", "chodhari", "paswan",
    "nishad", "rajput", "thakur", "lodhi", "qureshi", "kureshi", "malik", "masih",
})

_DEVA_RE = re.compile(r"[\u0900-\u097F]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_IAST_HINT_RE = re.compile(r"[āīūṛṝḷḹēōṃṁḥṅñṭḍṇśṣḻ]")

_DEVA_CONSONANTS: dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y",
}
_DEVA_IND_VOWELS: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e",
}
_DEVA_MATRAS: dict[str, str] = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_HALANT = "्"
_NUKTA = "़"
_NASALS = {"ं", "ँ"}
_VISARGA = "ः"
_LABIALS = {"प", "फ", "ब", "भ", "म"}

_INDIC_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def ascii_digits(text: str) -> str:
    """Convert Unicode/Devanagari digits to ASCII and strip non-digits."""
    normed = unicodedata.normalize("NFKC", text).translate(_INDIC_DIGITS)
    return re.sub(r"\D", "", normed)


def deva_word_to_latin(word: str) -> str:
    """Transliterate a Devanagari word to Latin using Hindi schwa-deletion rules."""
    chars: list[str] = []
    i = 0
    while i < len(word):
        ch = word[i]
        if i + 1 < len(word) and word[i + 1] == _NUKTA and (ch + _NUKTA) in _DEVA_CONSONANTS:
            chars.append(ch + _NUKTA)
            i += 2
        elif ch == _NUKTA:
            i += 1
        else:
            chars.append(ch)
            i += 1

    # Each entry: [latin_text, is_inherent_schwa, has_vowel, has_nasal]
    sylls: list[list] = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _DEVA_CONSONANTS:
            c_lat = _DEVA_CONSONANTS[ch]
            if i + 1 < len(chars) and chars[i + 1] == _HALANT:
                sylls.append([c_lat, False, False, False])
                i += 2
            elif i + 1 < len(chars) and chars[i + 1] in _DEVA_MATRAS:
                v_lat = _DEVA_MATRAS[chars[i + 1]]
                sylls.append([c_lat + v_lat, False, True, False])
                i += 2
            else:
                sylls.append([c_lat, True, True, False])
                i += 1
            if i < len(chars) and chars[i] in _NASALS:
                nas = "m" if (i + 1 < len(chars) and chars[i + 1] in _LABIALS) else "n"
                sylls[-1][0] += ("a" if sylls[-1][1] else "") + nas
                sylls[-1][1] = False
                sylls[-1][3] = True
                i += 1
        elif ch in _DEVA_IND_VOWELS:
            sylls.append([_DEVA_IND_VOWELS[ch], False, True, False])
            i += 1
            if i < len(chars) and chars[i] in _NASALS:
                sylls[-1][0] += "n"
                sylls[-1][3] = True
                i += 1
        elif ch in _NASALS:
            if sylls:
                sylls[-1][0] += ("a" if sylls[-1][1] else "") + "n"
                sylls[-1][1] = False
                sylls[-1][3] = True
            i += 1
        elif ch == _VISARGA:
            if sylls:
                sylls[-1][0] += ("a" if sylls[-1][1] else "") + "h"
                sylls[-1][1] = False
            i += 1
        else:
            if ch.isascii() and ch.isalnum():
                sylls.append([ch.casefold(), False, False, False])
            i += 1

    out: list[str] = []
    n = len(sylls)
    for k, (txt, is_schwa, _has_v, _has_nas) in enumerate(sylls):
        out.append(txt)
        if is_schwa:
            if k == n - 1:
                # Keep final schwa for monosyllables and after conjuncts (e.g. Satyendra, Mishra)
                if n == 1 or (k > 0 and not sylls[k - 1][2]):
                    out.append("a")
            elif k > 0 and sylls[k - 1][2] and not sylls[k - 1][3]:
                if k + 1 < n and not sylls[k + 1][1] and sylls[k + 1][2]:
                    pass  # delete medial schwa before explicit-vowel syllable
                else:
                    out.append("a")
            else:
                out.append("a")
    return "".join(out)


def _strip_iast(text: str) -> str:
    """Fold IAST/Latin diacritics into plain ASCII phonetic approximations."""
    s = unicodedata.normalize("NFKC", text).casefold()
    has_iast = bool(_IAST_HINT_RE.search(s))
    s = s.replace("ś", "sh").replace("ṣ", "sh").replace("ṃ", "n").replace("ṁ", "n").replace("ḥ", "h")
    if has_iast:
        # In IAST, 'c' represents /ch/ unless already 'ch'
        s = re.sub(r"c(?!h)", "ch", s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def normalize_token(tok: str) -> str:
    """Normalize an already-Latin token into a canonical Indian-phonetic spelling."""
    t = unicodedata.normalize("NFKC", tok).casefold()
    t = ALIASES.get(t, t)
    t = t.replace("qu", "k").replace("q", "k")
    t = t.replace("ph", "f").replace("w", "v").replace("z", "j")
    t = t.replace("aa", "a").replace("ee", "i").replace("ii", "i").replace("oo", "u").replace("uu", "u")
    t = t.replace("ai", "e").replace("ae", "e").replace("ei", "e").replace("ey", "e").replace("ay", "e")
    t = t.replace("au", "o").replace("ou", "o")
    t = t.replace("y", "i")
    t = re.sub(r"(.)\1+", r"\1", t)
    return t


def normalize_tokens(text: str, *, strip_honorifics: bool = True) -> tuple[str, ...]:
    """Convert Devanagari or Latin text into normalized phonetic tokens."""
    s = _ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFKC", text))
    parts = re.split(r"[\s,./()\-_]+", s)
    res: list[str] = []
    for part in parts:
        if not part:
            continue
        if _DEVA_RE.search(part):
            lat = deva_word_to_latin(part)
        else:
            lat = _strip_iast(part)
        lat = re.sub(r"[^a-z]", "", lat)
        if not lat:
            continue
        if strip_honorifics and lat in HONORIFICS:
            continue
        nt = normalize_token(lat)
        if nt:
            res.append(nt)
    return tuple(res)


def normalize_name_mention(mention: NameMention) -> tuple[str, ...]:
    """Normalize a NameMention, preferring Devanagari source when present."""
    raw_text = mention.get("text") or ""
    raw_norm = mention.get("norm") or ""
    src = raw_text if _DEVA_RE.search(raw_text) else (raw_norm or raw_text)
    return normalize_tokens(src, strip_honorifics=True)


def phonetic_block_key(tok: str) -> str:
    """Coarse consonant-skeleton key for indexing/blocking across spelling variants."""
    if not tok:
        return ""
    # Strip 'h' after position 0 and internal short vowels 'a','i','u','e','o' after position 0
    head = tok[0]
    tail = tok[1:].replace("h", "")
    tail = re.sub(r"[aeiou]", "", tail)
    return head + tail


def tokens_similar(a: str, b: str, *, allow_initial: bool = False) -> bool:
    """Return True if two normalized tokens match up to Indian transliteration/spelling variants."""
    if a == b:
        return True
    if not a or not b:
        return False
    if allow_initial and (len(a) == 1 or len(b) == 1):
        short, long_ = (a, b) if len(a) == 1 else (b, a)
        if len(long_) >= 2 and _initial_compatible(short, long_[0]):
            return True
        return False
    if a + "a" == b or b + "a" == a:
        return True
    a_noh = a[0] + a[1:].replace("h", "")
    b_noh = b[0] + b[1:].replace("h", "")
    if a_noh == b_noh and len(a_noh) >= 3:
        return True
    if len(a) >= 5 and len(b) >= 5 and Levenshtein.distance(a, b) == 1:
        return True
    return False


def _initial_compatible(c1: str, c2: str) -> bool:
    if c1 == c2:
        return True
    equivs = ({"c", "k", "q"}, {"s", "c"}, {"f", "p"}, {"j", "z"}, {"v", "w"})
    return any(c1 in g and c2 in g for g in equivs)


def village_tokens_similar(a: str, b: str) -> bool:
    """Compare normalized village tokens, tolerating IAST schwa differences."""
    if tokens_similar(a, b):
        return True
    if len(a) >= 4 and len(b) >= 4:
        ca = a[0] + a[1:].replace("a", "").replace("h", "")
        cb = b[0] + b[1:].replace("a", "").replace("h", "")
        if ca == cb and len(ca) >= 3:
            return True
    return False


def villages_match(v1: tuple[str, ...], v2: tuple[str, ...]) -> bool:
    """Return True if two normalized village token tuples refer to the same village."""
    if not v1 or not v2 or len(v1) != len(v2):
        return False
    return all(village_tokens_similar(x, y) for x, y in zip(v1, v2))


def full_names_match(fn1: tuple[str, ...], fn2: tuple[str, ...]) -> bool:
    """Compare two multi-token names (supports reversed order, middle name omission, initials)."""
    if len(fn1) < 2 or len(fn2) < 2:
        return False
    # Same-length direct or reversed order (e.g. Shahid Mohammad vs Mohammad Shahid)
    if len(fn1) == len(fn2):
        if _aligned_match(fn1, fn2):
            return True
        if len(fn1) == 2 and _aligned_match(fn1, (fn2[1], fn2[0])):
            return True
        return False
    # Different lengths (e.g. Ram Kumar Sharma vs Ram Sharma): shorter must match first+last or ordered subset
    short, long_ = (fn1, fn2) if len(fn1) < len(fn2) else (fn2, fn1)
    if len(short) < 2:
        return False
    # Check ordered subsequence with at least 2 multi-char matched tokens
    j = 0
    matched_full = 0
    for tok in short:
        found = False
        while j < len(long_):
            if tokens_similar(tok, long_[j], allow_initial=True):
                if len(tok) >= 2 and len(long_[j]) >= 2:
                    matched_full += 1
                j += 1
                found = True
                break
            j += 1
        if not found:
            return False
    return matched_full >= 2 or (matched_full >= 1 and len(short) >= 2)


def _aligned_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    multi_char_matches = 0
    for x, y in zip(a, b):
        if not tokens_similar(x, y, allow_initial=True):
            return False
        if len(x) >= 2 and len(y) >= 2:
            multi_char_matches += 1
    return multi_char_matches >= 1


def single_matches_full(tok: str, fn: tuple[str, ...], *, allow_surname_only: bool = False) -> bool:
    """Return True if a single-token name matches a non-generic token in a full name."""
    if len(tok) < 2:
        return False
    for idx, ftok in enumerate(fn):
        if tokens_similar(tok, ftok):
            # Avoid linking solely on a common surname when matching against a full name
            if not allow_surname_only and idx == len(fn) - 1 and tok in GENERIC_SURNAME_TOKENS:
                continue
            return True
    return False


def normalize_strong_id(mention: IdMention) -> tuple[str, str] | None:
    """Normalize a strong identifier into (id_type, canonical_value), or None if unusable."""
    id_type = (mention.get("type") or "").strip().upper()
    raw = unicodedata.normalize("NFKC", mention.get("norm") or "").translate(_INDIC_DIGITS).strip()
    if not raw or not id_type:
        return None

    if id_type == "PHONE":
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            return None
        digits = digits[-10:]
        if len(set(digits)) == 1 or digits in {"1234567890", "0123456789"}:
            return None
        return ("PHONE", digits)

    if id_type == "AADHAAR":
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 12 or len(set(digits)) == 1:
            return None
        return ("AADHAAR", digits)

    if id_type == "ABHA_NUMBER":
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 14 or len(set(digits)) == 1:
            return None
        return ("ABHA_NUMBER", digits)

    if id_type in {"EMAIL", "ABHA_ADDRESS"}:
        val = raw.casefold()
        return (id_type, val) if "@" in val else None

    if id_type in {"PAN", "INSURANCE_ID"}:
        val = re.sub(r"[^a-z0-9]", "", raw.casefold())
        return (id_type, val) if len(val) >= 6 else None

    if id_type == "MRN":
        val = re.sub(r"[^a-z0-9]", "", raw.casefold())
        return ("MRN", val) if len(val) >= 4 else None

    return None
