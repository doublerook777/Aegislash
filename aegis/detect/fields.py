"""What to do with one value once we know its role (from a header, a JSON key or a text label)."""
from __future__ import annotations

import re

from aegis.detect.address import parse_address
from aegis.detect.dates import find_dates
from aegis.detect.gazetteer import SURNAMES
from aegis.detect.ids import find_ids, phone_norm
from aegis.detect.names import _TITLE, DEVA_NAME, ORG, STOP, trim_name
from aegis.detect.normalize import DEVA, digits, norm_name
from aegis.detect.spans import PRIORITY, Cand

NAME_ROLES = ("patient_name", "relative_name", "name", "first_name", "last_name")
ID_ROLES = {"phone": "PHONE", "aadhaar": "AADHAAR", "abha": "ABHA_NUMBER", "abha_address": "ABHA_ADDRESS",
            "email": "EMAIL", "pan": "PAN", "insurance": "INSURANCE_ID", "mrn": "MRN"}
_RELATION_PREFIX = re.compile(r"^\s*(?P<rel>[SDWCsdwc]/[Oo])\b[.:]?\s*")
# "Bed 4 - <name>": the bed is not part of the name (and its number must not cut the name off)
_BED_PREFIX = re.compile(r"^\s*(?:(?i:bed|cot|room|ward)(?: (?i:no|number))?|बेड|बिस्तर)\.? ?[#:-]? ?[A-Z]?\d+[A-Z]?(?![A-Za-z0-9])"
                         r"[ \-–—:|,/).]*")
# what a ward is called, so "Ward 4 - Male Surgical" is not read as a person
_WARD_WORDS = frozenset("male female general medical surgical surgery medicine maternity paediatric pediatric labour "
                        "labor isolation private semi special ortho orthopaedic gynae obstetric neonatal burns icu nicu "
                        "picu hdu ccu ward unit wing".split())
_TITLES = re.compile(rf"^\s*(?:(?!Mohd\b|Md\b){_TITLE}\s*)+")
_KIN_ANY = (r"(?:husband|wife|father|mother|son|daughter|brother|sister|uncle|aunt|cousin|guardian|friend|neighbou?r|"
            r"amma|appa|papa|mummy|didi|bhaiya|bhabhi|bahu|beta|beti|pati|patni)")
_SENTENCE_STARTS = re.compile(r"\s(?:came|comes|with|is|was|has|had|presented|admitted|reports|complains|visited|"
                              r"since|today|yesterday|who)(?![A-Za-z])")
def _plain_words(tail: str) -> bool:
    """All lowercase and no relation word: "came with cough", but not "with <Name>" or "with husband <name>"."""
    return tail == tail.lower() and not DEVA.search(tail) and not re.search(rf"(?<![a-z]){_KIN_ANY}(?![a-z])", tail)


_NOT_A_NAME = re.compile(r"^(?:n/?a|na|nil|none|null|unknown|-+|self|same|test)$", re.I)


def relation_of(s: str) -> str | None:
    m = re.search(r"(?<![A-Za-z])([SDWC])/[Oo]\b", s)
    return {"S": "S/o", "D": "D/o", "W": "W/o", "C": "C/O"}[m.group(1).upper()] if m else None


def gender_norm(s: str) -> str | None:
    w = s.strip().casefold()
    if w in ("m", "male", "पुरुष", "पु"):
        return "M"
    if w in ("f", "female", "महिला", "स्त्री", "म"):
        return "F"
    return None


def _strip(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s] in " \t\r\n\"'":
        s += 1
    while e > s and text[e - 1] in " \t\r\n\"',;.|":
        e -= 1
    return s, e


_KIN_THEN_NAME = re.compile(
    r"^\s*(?:(?i:spouse|husband|wife|father|mother|son|daughter|brother|sister|(?:brother|sister|father|mother|son|daughter)-in-law|"
    r"cousin|uncle|aunt|guardian|[hwsdfm]/o)|पति|पत्नी|पिता|माता|पुत्र|पुत्री|बेटा|बेटी|भाई|बहन|बहू|शौहर)\b[ :.\-]+(?P<n>.+)$")


# "<name> (wife)"
_NAME_THEN_KIN = re.compile(
    r"^\s*(?P<n>[A-Z][A-Za-z.' ]+?) *\( *(?i:spouse|husband|wife|father|mother|son|daughter|brother|sister|cousin|uncle|"
    r"aunt|guardian|friend|neighbou?r)\b[^)]*\)")

