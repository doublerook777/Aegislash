"""Addresses: split into house, locality, landmark, village, district and PIN.

Tehsil and state are kept (they are the level we generalise villages *to*).
`parse_address` is for text known to be an address. `find_places` looks for the clearer
cues anywhere in free text.
"""
from __future__ import annotations

import re

from aegis.detect.names import find_names
from aegis.detect.normalize import norm_name
from aegis.detect.spans import Cand

_NUM = r"[A-Z]?[-/]?\d+(?:[-/]?[A-Z0-9]+)?"
HOUSE = re.compile(
    rf"(?<![A-Za-z])(?:(?:H|Hno|HNo)\.? ?(?:No\.?|Number)? ?|(?i:house|makan|flat|plot|door|quarter|qtr|kothi)(?: (?i:no|number))?\.? ?"
    rf"|(?:मकान|घर|प्लॉट) ?(?:नं|नंबर|संख्या)?\.? ?)[:#-]? ?{_NUM}")
_PLACE_WORD = r"(?:[A-Z][a-z]+|[A-Z]{2,})"
_DEVA_W = r"[ऀ-ॣॱ-ॿ]+"
LOCALITY = re.compile(
    rf"\b(?i:mohalla|moh\.|gali|galli|tola) (?:{_PLACE_WORD})(?: {_PLACE_WORD}){{0,2}}"
    rf"|(?:मोहल्ला|मुहल्ला|गली|टोला) {_DEVA_W}(?: {_DEVA_W}){{0,2}}")
_LANDMARK_NOUN = (r"(?:Mandir|Temple|Masjid|Mosque|Gurudwara|Church|School|College|Tanki|Bhawan|Bhavan|Chowk|Crossing|Station|"
                  r"Office|Bank|Market|Bazar|Bazaar|Talab|Pond|Tower|Stand|Gate|Park|Hospital|PHC|Chauraha|Well|Tree)")
LANDMARK = re.compile(
    rf"\b(?i:near|nr\.?|opp\.?|opposite|behind|beside|next to) +(?:{_PLACE_WORD} ){{0,3}}{_LANDMARK_NOUN}\b"
    rf"|(?:{_DEVA_W} ){{1,3}}(?:के पास|के पीछे|के सामने|के बगल(?: में)?)")
VILLAGE_CUE = re.compile(
    rf"(?:\b(?i:village|vill\.?|gram(?! panchayat)|gaon|r/o)|(?<![ऀ-ॿ])(?:ग्राम|गाँव|गांव))[ :.-]+"
    rf"(?P<v>{_PLACE_WORD}(?: {_PLACE_WORD}){{0,2}}|{_DEVA_W}(?: (?:खुर्द|कलां|कलाँ))?)")
DISTRICT_CUE = re.compile(
    rf"(?:\b(?i:district|distt\.?|dist\.?|zila|jila)|(?:जिला|ज़िला|जनपद))[ :.-]+"
    rf"(?P<d>{_PLACE_WORD}(?: {_PLACE_WORD}){{0,2}}|{_DEVA_W})")
PIN_CUE = re.compile(r"(?:\b(?i:pin(?: ?code)?|zip|postal code)\b|पिन(?: कोड)?)\D{0,4}(?P<p>[1-9]\d{2} ?\d{3})(?!\d)")
_PIN_ANY = re.compile(r"(?<![\d-])[1-9]\d{5}(?![\d-])")
# "Distt. Rae Bareli - 229228": only after a word, never after a number ("150000-410000" is a lab range)
_PIN_TAIL = re.compile(r"(?:(?<=[A-Za-zऀ-ॿ)])|(?<=[A-Za-zऀ-ॿ)] ))[-–] ?(?P<p>[1-9]\d{5})(?!\d)")
# the 75 districts of Uttar Pradesh (public administrative data); districts are allowed to stay
_UP_DISTRICTS = frozenset(d.strip() for d in """agra, aligarh, ambedkar nagar, amethi, amroha, auraiya, ayodhya,
azamgarh, baghpat, bahraich, ballia, balrampur, banda, barabanki, bareilly, basti, bhadohi, bijnor, budaun,
bulandshahr, chandauli, chitrakoot, deoria, etah, etawah, farrukhabad, fatehpur, firozabad, gautam buddha nagar,
ghaziabad, ghazipur, gonda, gorakhpur, hamirpur, hapur, hardoi, hathras, jalaun, jaunpur, jhansi, kannauj,
kanpur dehat, kanpur nagar, kasganj, kaushambi, kushinagar, lakhimpur kheri, lalitpur, lucknow, maharajganj,
mahoba, mainpuri, mathura, mau, meerut, mirzapur, moradabad, muzaffarnagar, pilibhit, pratapgarh, prayagraj,
rae bareli, raebareli, rampur district, saharanpur, sambhal, sant kabir nagar, shahjahanpur, shamli, shravasti,
siddharthnagar, sitapur, sonbhadra, sultanpur, unnao, varanasi, faizabad, allahabad""".split(","))
_TEHSIL = re.compile(r"^(?:tehsil|tahsil|taluka|taluk|block|तहसील)\b", re.I)
_STATE = re.compile(r"^(?:uttar pradesh|u\.?p\.?|india|bharat|उत्तर प्रदेश|भारत)\.?$", re.I)
_RELATION_ONLY = re.compile(r"^(?:[CSDW]/[Oo])\b")
_LOCALITY_TAIL = re.compile(r"(?:Nagar|Colony|Tola|Basti|Purwa|Mohalla|Enclave|Vihar|Puri|Gali|Lane|Road|Marg|Sector)\b|"
                            r"(?:नगर|कॉलोनी|टोला|बस्ती|गली|मार्ग|रोड)")


