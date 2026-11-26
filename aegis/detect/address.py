"""Addresses: split into house, locality, landmark, village, district and PIN.

Tehsil and state are kept (they are the level we generalise villages *to*).
`parse_address` is for text known to be an address. `find_places` looks for the clearer
cues anywhere in free text.
"""
from __future__ import annotations

import re

from aegis.detect.gazetteer import SURNAMES
from aegis.detect.names import STOP, find_names
from aegis.detect.normalize import norm_name
from aegis.detect.spans import PRIORITY, Cand

_NUM = r"[A-Z]?[-/]?\d+(?:[-/]?[A-Z0-9]+)*(?:/[ऀ-ॿ](?![ऀ-ॿ]))?"
HOUSE = re.compile(
    rf"(?<![A-Za-z])(?:(?:H|Hno|HNo)\.? ?(?:No\.?|Number)? ?|(?i:house|makan|flat|plot|door|quarter|qtr|kothi)(?: (?i:no|number))?\.? ?"
    rf"|(?:मकान|घर|प्लॉट) ?(?:नं|नंबर|संख्या)?\.? ?)[:#-]? ?{_NUM}")
_PLACE_WORD = r"(?:St\.|[A-Z][a-z]+|[A-Z]{2,})"
_DEVA_W = r"[ऀ-ॣॱ-ॿ]+"
LOCALITY = re.compile(
    rf"\b(?i:mohalla|moh\.|gali|galli|tola) (?:{_PLACE_WORD})(?: {_PLACE_WORD}){{0,2}}"
    rf"|(?:मोहल्ला|मुहल्ला|गली|टोला) {_DEVA_W}(?: {_DEVA_W}){{0,2}}")
_LANDMARK_NOUN = (r"(?:Mandir|Temple|Masjid|Mosque|Gurudwara|Church|School|College|Tanki|Bhawan|Bhavan|Chowk|Crossing|Station|"
                  r"Office|Bank|Market|Bazar|Bazaar|Talab|Pond|Tower|Stand|Gate|Park|Hospital|PHC|Chauraha|Well|Tree|Fatak|Phatak|Naka|"
                  r"Maidan|Chowki|Cinema|Depot|Hall|Bridge|Pump|Dharamshala|Library|Stadium|Circle)")
LANDMARK = re.compile(
    rf"\b(?i:near|nr\.?|opp\.?|opposite|behind|beside|next to)(?: *: *| +)(?:{_PLACE_WORD} ){{0,3}}{_LANDMARK_NOUN}\b"
    rf"|(?:{_DEVA_W} ){{1,3}}(?:के पास|के पीछे|के सामने|के बगल(?: में)?)"
    rf"|(?:{_PLACE_WORD} ){{0,3}}{_LANDMARK_NOUN} (?i:ke|ki) (?i:paas|pass|peeche|piche|saamne|samne|bagal)\b")
VILLAGE_CUE = re.compile(
    rf"(?:\b(?i:village|vill\.?|gram(?! panchayat)|gaon|r/o)|(?<![ऀ-ॿ])(?:ग्राम|गाँव|गांव))[ :.-]+"
    rf"(?P<v>{_PLACE_WORD}(?: {_PLACE_WORD}){{0,2}}|{_DEVA_W}(?: (?:खुर्द|कलां|कलाँ))?)")
# "resident of X", "hailing from X"; and the place named just before the word "village"
_LIVES_IN = re.compile(
    rf"\b(?i:resident of|residing (?:at|in)|resides (?:at|in)|hailing from|hails from|native of|lives (?:at|in))"
    rf" (?:(?i:village|vill\.?|gram) )?(?P<v>{_PLACE_WORD}(?: {_PLACE_WORD}){{0,2}})")
_THEN_VILLAGE = re.compile(rf"(?<![A-Za-z])(?P<v>{_PLACE_WORD}) (?i:village|gaon)\b|(?<![ऀ-ॿ])(?P<d>{_DEVA_W}(?:-{_DEVA_W})?) (?:गांव|गाँव)(?![ऀ-ॿ])")
DISTRICT_CUE = re.compile(
    rf"(?:\b(?i:district|distt\.?|dist\.?|zila|jila)|(?:जिला|ज़िला|जनपद))[ :.-]+"
    rf"(?P<d>{_PLACE_WORD}(?: {_PLACE_WORD}){{0,2}}|{_DEVA_W})")