# a relative column may put the relation first: "amma - <name>", "papa <name>, didi <name>". It is only cut off when
# written in lowercase or followed by a separator: "Nana <surname>" can be somebody's name
_KIN_WORD = (r"(?:amma|appa|papa|mummy|mom|dad|didi|bhaiya|bhabhi|devrani|jethani|bahu|pota|poti|dada|dadi|nana|nani|"
             r"chacha|chachi|tau|tai|mama|mami|mausi|bua|dtr|bro|sibling|son|daughter|wife|husband|father|mother|"
             r"brother|sister|uncle|aunt|cousin)")
_KIN_PREFIX = re.compile(rf"^\s*(?:{_KIN_WORD}(?: +| *[-:=] *)|(?i:{_KIN_WORD}) *[-:=] *)(?=[A-Zऀ-ॿ])")
_LIST_BREAK = re.compile(r"[,;/&]| and ")


def kin_and_name(text: str) -> list[Cand]:
    """A "relation" column may hold the person too: "Father <name>" or "<name> (wife)"."""
    m = _NAME_THEN_KIN.match(text)
    if m:
        return name_value(text, m.start("n"), m.end("n"), "relative_name")
    m = _KIN_THEN_NAME.match(text)
    if not m or not (DEVA.search(m.group("n")) or m.group("n")[:1].isupper()):
        return []
    return name_value(text, m.start("n"), m.end("n"), "relative_name")


# "Surname, Given [Middle]": the comma belongs to the name. Degrees are upper case and do not match.
_SURNAME_FIRST = re.compile(r"[A-Z][a-z'-]+, ?[A-Z][a-z'-]+(?: [A-Z](?![A-Za-z])\.?| [A-Z][a-z'-]+)?")
_NOT_GIVEN = frozenset("male female other nurse sister doctor staff patient self son daughter wife husband father mother".split())


def surname_first(value: str) -> bool:
    words = re.findall(r"[a-z]+", value.casefold())
    return bool(_SURNAME_FIRST.fullmatch(value)) and not set(words) & (_NOT_GIVEN | (STOP - {"asha"}) | ORG)


def relative_in_contact(text: str) -> list[Cand]:
    """A relative's "contact" cell: "<relation> <name>", or something that looks like a name, with or without a number."""
    found = kin_and_name(text)
    if not found and (DEVA.search(text) or len(digits(text)) >= 5
                      or set(re.findall(r"[a-z]+", text.casefold())) & SURNAMES):
        found = name_value(text, 0, len(text), "name")
    return [c._replace(type="RELATIVE_NAME", role="relative", prio=PRIORITY["RELATIVE_NAME"] + 2) for c in found]


def name_value(text: str, s: int, e: int, role: str) -> list[Cand]:
    """The value of a name column. `role` decides patient vs relative."""
    kind = "RELATIVE_NAME" if role == "relative_name" else "PATIENT_NAME"
    who = "relative" if role == "relative_name" else "patient"
    relation = None
    while m := _BED_PREFIX.match(text[s:e]):   # "Ward 3 Bed 8 - <name>"
        s += m.end()
    if role == "relative_name" and (m := _KIN_PREFIX.match(text[s:e])):
        s += m.end()
    # a name cell that runs on into a sentence ("<name> came with cough") ends where the sentence starts
    m = _SENTENCE_STARTS.search(text, s, e)
    if m and _plain_words(text[m.start():e]):
        e = m.start()
    m = _RELATION_PREFIX.match(text[s:e])
    if m:
        relation = relation_of(m.group("rel"))
        s += m.end()
        kind, who = "RELATIVE_NAME", "relative"
    m = _TITLES.match(text[s:e])
    if m:
        s += m.end()
    whole = surname_first(text[s:e].strip(" \t\r\n\"'.;|"))
    cut = re.search(r"[(\[|;:/]| - |\s{2,}|\d|\n" if whole else r"[,(\[|;:/]| - |\s{2,}|\d|\n", text[s:e])
    if cut:
        e = s + cut.start()
    s, e = _strip(text, s, e)
    value = text[s:e]
    words = value.split()
    if not value or len(words) > 5 or _NOT_A_NAME.match(value) or re.match(r"(?:Dr\b|डॉ|ASHA\b(?! [A-Z]))", value):
        return []
    if not (DEVA.search(value) or whole or re.fullmatch(r"[A-Za-z][A-Za-z.' -]*", value)):
        return []
    if role == "name":
        # a bare "name" label: only accept values that really look like a person
        if all(w.strip(".").casefold() in (STOP | ORG) - {"asha"} for w in words):
            return []
        if not (re.fullmatch(DEVA_NAME, value) or all(w[0].isupper() for w in words)):
            return []
    if not DEVA.search(value) and not whole:
        span = trim_name(text, s, e) if role == "name" else (s, e)
        if not span:
            return []
        s, e = span
    return [Cand(s, e, kind, None, who, prio=PRIORITY[kind] + 2, relation=relation)]