def find_places(text: str) -> list[Cand]:
    """Places announced by a clear cue, safe to run on any free text."""
    out = []
    for kind, pattern in (("HOUSE", HOUSE), ("LOCALITY", LOCALITY), ("LANDMARK", LANDMARK)):
        for m in pattern.finditer(text):
            out.append(Cand(m.start(), m.end(), kind, norm_name(m.group(0)) or None, "patient"))
    for m in VILLAGE_CUE.finditer(text):
        out.append(Cand(m.start("v"), m.end("v"), "VILLAGE", norm_name(m.group("v")), "patient"))
    for m in DISTRICT_CUE.finditer(text):
        out.append(Cand(m.start("d"), m.end("d"), "DISTRICT", norm_name(m.group("d")), "patient"))
    for pattern in (PIN_CUE, _PIN_TAIL):
        for m in pattern.finditer(text):
            out.append(Cand(m.start("p"), m.end("p"), "PIN", m.group("p").replace(" ", ""), "patient"))
    return out


def parse_address(text: str, offset: int = 0, end: int | None = None) -> list[Cand]:
    """Every part of an address gets a type. When unsure, it is a locality (remove it)."""
    end = len(text) if end is None else end
    part = text[offset:end]
    found = [c for c in find_places(part) + find_names(part)]
    for m in re.finditer(r"(?i:ward)(?: no\.?)? ?\d+|वार्ड(?: नं\.?)? ?\d+", part):
        found.append(Cand(m.start(), m.end(), "LOCALITY", norm_name(m.group(0)) or None, "patient"))
    for m in _PIN_ANY.finditer(part):
        found.append(Cand(m.start(), m.end(), "PIN", m.group(0), "patient"))

    segments = []
    for m in re.finditer(r"[^,;\n|]+", part):
        s, e = m.span()
        while s < e and part[s] in " .-":
            s += 1
        while e > s and part[e - 1] in " .-":
            e -= 1
        if e > s:
            segments.append((s, e))
    for i, (s, e) in enumerate(segments):
        if any(c.start < e and s < c.end for c in found):
            continue
        seg = part[s:e]
        if _TEHSIL.match(seg) or _STATE.match(seg) or _RELATION_ONLY.match(seg):
            continue
        if len(seg) < 3 and not seg.isdigit():
            continue
        following = part[segments[i + 1][0]:segments[i + 1][1]] if i + 1 < len(segments) else ""
        if _TEHSIL.match(following):
            kind = "VILLAGE"
        elif any(ch.isdigit() for ch in seg):
            kind = "HOUSE"
        elif " ".join(seg.casefold().split()) in _UP_DISTRICTS:
            kind = "DISTRICT"
        elif i == len(segments) - 1 and len(segments) > 1 and not _LOCALITY_TAIL.search(seg):
            kind = "VILLAGE"  # an unlabelled last part is usually the village or town
        else:
            kind = "LOCALITY"
        found.append(Cand(s, e, kind, norm_name(seg) or None, "patient"))
    return [c._replace(start=c.start + offset, end=c.end + offset) for c in found]