PIN_CUE = re.compile(r"(?:\b(?i:pin(?: ?code)?|zip|postal code)\b|पिन(?: कोड)?)\D{0,4}(?P<p>[1-9]\d{2} ?\d{3})(?!\d)")
_PIN_ANY = re.compile(r"(?<![\d-])[1-9]\d{5}(?![\d-])")
# "Distt. Rae Bareli - 229228": only after a word, never after a number ("150000-410000" is a lab range)
_PIN_TAIL = re.compile(r"(?:(?<=[A-Za-zऀ-ॿ)])|(?<=[A-Za-zऀ-ॿ)] ))[-–] ?(?P<p>[1-9]\d{5})(?!\d)")
# "address 45/2, Mylapore", "पता 12/3, झूला रोड": a door number right after the word "address"
_ADDRESS_NUMBER = re.compile(rf"(?:\b(?i:address|addr\.?)|(?<![ऀ-ॿ])पता)[ :-]+(?P<h>\d{{1,4}}(?:[-/]?[A-Z0-9]{{1,4}})?)(?=[ ]*,)")
# ", 560001" with no PIN label: not money, not a count with a unit; real PIN codes never end in 000
_PIN_AFTER_COMMA = re.compile(
    r",[ ]?(?P<p>[1-9]\d{2}(?!000)\d{3})(?![\d%]|[.,]\d|[ ]?(?:/|-[ ]?\d|(?i:cells|cumm|per|lakh|mg|ml|iu|units?|rs|inr)\b))")
_PART_BODY = (rf"(?:{_PLACE_WORD}|{_DEVA_W}(?:-{_DEVA_W})?)(?:[ -](?:{_PLACE_WORD}|{_DEVA_W}|[A-Z](?![A-Za-z])|\d{{1,3}}(?!\d))){{0,4}}")
_NEXT_PART = re.compile(rf"[ ]*,[ ]*(?P<v>{_PART_BODY})(?=[ ]*(?:[,;|)\n]|\.(?![A-Za-z0-9])|-[ ]?\d{{6}}|$))")
_PREVIOUS_PART = re.compile(rf"(?:^|[,;|:(\n]|(?i:vill\.?|gram|village|gaon|from|resident of)[ ]|(?:ग्राम|गाँव|गांव)[ ])[ ]*(?P<v>{_PART_BODY})[ ]*(?:,|-)?[ ]*$")
_NOT_PLACE = frozenset("""hostel family health nutrition day camp care home hospice shelter joint rural urban area
vill distt dist tehsil teh po ps post moh""".split())
_DISTRICT_LABELLED = re.compile(r"^(?:(?i:district|distt|dist|zila|jila)\b|जिला|ज़िला|जनपद)")
# "Platelets, 245100" is a result, not a PIN code
_COUNTED = frozenset("""platelets platelet wbc rbc count counts total amount deposit cost paid balance fee fees charges bill
value level titre units rupees inr rs claim package reading result sample lab no id राशि बिल खर्च कुल जमा""".split())
# words that are common in notes but also normal parts of a place name
_PLACE_STOP = frozenset(("nagar", "road", "village", "gram", "mohalla", "gali", "district", "asha", "near", "behind", "opp", "salt", "hospital", "may", "march"))
_PLACE_SURNAMES = frozenset(("nagar", "ganj", "lal", "ram", "das", "singh", "rai", "gandhi", "patel", "bose", "tagore"))
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


_CARE_OF_ADDRESS = re.compile(r"(?<![A-Za-z/])(?i:c/o)[ :.-]+(?P<a>\d{1,4}[A-Z]?(?:/\d+)?, *[^;\n|]{5,120})")