def structured(text: str, s: int, e: int, role: str, dmy: bool) -> list[Cand]:
    """Candidates for text[s:e] (folded text) that is known to hold a `role` value."""
    s, e = _strip(text, s, e)
    if e <= s:
        return []
    value = text[s:e]
    if role == "relative_name":
        # several relatives in one cell, each announced by its relation
        pieces, start = [], s
        for m in [*_LIST_BREAK.finditer(text, s, e), None]:
            pieces.append(_strip(text, start, m.start() if m else e))
            start = m.end() if m else e
        if len(pieces) > 1 and all(_KIN_PREFIX.match(text[a:b]) for a, b in pieces):
            return [c for a, b in pieces for c in name_value(text, a, b, role)]
    if role in NAME_ROLES:
        return name_value(text, s, e, role)
    if role == "bed_patient":
        # a name right after a bed number is the patient. Anything else ("Female Medical Ward") is read like free text
        bed = _BED_PREFIX.match(value)
        if not bed or set(re.findall(r"[a-z]+", value[bed.end():].casefold())) & _WARD_WORDS:
            return []
        return name_value(text, s, e, "name")

    if role in ID_ROLES:
        kind = ID_ROLES[role]
        found = [c._replace(start=c.start + s, end=c.end + s) for c in find_ids(value)]
        # the column holds one number: take all of it, even if only a part has a known shape ("RCH-JH-26-44109")
        if (kind in ("MRN", "INSURANCE_ID") and re.fullmatch(r"[A-Za-z0-9#/_.-]{5,30}", value)
                # (a 12-digit tail can look like an Aadhaar number: it is still one ID, remove all of it)
                and len(digits(value)) >= 4 and all(c.type in ("MRN", "INSURANCE_ID", "PHONE", "AADHAAR") for c in found)
                and not any(c.start == s and c.end == e for c in found)):
            norm = re.sub(r"[^A-Z0-9]", "", value.upper()) if kind == "INSURANCE_ID" else digits(value)
            return [Cand(s, e, kind, norm, "patient", prio=PRIORITY[kind] + 2)]
        if found:
            return found
        needs_at = kind in ("EMAIL", "ABHA_ADDRESS")
        if len(re.findall(r"[a-z]{3,}", value)) >= 2 and not needs_at:
            return []
        if (needs_at and "@" not in value) or (not needs_at and len(digits(value)) < 5) or len(value) > 40:
            return []
        if kind == "AADHAAR" and re.search(r"[Xx*•]", value):
            kind = "AADHAAR_MASKED"
        norm = (phone_norm(value) if kind == "PHONE" else
                value.casefold() if needs_at else
                re.sub(r"[^A-Z0-9]", "", value.upper()) if kind in ("PAN", "INSURANCE_ID") else digits(value))
        return [Cand(s, e, kind, norm, "patient")]

    if role == "dob" and re.fullmatch(r"(?:18|19|20)\d{2}", value):
        return [Cand(s, e, "DOB", None, "patient")]     # a birth year: no ISO date to give as norm
    if role in ("dob", "date"):
        return [c._replace(start=c.start + s, end=c.end + s)
                for c in find_dates(value, dmy, is_dob_field=role == "dob")]

    if role in ("age", "age_sex"):
        out = []
        m = re.match(r"\D{0,6}?(\d{1,3})(?![\d.-]|/\d)", value)
        if m:
            out.append(Cand(s + m.start(1), s + m.end(1), "AGE", str(int(m.group(1))), "patient"))
        g = re.search(r"(?<![A-Za-z])(male|female|पुरुष|महिला|[MF])(?![A-Za-z])", value, re.I)
        if g:
            out.append(Cand(s + g.start(1), s + g.end(1), "GENDER", gender_norm(g.group(1)), "patient"))
        return out

    if role == "gender":
        word = re.match(r"[^\s,/|(]+", value)
        norm = gender_norm(word.group(0)) if word else None
        return [Cand(s, s + word.end(), "GENDER", norm, "patient")] if norm else []

    if role == "pin":
        m = re.search(r"(?<!\d)[1-9]\d{2} ?\d{3}(?!\d)", value)
        return [Cand(s + m.start(), s + m.end(), "PIN", m.group(0).replace(" ", ""), "patient")] if m else []

    if role in ("village", "district"):
        if "," in value:
            return parse_address(text, s, e)
        cut = re.search(r"\s{2,}|\(|\||;| - |\d{6}", value)
        if cut:
            s, e = _strip(text, s, s + cut.start())
        value = text[s:e]
        if not value or len(value) > 40 or _NOT_A_NAME.match(value) or not re.search(r"[A-Za-zऀ-ॿ]{3}", value):
            return []
        return [Cand(s, e, role.upper(), norm_name(value), "patient")]

    if role == "address":
        return parse_address(text, s, e)
    return []
