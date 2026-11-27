"""detect_file: the real implementation of contracts/detect.md.

For one file:
  1. work out the role of every column / JSON key (labels.py, then the values themselves)
  2. collect candidates for every field (structured rules + free-text rules)
  3. copy names and record numbers found anywhere to everywhere else in the file
     (file names, headers, metadata, narrative text)
  4. drop overlaps, then build the Evidence for linking

Pure: no printing, files or network. No iteration over sets (output must be deterministic).
"""
from __future__ import annotations

import base64
import binascii
import re

from aegis.detect import address, dates, evidence, fields, gazetteer, hl7, ids, names
from aegis.detect.labels import _owner, category_column, classify, extra_checks, names_a_relative, person_holder, tokens
from aegis.detect.normalize import DEVA, decode_view, digits, fold, norm_name, visible
from aegis.detect.spans import PRIORITY, PROPAGATED, Cand, resolve
from aegis.types import DIRECT_TYPES, QUASI_TYPES, STRONG_ID_TYPES, Record, RecordResult, empty_evidence

NAME_TYPES = ("PATIENT_NAME", "RELATIVE_NAME")
# two or more of these words mean the sentence is Hinglish (Hindi written in Latin letters)
_HINGLISH = re.compile(r"\b(?:ka|ki|ke|ko|ne|hai|hain|nahi|raha|rahe|rahi|gaya|gayi|diya|liya|se|mein|aur|ji|sahab|behenji|bhai)\b")
_CONDITION_KEYS = ("diagnosis", "diagnoses", "condition", "dx", "icd", "निदान")
_LABEL_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<label>[^:=\n]{1,40}?)\s*(?::(?!\d|//)|=| - | – )[ \t]*(?P<value>.*)$")
# "नाम- <name>": tried only when the line has none of the separators above
_NAME_DASH_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<label>[^:=\n]{1,40}?)(?<![\s\d])- [ \t]*(?P<value>.*)$")
# a "label" that ends in a URL query parameter ("...?_format"); "Patient?: yes" does not
_QUERY_TAIL = re.compile(r"\?[^\s?]+$")
_NAME_LABEL_WORDS = frozenset(("name", "naam", "nm", "नाम"))


# ---------------------------------------------------------------- 1. roles

def _segments(path: str) -> list[str]:
    # "/note#b64:0" is the text inside a base64 run of "/note" (made by io): it reads like its parent field
    return [p.replace("~1", "/").replace("~0", "~") for p in path.partition("#b64:")[0].split("/")[1:]]


def _json_label(path: str) -> tuple[str, tuple[str, ...]]:
    keys = [p for p in _segments(path) if not p.isdigit()]
    if not keys:
        return "", ()
    return keys[-1], tuple(keys[:-1])


def _fhir_types(records: list[Record]) -> dict[str, str]:
    """pointer of an object -> its FHIR resourceType."""
    return {f["path"].rsplit("/", 1)[0]: f["value"] for r in records for f in r["fields"]
            if f["path"].startswith("/") and f["path"].endswith("/resourceType")}


# Identifier.value of a person: whatever its shape it names the patient. The system / type beside it may say which kind.
_PERSON_RESOURCES = ("Patient", "RelatedPerson", "Person")
_PERSON_REFS = ("subject", "patient", "beneficiary")     # Observation.subject.identifier is the patient's too
_NOT_PERSON_IDENTIFIER = ("assigner", "managingOrganization", "generalPractitioner", "performer", "author", "requester")
_IDENT_PARTS = ("identifier", "identifiers")
_IDENT_VALUE_KEYS = ("value", "number", "id", "val")
PID = "pid:"      # role prefix: "this value is a patient identifier of the kind after the colon, whatever its shape"


def _identifier_kind(holder: str, by_path: dict[str, str]) -> str:
    """Kind of identifier an Identifier object (the pointer `holder`) says it holds: an ID_ROLES role, "mrn" by default."""
    for leaf in ("system", "label", "type/text", *(f"type/coding/{i}/{k}" for i in range(3) for k in ("code", "display", "system"))):
        text = by_path.get(f"{holder}/{leaf}")
        role = classify(re.split(r"[/#:]", text.rstrip("/"))[-1]) if text else None
        if role in fields.ID_ROLES:
            return role
    return "mrn"


def _identifier_role(path: str, below: list[str], kind: str | None, by_path: dict[str, str]) -> str | None:
    if not below or below[-1] not in _IDENT_VALUE_KEYS or not any(p in _IDENT_PARTS for p in below):
        return None
    if set(below) & set(_NOT_PERSON_IDENTIFIER) or not (kind in _PERSON_RESOURCES or set(below) & set(_PERSON_REFS)):
        return None
    return PID + _identifier_kind(path.rsplit("/", 1)[0], by_path)


def _plain_identifier_role(path: str, label: str, parents: tuple[str, ...], by_path: dict[str, str]) -> str | None:
    """{"patient": {"identifier": [{"system": ..., "value": ...}]}}: the same rule for JSON that is not FHIR."""
    keys = [*parents, label]
    at = max((i for i, k in enumerate(keys) if k in _IDENT_PARTS), default=-1)
    if at < 0 or set(keys) & set(_NOT_PERSON_IDENTIFIER):
        return None
    if not (at == len(keys) - 1 or (at == len(keys) - 2 and label in _IDENT_VALUE_KEYS)):
        return None
    if at == 0 or _owner((re.sub(r"s$", "", keys[at - 1]),)) not in ("patient_name", "relative_name"):   # the key just above
        return None
    return PID + (_identifier_kind(path.rsplit("/", 1)[0], by_path) if at == len(keys) - 2 else "mrn")


def _fhir_role(path: str, role: str | None, types: dict[str, str], by_path: dict[str, str]) -> str | None:
    parts = path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        kind = types.get("/".join(parts[:i]))
        if kind:
            below = [p for p in parts[i:] if not p.isdigit()]
            break
    else:
        return role
    if pid := _identifier_role(path, below, kind, by_path):
        return pid
    if "subject" in below and below[-1] == "display":
        return "patient_name"
    if below[-1] == "display" and any(p in below for p in ("author", "performer", "requester", "recorder", "asserter")):
        return "doctor"
    if "name" in below:
        if kind in ("Practitioner", "PractitionerRole"):
            return "doctor"
        if kind not in ("Patient", "RelatedPerson", "Person"):
            return "keep"
        if kind == "RelatedPerson" or "contact" in below:
            return "relative_name"
        return {"given": "first_name", "family": "last_name"}.get(below[-1], "patient_name")
    if "relationship" in below:
        return "relation"
    return role


# {"subject": {"display": X}}: leaves that hold a person's name when the key just above them names only a person
_NAME_LEAVES = ("display", "text", "full")
_BRACKET_TAIL = re.compile(r" *\([^()\n]*\)\s*$")


def _person_leaf_role(path: str, value: str) -> str | None:
    """The role of a name written as the "display" / "text" of a person, in JSON of any kind. The value must read as a
    whole name: "subject": {"text": "Discharge Summary"} and "patient": {"text": "stable since morning"} stay text."""
    label, parents = _json_label(path)
    if label.casefold() not in _NAME_LEAVES or not parents:
        return None
    role = person_holder(parents[-1])
    if not role or (label.casefold() == "text" and "subject" in tokens(parents[-1])):   # a subject line is a topic
        return None
    text = _BRACKET_TAIL.sub("", fold(value))
    found = fields.name_value(text, 0, len(text), role)
    # the name must be the whole value (titles aside): anything longer is read as ordinary text
    if len(found) != 1 or text[found[0].end:].strip(" .,;|\"'"):
        return None
    title = fields._TITLES.match(text)
    if text[title.end() if title else 0:found[0].start].strip(" \"'"):
        return None
    name = text[found[0].start:found[0].end]
    if not gazetteer.reads_as_full_name(name, names.STOP | names.ORG):
        return None
    # "text" also holds narrative ("Under Observation"), so the shape is not enough there: it needs a title, an
    # initial, "Surname, Given" or a listed surname
    if label.casefold() == "text" and not (title or "," in name or re.search(r"(?<!\w)[A-Z]\.", name)
                                           or gazetteer.has_surname(name)):
        return None
    return role


_PAIR_VALUE = re.compile(r"^(?:value[A-Za-z]*|answer|val|data_value)$")
_PAIR_LABEL = ("url", "field", "label", "key", "name", "attribute", "question")


def _pair_role(path: str, by_path: dict[str, str]) -> str | None:
    """{"url": ".../mothers-name", "valueString": X}  or  {"field": "mobile", "value": X}."""
    holder, _, key = path.rpartition("/")
    if not _PAIR_VALUE.match(key):
        return None
    for label_key in _PAIR_LABEL:
        label = by_path.get(f"{holder}/{label_key}")
        if label:
            role = classify(re.split(r"[/#]", label.rstrip("/"))[-1])
            return None if role in ("keep", "free", "date", "name") else role
    return None


def field_roles(records: list[Record]) -> dict[tuple[str, str], str | None]:
    types = _fhir_types(records)
    roles: dict[tuple[str, str], str | None] = {}
    by_path = {f["path"]: f["value"] for r in records for f in r["fields"] if f["path"].startswith("/")}
    columns: dict[str, list[tuple[str, str]]] = {}
    col_label: dict[str, str] = {}      # table columns only: path -> header
    for r in records:
        for f in r["fields"]:
            key = (r["record_id"], f["path"])
            if f["kind"] != "value":
                continue
            if f["path"].startswith("col:"):
                role = classify(f["context"] or "")
                columns.setdefault(f["path"], []).append(key)
                col_label[f["path"]] = f["context"] or ""
            else:
                label, parents = _json_label(f["path"])
                role = classify(label, parents)
                if types:
                    role = _fhir_role(f["path"], role, types, by_path)
                if not (role or "").startswith(PID):
                    role = _plain_identifier_role(f["path"], label, parents, by_path) or role
                role = _pair_role(f["path"], by_path) or role
                columns.setdefault(re.sub(r"/\d+(?=/|$)", "/*", f["path"]), []).append(key)
            roles[key] = role
    # unknown column: decide from its values (hidden data renames headers)
    values = {(r["record_id"], f["path"]): f["value"] for r in records for f in r["fields"]}
    labels = {(r["record_id"], f["path"]): (f["context"] or "") if f["path"].startswith("col:")
              else _json_label(f["path"])[0] for r in records for f in r["fields"]}
    # a doctor column without "Dr." in it: the same people are written "Dr. X" somewhere else in the file
    doctors = {" ".join(names.doctor_name(m)) for text in values.values() for m in names.doctor_mentions(text)}
    has_name = any(role in ("patient_name", "name", "first_name") for role in roles.values())
    guesses = {}
    for path, keys in columns.items():
        if roles[keys[0]] is None:
            guesses[path] = _guess_role([values[k] for k in keys if values[k].strip()], col_label.get(keys[0][1], ""),
                                        keys[0][1] in col_label)
    # a column that only looks like names counts when its rows share surnames with another column of people
    people_cols = [keys for path, keys in columns.items()
                   if roles[keys[0]] in _NAME_ROLES or guesses.get(path) in ("patient_name", PERSON_SHAPED)]
    for path, keys in columns.items():
        if guesses.get(path) == PERSON_SHAPED:
            guesses[path] = "patient_name" if _shares_surnames(keys, people_cols, values) else None
    for path, keys in columns.items():
        if roles[keys[0]] is None:
            guess = guesses[path]
            if guess == "patient_name":
                filled = [values[k] for k in keys if values[k].strip()]
                # most of the column, never a single match: one patient who shares a doctor's name must not
                # expose every other patient
                if 2 * sum(" ".join(names.name_words(v)) in doctors for v in filled) > len(filled):
                    guess = "doctor"
            if guess == "patient_name":
                # a second column full of people is usually the relative
                guess, has_name = ("relative_name" if has_name else "patient_name"), True
            for k in keys:
                roles[k] = guess
    # after the column guesses: these roles depend on the value, so they are decided one value at a time
    for key, role in roles.items():
        # {"subject": "Referral - <name>"}: the title of a mail, not the patient's name
        if role == "patient_name" and names.mail_subject_label(tokens(labels[key])) and names.is_topic(values[key]):
            roles[key] = None
        elif role in (None, "keep") and not key[1].startswith("col:"):
            roles[key] = _person_leaf_role(key[1], values[key]) or role
    return roles


def _is_mobile(value: str) -> bool:
    """Ten digits starting 6-9 (with an optional 0 or +91), and nothing but phone punctuation."""
    if not re.fullmatch(r"\+?[\d ().-]{10,20}", value) or re.search(r"\d\.\d{1,2}$", value):
        return False
    d = re.sub(r"\D", "", value)
    if value.startswith("+91"):
        d = d[2:]
    elif len(d) == 11 and d[0] == "0":
        d = d[1:]
    return len(d) == 10 and d[0] in "6789"


def _guess_role(vals: list[str], label: str = "", column: bool = False) -> str | None:
    if len(vals) < 3:
        return None
    if all(re.fullmatch(r"[1-9]\d{2}(?!000)\d{3}", v.strip()) for v in vals):
        return "pin"
    # phone numbers, however they are spaced ("9412 7 30518")
    # every cell: one that is not a number may name a person, and a phone column is not searched for names
    if all(_is_mobile(fold(v).strip()) for v in vals):
        return "phone"
    if all(re.fullmatch(r"(?:19[1-9]\d|20[0-2]\d)", v.strip()) for v in vals):
        yrs = [int(v.strip()) for v in vals]
        # diagnosis, admission or follow-up years are recent and close together; patients' birth years are not
        if max(yrs) - min(yrs) >= 10 and sorted(yrs)[len(yrs) // 2] < 1995:
            return "dob"
    # addresses: most values carry a house number, landmark or PIN together with a comma
    addresses = [v for v in vals if "," in v and any(c.type in ("HOUSE", "LANDMARK", "LOCALITY", "PIN")
                                                     for c in address.find_places(fold(v)))]
    if len(addresses) >= 0.6 * len(vals) and all(len(v) <= 90 for v in vals):
        return "address"
    folded = [fold(v).strip() for v in vals]
    people = [v for v in folded
              if re.fullmatch(r"[A-Z][A-Za-z.']*(?: [A-Z][A-Za-z.']*){1,3}", v) or fields.surname_first(v)]
    with_surname = [v for v in people if set(v.casefold().replace(",", " ").split()) & gazetteer.SURNAMES]
    if len(people) >= 0.7 * len(vals) and len(with_surname) >= 0.4 * len(vals):
        return "patient_name"
    # a table column whose cells nearly all read as 2-3 word person names, surnames listed or not: the whole
    # column is a name column (the cells that happen to carry a listed surname must not be the only ones removed)
    if column and not category_column(label):
        persons = [v for v in folded if gazetteer.looks_like_person_cell(v, names.STOP | names.ORG)
                   and v.casefold() not in address._UP_DISTRICTS]
        if len(persons) >= 0.8 * len(vals) and len(set(folded)) >= max(3, 0.3 * len(vals)):
            # "looks like two capitalised words" alone also fits organisms, drugs and vaccines ("Escherichia Coli",
            # "Piperacillin Tazobactam", "Measles Rubella"). Some evidence of people is needed: a listed surname in
            # at least one cell (and a fifth of them), or, decided in field_roles, surnames shared row by row with
            # another column of people ("Bhagwati Rajak" / "Sohan Rajak").
            surnames = gazetteer.SURNAMES | gazetteer.DEVA_SURNAMES
            listed = sum(1 for v in persons if set(v.casefold().split()) & surnames)
            return "patient_name" if listed >= max(1, 0.2 * len(vals)) else PERSON_SHAPED
    return None


PERSON_SHAPED = "person_shaped"     # an unknown column that looks like names but carries no listed surname
_NAME_ROLES = ("patient_name", "relative_name", "name", "first_name", "last_name")


def _shares_surnames(keys: list[tuple[str, str]], others: list[list[tuple[str, str]]],
                     values: dict[tuple[str, str], str]) -> bool:
    """At least half the filled rows of this column (and two or more) end in the same word as a column of people
    in the same row."""
    def last(v: str) -> str:
        words = fold(v).replace(",", " ").split()
        return words[-1].casefold() if words and len(words[-1]) >= 3 else ""
    mine = {rid: last(values[(rid, p)]) for rid, p in keys if values[(rid, p)].strip()}
    shared = 0
    for rid, word in mine.items():
        if word and any(last(values.get((rid, ok[0][1]), "")) == word for ok in others if ok[0][1] != keys[0][1]):
            shared += 1
    return shared >= max(2, 0.5 * len(mine))


# ---------------------------------------------------------------- 2. candidates

def _labelled(text: str, dmy: bool) -> list[Cand]:
    """'Patient Name: X        Age/Sex: 52/F' lines inside free text."""
    out = []
    pos = 0
    for line in text.split("\n"):
        # several "label: value" pairs can share a line, separated by wide gaps or pipes
        # a comma or semicolon followed by "something:" starts the next label
        for m in re.finditer(r"(?:(?! {3}|\t|\||[;,](?=[^,;:|\n]{1,30}:(?!\d))|;).)+", line):
            lab = _LABEL_LINE.match(m.group(0))
            if not lab:
                lab = _NAME_DASH_LINE.match(m.group(0))
                if not lab or not set(tokens(lab.group("label"))) & _NAME_LABEL_WORDS:
                    continue  # "Patient- stable" is a sentence, "नाम- <name>" is a label
            label = lab.group("label")
            if _QUERY_TAIL.search(label):
                continue  # "Patient/p1?_format=json": a reference or URL with a query, not a "label=value" line
            if re.search(r"\d{4}", label):
                continue  # "PAN ABCDE1234F: BP 118/76": the "label" holds the number itself
            dashed = not re.match(r"\s*[:=]", m.group(0)[lab.end("label"):])
            # a dash is a weak separator ("Ward 4 - ..."): require the label to be short and digit-free
            if dashed and (len(label.split()) > 5 or any(ch.isdigit() for ch in label)):
                continue
            if names.mail_subject_label(tokens(label)):
                continue  # a mail subject is a topic: names.subject_lines reads it
            role = classify(label)
            if role in (None, "free", "keep", "doctor", "date", "relation", "tehsil"):
                continue
            base = pos + m.start()
            end = base + lab.end("value")
            if role in ("address", "village", "district"):
                stop = re.search(r"।|\)(?![^(]*\()", lab.group("value"))  # not ".": "Vill. X", "Distt. Y"
                end = base + lab.start("value") + stop.start() if stop else end
            found = fields.structured(text, base + lab.start("value"), end, role, dmy)
            if role in fields.NAME_ROLES:
                relation = fields.relation_of(label)
                father = re.search(r"father|पिता", label, re.I)
                found = [c._replace(relation=c.relation or relation or ("S/o" if father else None)) for c in found]
            out.extend(found)
        pos += len(line) + 1
    return out


def _conditions(text: str, role: str | None, label: str, parents: tuple[str, ...]) -> list[Cand]:
    """CONDITION is information for privacy (rare-disease handling), not an identifier."""
    out = []
    if set(tokens(label)) & set(_CONDITION_KEYS) or (set(parents) & set(_CONDITION_KEYS) and label in ("display", "code", "text")):
        if text.strip():
            out.append(Cand(0, len(text), "CONDITION", " ".join(text.casefold().split()), None))
    for m in re.finditer(r"\bK/C/O +(?P<c>[^\n.;,|]{2,50}?)(?=$|[\n.;,|]| x \d)", text):
        if not m.group("c").startswith(("DM/HTN", ":")):
            out.append(Cand(m.start("c"), m.end("c"), "CONDITION", m.group("c").casefold(), None))
    return out


def _next_to_mrn(text: str, found: list[Cand]) -> list[Cand]:
    """In headers, keys and file names, a word right after a record number is the patient's name."""
    out = []
    for c in found:
        if c.type == "MRN":
            m = re.compile(r"[ _:|-]+(?P<name>[A-Z][a-z]+(?:[ _][A-Z][a-z]+){0,2})(?![A-Za-z])").match(text, c.end)
            if m and m.group("name").casefold() not in names.STOP:
                out.append(Cand(m.start("name"), m.end("name"), "PATIENT_NAME", None, "patient"))
    return out


_B64_STEM = re.compile(r"^[A-Za-z0-9+/]{16,}={0,2}$")


def _b64_filename_cands(text: str, dmy: bool) -> list[Cand]:
    stem, dot, _ext = text.rpartition(".")
    if not dot:
        stem = text
    if not _B64_STEM.fullmatch(stem):
        return []
    try:
        dec = base64.b64decode(stem + "=" * (-len(stem) % 4)).decode("utf-8")
    except (binascii.Error, ValueError):
        return []
    if not dec or sum(c.isprintable() or c in "\n\r\t" for c in dec) < 0.95 * len(dec):
        return []
    inner = candidates({"path": "text", "kind": "text", "context": None, "value": dec}, None, dmy)
    if any(c.type in DIRECT_TYPES or c.type in QUASI_TYPES for c in inner):
        return [Cand(0, len(stem), "PATIENT_NAME", norm_name(dec) or None, "patient", prio=PRIORITY["PATIENT_NAME"] + 2)]
    return []


_STEM_TOK = re.compile(
    r"(?=[A-Za-z0-9])[A-Za-z]+\d+[A-Za-z][A-Za-z0-9]*|[a-z]+\d+[a-z0-9]*|\d+[a-z][a-z0-9]*|[0-9a-f]{6,}(?![A-Za-z0-9])"
    r"|[A-Z][a-z']+(?=[A-Z]|[^A-Za-z]|$)|[A-Z]+(?=[A-Z][a-z]|[^A-Za-z]|$)|[a-z']+"
    r"|[\u0900-\u0963\u0971-\u097f]+|\d+|[\u0966-\u096f]+"
)
_STEM_CODE = re.compile(r"^(?:\d|[\u0966-\u096f]|[A-Za-z]+\d+[A-Za-z]|[a-z]+\d|[0-9a-f]{6,}$)")
_STEM_PATIENT_DOC = frozenset(
    "ipd opd ds rx lab labs report reports discharge summary consent prescription note notes memo referral "
    "bill bills claim claims invoice receipt record records file case sheet card history followup follow "
    "patient patients pt uhid mrn crn admission newborn delivery palliative angio biopsy culture "
    "xray ecg usg cbc ogtt pcr anc nrc dots sickle electrophoresis immunisation immunization dialysis "
    "cataract fever sugar iron scan test result results hb form "
    "रिपोर्ट पर्चा पर्ची डिस्चार्ज भर्ती छुट्टी दवा जांच जाँच फाइल फ़ाइल कार्ड फार्म फॉर्म "
    "टीकाकरण प्रसव विवरण क्षय उपचार एएनसी सोनोग्राफी हीमोग्लोबिन रक्तचाप रक्त नसबंदी एक्सरे".split()
)
_STEM_ADMIN_DOC = frozenset(
    """
    audit census occupancy turnaround roster schedule protocol guideline guidelines sop manual handbook module
    training workshop seminar orientation awareness handout circular minutes agenda meeting committee samiti
    yojana scheme abhiyan mission campaign program programme strategy score scoresheet indicator indicators metric
    metrics stats statistics aggregate totals trend backlog compliance accreditation assessment evaluation inspection
    stock inventory indent reorder supply expiry wastage utilization utilisation availability consumption usage
    downtime maintenance repair calibration qc eqas antibiogram validation excursion excursions mismatch sync errors
    rejections failures defaulters pending template format blank mock drill fumigation manifest refill tracker
    readings times trip diet formulary archive backup export dump log logbook register line linelist microplan
    session booth site sites blockwise footfall grievance grievances expenditure rates dbt helpdesk directory index
    chc phc dh sdh uhc district state national block subcentre subcenter baithak karaywahi parchi samaan mang
    patra kayakalp anm asha peer educator supervisor nurses attendant workers staff duty safai karmi roster
    analyzer analyser slit lamp chair dental freezer cylinder plant purity autoclave spore cold chain bag bags kit
    kits reagent reagents stain worklist anti rabies sucrose infusion birth dose coverage spray irs
    mda hand hygiene needle stick injury waste biomedical bmw ambulance linen laundry canteen mortuary diesel
    generator dg oxygen psa blood bank component components crossmatch donation camp film ultrasound echo leprosy
    malaria dengue chikungunya encephalitis typhus leptospirosis diarrhoeal anaemia anemia thalassemia hepatitis
    hiv ictc syphilis rapid gram widal hba1c biochem hematology histopath pcpndt ct ifa ors zinc amoxicillin
    paracetamol oxytocin magsulf metformin amlodipine venom artemether lumefantrine bedaquiline delamanid isoniazid
    albendazole deworming vaccine penta polio hpv setu swasthya swachh arogya mandir final
    rbsk rksk jsy jssk nvbdcp ntep npcdcs nlep npcb nmhp idsp ihip hmis rch uwin evin ilr amc
    मासिक दैनिक साप्ताहिक वार्षिक प्रगति प्रतिवेदन आंकड़े आँकड़े गणना पंजी पंजिका प्रारूप योजना परियोजना अभियान
    मिशन कार्यक्रम कार्ययोजना प्रशिक्षण कार्यशाला बैठक समिति कल्याण स्वच्छता प्रोत्साहन राशि भंडार कोष स्टॉक लॉगबुक
    सूक्ष्म गतिविधि पखवाड़ा सप्ताह अवकाश आवेदन पत्र मांग आपूर्ति वितरण खपत उपयोग सत्यापन निरीक्षण टिप्पणी मूल्यांकन
    उन्मूलन रोकथाम प्रबंधन नीति नियमावली मानक कार्यकर्ता एएनएम आंगनवाड़ी पर्यवेक्षक महिला शिशु मातृ बाल किशोर जननी
    परिवार नियोजन माह दिवस उत्सव मेला आरोग्य आयुष्मान मंदिर कायाकल्प इन्द्रधनुष इंद्रधनुष दस्तक वंदना प्रधानमंत्री
    मुख्यमंत्री भारत मुक्त शीत श्रृंखला तापमान सिलेंडर ऑक्सीजन एम्बुलेंस जनवरी फरवरी मार्च अप्रैल मई जून जुलाई अगस्त
    सितंबर अक्टूबर नवंबर दिसंबर पुरुष पंजीयन
    """.split()
)
_STEM_STAFF = frozenset("dr doctor prof nurse sister surgeon consultant physician resident डॉ डा डॉक्टर नर्स".split())
_STEM_ORG_ADJ = frozenset(
    "hospital hospitals clinic clinics centre center memorial trust foundation school college university "
    "pharmacy medicals scheme yojana samiti abhiyan mission mela baithak circular "
    "अस्पताल हॉस्पिटल क्लिनिक संस्थान ट्रस्ट योजना समिति अभियान मिशन".split()
)
_STEM_NON_NAME_SUFFIX = re.compile(
    r"(?:tion|sion|ment|ance|ence|ness|logy|ography|ometry|oscopy|ectomy|itis|osis|emia|aemia|"
    r"pathy|plasia|penia|algia|uria|able|ible|ious|eous|tory|ware|ship)$"
)
_STEM_VOCAB = frozenset(
    """
    infection control prevention rounds prevention sample samples check checklist slip voucher payment tariff
    package reimbursement cash credit ledger account analytics dashboard alert notification message forward fwd reply
    query ticket tickets support desk counter reception enquiry inquiry feedback complaint feedback grievance
    visitor pass gate security transport primary secondary tertiary rural urban central public private annexure
    appendix enclosure scan scanned photo image pdf doc xls csv json xml txt misc common standard routine urgent
    stat unknown other others all none na nil english hindi hinglish latin devanagari deva roman tamil telugu
    bengali marathi urdu ambiguous corrupt cryptic extreme rare homonym obfuscated transitive chain trap dense
    triple unfamiliar unlabeled unlabelled escalation unseen synthetic variant variants lowercase stream wrapped
    late binary after mixed ragged depth bomb nested single five token tokens multi v1 v2 v3 bundle unicode
    escape escaped semicolon colon pipe delim delimiter comma utf ascii hex base64 jsonl ndjson tsv fhir encoding
    charset locale payload chunk chunks header headers footer body meta key keys value values path paths dir root
    tree node nodes array object string text bytes char chars zero width bilinear creatinine bilirubin cholesterol
    albumin globulin electrolytes potassium calcium magnesium urea amylase lipase troponin ferritin folate vitamin
    esr lft kft rft tft abg vbg inr aptt crp mantoux hbsag hcv vdrl elisa sensitivity smear fnac ekg eeg emg tmt
    doppler mri pet dexa whatsapp hl7 cda city deep bulk mislabeled truncated lifeline pathkind response express
    service ophthalmology chart poshan sahay
    """.split()
) | names.STOP | names.ORG | gazetteer.NOT_A_PERSON_WORDS | gazetteer._COLUMN_NOT_PERSON | _STEM_PATIENT_DOC | _STEM_ADMIN_DOC | _STEM_STAFF
_DEVA_STEM_VOCAB = (
    names.HI_NOT_NAME | gazetteer.DEVA_NOT_NAME | gazetteer.DEVA_PLACE_OR_ORG
    | gazetteer._DEVA_COLUMN_NOT_PERSON | _STEM_PATIENT_DOC | _STEM_ADMIN_DOC | _STEM_STAFF
    | frozenset(("पोषण",))
)


def _is_stem_vocab(tok: str, kind: str) -> bool:
    if kind == "num":
        return True
    if kind == "deva":
        return tok in _DEVA_STEM_VOCAB
    w = tok.casefold()
    return (
        len(w) < 2
        or w in _STEM_VOCAB
        or (tok.isupper() and len(tok) <= 5)
        or bool(_STEM_NON_NAME_SUFFIX.search(w))
        or bool(gazetteer._DIAGNOSIS_ENDING.search(w))
    )


def _is_stem_admin(tok: str, kind: str) -> bool:
    if kind == "num":
        return False
    if kind == "deva":
        return tok in _STEM_ADMIN_DOC
    return tok.casefold() in _STEM_ADMIN_DOC


def _filename_name_cands(text: str) -> list[Cand]:
    """Detect 2-3 word patient names inside dashed, CamelCase, spaced, or Devanagari filename stems."""
    slash = max(text.rfind("/"), text.rfind("\\"))
    base_start = slash + 1
    dot = text.rfind(".", base_start)
    stem_end = dot if dot > base_start else len(text)
    if stem_end <= base_start:
        return []
    stem = text[base_start:stem_end]
    toks = []
    for m in _STEM_TOK.finditer(stem):
        w = m.group(0)
        kind = "num" if _STEM_CODE.match(w) else ("deva" if DEVA.match(w[0]) else "latin")
        toks.append((base_start + m.start(), base_start + m.end(), w, kind))
    if len(toks) < 2:
        return []

    out: list[Cand] = []
    surnames = gazetteer.SURNAMES | gazetteer._SURNAME_NO_APOSTROPHE | gazetteer.DEVA_SURNAMES
    given = gazetteer.GIVEN_NAMES | gazetteer.DEVA_GIVEN_NAMES
    n = len(toks)
    used = [False] * n
    for length in (3, 2):
        for i in range(n - length + 1):
            if any(used[i:i + length]):
                continue
            span = toks[i:i + length]
            script = span[0][3]
            if script == "num" or any(t[3] != script or _is_stem_vocab(t[2], t[3]) for t in span):
                continue
            if i > 0 and toks[i - 1][2].casefold() in _STEM_STAFF:
                continue
            if any(t[2].casefold() in _STEM_ORG_ADJ for t in (toks[i - 1:i] + toks[i + length:i + length + 1])):
                continue
            has_surn = any(t[2].casefold() in surnames for t in span)
            has_given = any(t[2].casefold() in given for t in span)
            outside = toks[:i] + toks[i + length:]
            all_outside_vocab = all(_is_stem_vocab(t[2], t[3]) for t in outside)
            has_admin = any(_is_stem_admin(t[2], t[3]) for t in outside)
            has_patient_doc = any(
                (t[3] == "num" and t[2].isdigit()) or t[2].casefold() in _STEM_PATIENT_DOC
                for t in outside
            )
            if has_given and has_surn:
                pass  # strong: both listed given name and listed surname
            elif (has_given or has_surn) and all_outside_vocab and not has_admin:
                pass  # one listed part + clean doc/clinical context
            elif (not has_admin and all_outside_vocab and has_patient_doc
                  and (script != "latin" or all(len(t[2]) >= 3 for t in span))):
                pass  # unseen full name inside an individual patient clinical file
            else:
                continue
            out.append(Cand(span[0][0], span[-1][1], "PATIENT_NAME", None, "patient"))
            for k in range(i, i + length):
                used[k] = True
    return out


# In a lookup table ("..._map", "..._index") the keys are data, not field names. A capitalised key is only taken for a
# person when the table's name is about people or whom to contact: "billing_map" keys look just like names.
_PEOPLE_WORDS = frozenset("patient patients person people contact contacts caller callers call escalation family kin "
                          "relative relatives attendant".split())
_LOOKUP_WORDS = frozenset(("map", "lookup", "index", "directory"))
_FIELD_MAP_WORDS = frozenset(("field", "column", "header", "label", "key"))   # keyed by field names


def _is_lookup_table(holder: str) -> bool:
    words = tokens(holder)
    # "drug_index" or "ward_map" are keyed by drugs and wards
    return (bool(words) and words[-1] in _LOOKUP_WORDS and bool(set(words) & _PEOPLE_WORDS)
            and not set(words) & _FIELD_MAP_WORDS and all(classify(w) not in ("keep", "free") for w in words[:-1]))


def _looks_like_person(key: str) -> bool:
    """Two to four capitalised words, none of them a field, medical, report, place or organisation word."""
    if not re.fullmatch(r"[A-Z][a-z']+(?: [A-Z][a-z']+){1,3}", key.strip()) or classify(key) is not None:
        return False
    return not set(key.casefold().split()) & (names.STOP | gazetteer.NOT_A_PERSON_WORDS)


# labels that say the value beside them is a person; classify() gives these no role of its own
_PERSON_CLUES = frozenset("reviewer reviewers verifier signatory witness nominee informant attendant escort guardian "
                          "kin spouse mother mothers father fathers maiden caller callee contact person".split())


def _person_labels(by_path: dict[str, str]) -> set[str]:
    """Paths whose own key, or the label paired with them ({"url": ".../mothers-maiden-name", "valueString": X}),
    points at a person."""
    out = set()
    for path in by_path:
        holder, _, key = path.rpartition("/")
        labels = [key]
        if _PAIR_VALUE.match(key):
            labels += [re.split(r"[/#]", by_path.get(f"{holder}/{k}", "").rstrip("/"))[-1] for k in _PAIR_LABEL]
        if any(set(tokens(label)) & _PERSON_CLUES for label in labels):
            out.add(path)
    return out


def candidates(f: dict, role: str | None, dmy: bool, person_label: bool = False) -> list[Cand]:
    text = fold(f["value"])
    kind = f["kind"]
    label, parents = ("", ())
    if kind == "value":
        label, parents = (f["context"] or "", ()) if f["path"].startswith("col:") else _json_label(f["path"])

    # the value of a person's Identifier: a patient identifier whatever its shape (kind: see _identifier_kind)
    forced = None
    if role and role.startswith(PID):
        forced, role = role[len(PID):], role[len(PID):]

    # a record number always has a digit: "patient_ref" holding words is read like any unknown value
    if role == "mrn" and kind == "value" and not forced and not re.search(r"\d", text):
        role = None

    # the header is only a hint: a "PIN" column may really hold the whole address ("Home Place & PIN"),
    # or words with no PIN at all, which are then read like any unknown value
    if role == "pin" and kind == "value":
        if address.holds_address(text):
            role = "address"
        elif address.has_no_pin(text):
            role = None

    found = ids.find_ids(text)
    if role in fields.ID_ROLES:
        found = []  # structured() returns the same ids, or the whole value if no shape matched
    if role in ("doctor", "keep", "relation", "tehsil", "gender", "district", "village"):
        extra: list[Cand] = []
    else:
        extra = dates.find_dates(text, dmy, is_dob_field=role == "dob")
    found += extra
    if role == "relation":
        found += fields.kin_and_name(text)
    if role not in (None, "free"):
        found += fields.structured(text, 0, len(text), role, dmy)
    # "परिजन_संपर्क", "relative mobile": the cell may name the relative as well as, or instead of, giving a number
    if role == "phone" and kind == "value" and names_a_relative(label):
        found += fields.relative_in_contact(text)

    if role in (None, "free", "date", "bed_patient"):
        found += dates.find_ages(text)
        found += address.find_places(text)
        found += names.find_names(text)
        # in file names, headers and keys "_" separates words
        scan_text = text.replace("_", " ") if kind in ("filename", "header", "key") else text
        found += gazetteer.find_listed_names(scan_text, names.STOP)
        if kind not in ("filename", "header", "key"):
            found += gazetteer.find_joined_names(text, names.STOP)
        found += _labelled(text, dmy)
        found += names.subject_lines(text)
        if kind == "value" and names.mail_subject_label(tokens(label)):
            found += names.subject_line(text, 0, len(text), bare=True)
    if role is None and kind == "value":
        extra_check = extra_checks(label)
        if extra_check == "place" and not set(tokens(text)) & names.MEDICAL:
            found += address.parse_address(text, 0, len(text))
        elif extra_check == "phone":
            found += fields.structured(text, 0, len(text), "phone", dmy)
        elif extra_check == "student":
            found += fields.name_value(text, 0, len(text), "name")
    if forced and text.strip() and not any(c.type in fields.ID_ROLES.values() and text[c.start:c.end] == text.strip()
                                           for c in found):
        # no known shape (digits only, a short code): all of the value is the identifier
        a = len(text) - len(text.lstrip())
        b = len(text.rstrip())
        kind_of = fields.ID_ROLES[forced]
        if kind_of != "MRN" and not any(c.type == kind_of for c in found):
            kind_of = "MRN"     # "aadhaar" system but not a number: still one identifier of the patient
        found = [c for c in found if c.type not in fields.ID_ROLES.values()
                 or c.end <= a or c.start >= b]
        found.append(Cand(a, b, kind_of, digits(text) or re.sub(r"[^A-Z0-9]", "", text.upper()), "patient",
                          prio=PRIORITY[kind_of] + 2))
    found += names.find_path_names(text)
    found += names.find_url_pii(text)
    if kind == "filename":
        b64_cands = _b64_filename_cands(text, dmy)
        found += b64_cands
        if not b64_cands:
            found = [
                c for c in found
                if c.type not in NAME_TYPES or any(
                    not _is_stem_vocab(m.group(0), "deva" if DEVA.match(m.group(0)[0]) else "latin")
                    for m in re.finditer(r"[A-Za-z']+|[\u0900-\u0963\u0971-\u097f]+", text[c.start:c.end])
                )
            ]
            found += _filename_name_cands(text)
    if kind in ("header", "key", "filename"):
        found += _next_to_mrn(text, found)
    if kind == "key":
        # {"by_name": {"<person>": ...}}: the key itself is the person's name
        holder = f["path"][4:].rsplit("/", 1)[0].rsplit("/", 1)[-1]
        if classify(holder.replace("by_", "")) in ("patient_name", "name") and holder.startswith("by_"):
            found += fields.name_value(text, 0, len(text), "name")
        elif (_is_lookup_table(holder) or not holder) and _looks_like_person(text):
            found += fields.name_value(text, 0, len(text), "name")
    elif kind == "value" and role is None and person_label:
        if not any(classify(k) in ("doctor", "keep") for k in (label, *parents)):
            found += gazetteer.find_unlisted_person(text, names.STOP)
    found += _conditions(text, role, label, parents)

    # "Door No. 18-4-22" is a house number, not a date
    houses = [c for c in found if c.type == "HOUSE"]
    found = [c for c in found if not (c.type == "DATE" and any(h.start <= c.start and c.end <= h.end for h in houses))]

    blocked = names.protected_spans(text)
    found = [c for c in found
             if not (c.type in NAME_TYPES and any(c.start < e and s < c.end for s, e in blocked))]
    # an HL7 v2 message: the segment and field position decide (not filtered by word lists)
    if kind in ("text", "value") and hl7.is_message(text):
        structured_found, stamps, coded = hl7.find(text)
        found = [c for c in found if not any(c.start < e and s < c.end for s, e in stamps)
                 and (c.type in hl7.CODED_KEEP or not any(s <= c.start and c.end <= e for s, e in coded))]
        found += structured_found
    return found


# ---------------------------------------------------------------- 3. propagation

def _word_pattern(words: list[str]) -> str:
    body = r"[ _.-]+".join(re.escape(w) for w in words)
    if DEVA.search(body):
        return rf"(?<![ऀ-ॿ]){body}(?![ऀ-ॿ])"
    return rf"(?<![A-Za-z]){body}(?![A-Za-z])"


# Speed: a known value is only searched for in fields that contain its first word.
# Without this index a 2,000-row export takes (rows x names) regex searches.
_TOKEN = re.compile(r"[A-Za-z]+|[ऀ-ॿ]+|\d+")


def _anchor(value: str) -> str:
    m = _TOKEN.search(value)
    return m.group(0).casefold() if m else ""


_RUN_TOGETHER = "run-together"   # marks the template of a full name written without spaces


def _known_values(cands: list[Cand], text: str) -> list[tuple[str, str, Cand, bool]]:
    """(first word, regex, template candidate, file-wide?) for every value worth searching for again."""
    out = []
    for c in cands:
        surface = text[c.start:c.end]
        if c.type in NAME_TYPES:
            words = surface.replace(",", " ").split()
            if "," in surface and len(words) > 1:           # "Surname, Given" is usually written "Given Surname"
                given_first = words[1:] + words[:1]
                out.append((_anchor(given_first[0]), _word_pattern(given_first), c, True))
            useful = [w.strip(".") for w in words if len(w.strip(".")) >= 3
                      and w.strip(".").casefold() not in names.GENERIC | (names.STOP - {"asha"})]
            if len(words) > 1:
                out.append((_anchor(words[0]), _word_pattern(words), c, True))
                joined = "".join(words)
                if len(joined) >= 8 and re.fullmatch(r"[A-Za-z]+", joined):     # "ds-<firstlast>-<number>.txt"
                    out.append((joined.casefold(), _word_pattern([joined]), c._replace(norm=_RUN_TOGETHER), True))
            for w in useful:
                out.append((_anchor(w), _word_pattern([w]), c, False))
        elif c.type == "MRN" and c.norm:
            runs = re.findall(r"\d+", surface)
            cores = [c.norm] + ([runs[-1]] if runs else [])
            for core in dict.fromkeys(cores):
                if len(core) >= 6:
                    out.append((core, rf"(?<!\d){core}(?!\d)", c, True))
        elif c.type == "VILLAGE" and len(surface) >= 4:
            out.append((_anchor(surface), _word_pattern(surface.split()), c, False))
    return out


def _add(index: dict, anchor: str, pattern: str, c: Cand) -> None:
    index.setdefault(anchor, {}).setdefault(pattern, c)


def _propagate(records: list[Record], per_field: dict) -> None:
    single = sum(r["loc"] != "@file" for r in records) <= 1
    wide: dict = {}                    # first word -> {regex: candidate}, usable anywhere in the file
    local: dict[str, dict] = {}        # record_id -> same shape, usable inside that record
    any_record: dict = {}              # every local value, for file names / headers / keys / metadata
    for (rid, path), (text, cands) in per_field.items():
        for anchor, pattern, c, file_wide in _known_values(cands, text):
            if file_wide or single:
                _add(wide, anchor, pattern, c)
            else:
                _add(local.setdefault(rid, {}), anchor, pattern, c)
                _add(any_record, anchor, pattern, c)
    compiled: dict[str, re.Pattern] = {}
    info = {(r["record_id"], f["path"]): (f["kind"], r["loc"]) for r in records for f in r["fields"]}
    for (rid, path), (text, cands) in per_field.items():
        kind, loc = info[(rid, path)]
        # file names, headers, keys and file metadata may mention anyone in the file
        scope = any_record if kind in ("filename", "header", "key") or loc == "@file" else local.get(rid, {})
        wanted: dict[str, Cand] = {}
        for token in dict.fromkeys(t.casefold() for t in _TOKEN.findall(text)):
            for index in (wide, scope):
                for pattern, c in index.get(token, {}).items():
                    wanted.setdefault(pattern, c)
        if not wanted:
            continue
        blocked = names.protected_spans(text)
        for pattern, c in wanted.items():
            rx = compiled.get(pattern) or compiled.setdefault(pattern, re.compile(pattern, re.I))
            for m in rx.finditer(text):
                if c.type in NAME_TYPES:
                    if any(m.start() < e and s < m.end() for s, e in blocked):
                        continue
                    # lowercase is accepted only for a whole name: run together, or in a file name
                    value = m.group(0).casefold()
                    whole = c.norm == _RUN_TOGETHER or kind == "filename"
                    if not (DEVA.search(value) or m.group(0)[0].isupper() or whole):
                        continue
                    norm = None
                else:
                    norm = c.norm
                cands.append(Cand(m.start(), m.end(), c.type, norm, c.role, prio=PROPAGATED, relation=c.relation))


# ---------------------------------------------------------------- 4. results

def _view(value: str) -> tuple[str, list[tuple[int, int]] | None]:
    """The text detect reads: hidden characters removed and URL escapes, "\\uXXXX" sequences and HTML entities
    decoded. For each of its characters, the (start, end) it covers in `value` (None: the text is unchanged)."""
    text, kept = visible(value)
    spans = None if kept is None else [(k, k + 1) for k in kept]
    text, inner = decode_view(text)
    if inner is not None:
        spans = inner if spans is None else [(spans[s][0], spans[e - 1][1]) for s, e in inner]
    return text, spans


def detect_file(records: list[Record]) -> list[RecordResult]:
    """Hidden characters are removed and URL escapes, \\uXXXX sequences and HTML entities decoded before detection;
    findings point back into the original values."""
    originals: dict[tuple[str, str], tuple[str, list[tuple[int, int]]]] = {}
    cleaned = []
    for r in records:
        fields_ = []
        for f in r["fields"]:
            text, spans = _view(f["value"])
            if spans is not None:
                originals[(r["record_id"], f["path"])] = (f["value"], spans)
                f = {**f, "value": text}
            fields_.append(f)
        cleaned.append({**r, "fields": fields_})
    results = _detect(cleaned)
    for result in results:
        for finding in result["findings"]:
            key = (result["record_id"], finding["path"])
            if key in originals:
                value, spans = originals[key]
                start, end = spans[finding["start"]][0], spans[finding["end"] - 1][1]
                finding.update(start=start, end=end, text=value[start:end])
    return results


# a place name as a tehsil / block cell holds it: one to three capitalised or Devanagari words
_PLACE_CELL = re.compile(r"(?:[A-Z][A-Za-z'-]*|[ऀ-ॣॱ-ॿ]+)(?: (?:[A-Z][A-Za-z'-]*|[ऀ-ॣॱ-ॿ]+)){0,2}")
# "block" is also a nerve block, a heart block and a part of a building
_NOT_A_BLOCK = frozenset("nerve heart bundle branch complete partial degree wing building tower ward opd ipd icu ot room "
                         "bed floor office lab main new old".split())


def _group(path: str) -> str:
    """Fields that describe one place: the cells of a row, or the keys of one JSON object."""
    return "col" if path.startswith("col:") else path.rsplit("/", 1)[0]


def _tehsils(records: list[Record], roles: dict) -> dict[tuple[str, str], Cand]:
    """The tehsil / taluk / block cells and keys that name an area. "Block" counts only beside a district or village."""
    placed = {(rid, _group(path)) for (rid, path), role in roles.items() if role in ("district", "village")}
    out = {}
    for r in records:
        for f in r["fields"]:
            key = (r["record_id"], f["path"])
            if f["kind"] != "value" or roles.get(key) != "tehsil":
                continue
            words = set(tokens(f["context"] or "" if f["path"].startswith("col:") else _json_label(f["path"])[0]))
            if not words & {"tehsil", "taluk", "taluka", "tahsil", "तहसील"} and (r["record_id"], _group(f["path"])) not in placed:
                continue
            text = fold(f["value"])
            value = text.strip()
            parts = set(value.casefold().split())
            if (len(value) < 3 or not _PLACE_CELL.fullmatch(value)
                    or parts & (names.MEDICAL | _NOT_A_BLOCK | {"na", "nil", "none", "not", "unknown"})):
                continue
            start = text.index(value)
            out[key] = Cand(start, start + len(value), "TEHSIL", norm_name(value) or None, None)
    return out


def _detect(records: list[Record]) -> list[RecordResult]:
    if not records:
        return []
    roles = field_roles(records)
    texts = [fold(f["value"]) for r in records for f in r["fields"]]
    headers = [f["context"] or f["value"] for r in records for f in r["fields"]
               if f["kind"] == "header" or f["path"].startswith("col:")]
    dmy = dates.day_first(texts, list(dict.fromkeys(headers)))

    people = _person_labels({f["path"]: f["value"] for r in records for f in r["fields"] if f["path"].startswith("/")})
    per_field = {}
    for r in records:
        for f in r["fields"]:
            key = (r["record_id"], f["path"])
            per_field[key] = (fold(f["value"]), candidates(f, roles.get(key), dmy, f["path"] in people))
    _propagate(records, per_field)
    for key, cand in _tehsils(records, roles).items():   # after propagation: a tehsil is never copied elsewhere
        per_field[key][1].append(cand)

    out: list[RecordResult] = []
    whole_text = "\n".join(texts)
    for r in records:
        findings, meta = [], {}
        relation_value = None
        for f in r["fields"]:
            key = (r["record_id"], f["path"])
            role = roles.get(key)
            if role == "relation":
                relation_value = fields.relation_of(f["value"]) or relation_value
            for c in resolve(per_field[key][1]):
                surface = f["value"][c.start:c.end]
                norm = c.norm
                who = c.role
                if c.type in STRONG_ID_TYPES or c.type == "AADHAAR_MASKED":
                    who = who or "patient"
                if c.type in NAME_TYPES:
                    last, comma, given = surface.partition(",")
                    norm = c.full_name or norm_name(f"{given} {last}" if comma else surface) or None
                    who = "relative" if c.type == "RELATIVE_NAME" else "patient"
                    hinglish = c.hinglish or len(_HINGLISH.findall(f["value"])) >= 2
                    script = "deva" if DEVA.search(surface) else ("hinglish" if hinglish else "latin")
                    part = role if role in ("first_name", "last_name") else None
                    meta[(f["path"], c.start)] = (script, c.relation, part)
                findings.append({"path": f["path"], "start": c.start, "end": c.end, "type": c.type,
                                 "text": surface, "norm": norm, "role": who})
        if r["loc"] == "@file":
            ev = empty_evidence(r["record_id"])
        else:
            record_text = "\n".join(fold(f["value"]) for f in r["fields"])
            if r["fmt"] in ("text", "fhir"):
                record_text = whole_text
            ev = evidence.build(r["record_id"], findings, meta, record_text, r["file"])
            for mention in ev["names"]:
                if mention["role"] == "relative" and mention["relation"] is None:
                    mention["relation"] = relation_value
        out.append({"record_id": r["record_id"], "findings": findings, "evidence": ev})
    return out