def find_places(text: str, care_of: bool = True) -> list[Cand]:
    """Places announced by a clear cue, safe to run on any free text."""
    out = []
    for kind, pattern in (("HOUSE", HOUSE), ("LOCALITY", LOCALITY), ("LANDMARK", LANDMARK)):
        for m in pattern.finditer(text):
            out.append(Cand(m.start(), m.end(), kind, norm_name(m.group(0)) or None, "patient"))
    for m in VILLAGE_CUE.finditer(text):
        if set(m.group("v").casefold().split()) & _NOT_PLACE:
            continue  # "Village Health Nutrition Day"
        out.append(Cand(m.start("v"), m.end("v"), "VILLAGE", norm_name(m.group("v")), "patient"))
    for pattern in (_LIVES_IN, _THEN_VILLAGE):
        for m in pattern.finditer(text):
            group = "v" if m.group("v") else "d"
            if _is_place(m.group(group)):
                kind = "DISTRICT" if m.group(group).casefold() in _UP_DISTRICTS else "VILLAGE"
                out.append(Cand(m.start(group), m.end(group), kind, norm_name(m.group(group)), "patient"))
    for m in DISTRICT_CUE.finditer(text):
        out.append(Cand(m.start("d"), m.end("d"), "DISTRICT", norm_name(m.group("d")), "patient"))
    # "c/o- 14, Nehru Marg, ...": care-of followed by a number is an address, not a complaint or a person
    for m in _CARE_OF_ADDRESS.finditer(text) if care_of else ():
        out.extend(parse_address(text, m.start("a"), m.end("a")))
    for m in _ADDRESS_NUMBER.finditer(text):
        out.append(Cand(m.start("h"), m.end("h"), "HOUSE", None, "patient"))
    pin_starts = []
    for pattern in (PIN_CUE, _PIN_TAIL, _PIN_AFTER_COMMA):
        for m in pattern.finditer(text):
            if pattern is _PIN_AFTER_COMMA and not _ends_with_place(text, m.start()):
                continue
            out.append(Cand(m.start("p"), m.end("p"), "PIN", m.group("p").replace(" ", ""), "patient"))
            pin_starts.append(m.start())
    # the rest of an address: parts after a house number, and parts before a PIN
    if care_of:  # not inside parse_address, which reads every part itself
        chain = [p for c in out if c.type in ("HOUSE", "LOCALITY", "LANDMARK") for p in _parts_after(text, c.end)]
        chain += [p for start in pin_starts for p in _parts_before(text, start)]
        # any more specific reading of the same words wins over the chain's guess
        out += [p._replace(prio=PRIORITY["LOCALITY"] - 10) if p.type == "LOCALITY" else p for p in chain]
    return out


def _is_place(value: str) -> bool:
    """Could this comma-separated piece be a place name? Not a report word, medicine or person."""
    if _DISTRICT_LABELLED.match(value):
        return False  # DISTRICT_CUE reads these
    words = value.replace(".", " ").split()
    if not words or len(words) > 5:
        return False
    folded = [w.casefold() for w in words]
    if any(w in _NOT_PLACE or w in STOP - _PLACE_STOP for w in folded):
        return False
    return not (len(words) > 1 and folded[-1] in SURNAMES - _PLACE_SURNAMES)


def _part(value: str) -> list[Cand]:
    plain = " ".join(value.casefold().split())
    if _TEHSIL.match(value) or _STATE.match(value):
        return []
    kind = "DISTRICT" if plain in _UP_DISTRICTS else "LOCALITY"
    return [Cand(0, len(value), kind, norm_name(value) or None, "patient")]


def _parts_after(text: str, pos: int) -> list[Cand]:
    out = []
    for _ in range(3):
        m = _NEXT_PART.match(text, pos)
        if not m or not _is_place(m.group("v")):
            break
        out += [c._replace(start=m.start("v"), end=m.end("v")) for c in _part(m.group("v"))]
        pos = m.end("v")
    return out


def _parts_before(text: str, pos: int) -> list[Cand]:
    out = []
    for _ in range(3):
        window = max(0, pos - 60)
        m = _PREVIOUS_PART.search(text[window:pos])
        if not m or not _is_place(m.group("v")):
            break
        start = window + m.start("v")
        out += [c._replace(start=start, end=window + m.end("v")) for c in _part(m.group("v"))]
        pos = start
    return out


def _ends_with_place(text: str, comma: int) -> bool:
    """True when the word just before ", 560001" can end an address ("Prem Nagar", "mandir ke paas")."""
    m = re.search(rf"(?:(?P<w>{_PLACE_WORD}|{_DEVA_W}|[A-Z])|(?i:ke paas|ke peeche|ke samne))[ .)]*$", text[max(0, comma - 40):comma])
    if not m:
        return False
    word = (m.group("w") or "").casefold()
    return word not in _COUNTED and word not in STOP - _PLACE_STOP


def parse_address(text: str, offset: int = 0, end: int | None = None) -> list[Cand]:
    """Every part of an address gets a type. When unsure, it is a locality (remove it)."""
    end = len(text) if end is None else end
    part = text[offset:end]
    found = find_places(part, care_of=False) + find_names(part)
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
        if len(seg.split()) > 7:
            continue  # a sentence, not part of an address
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
