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

from aegis.detect import address, dates, evidence, fields, gazetteer, ids, names
from aegis.detect.labels import classify, tokens
from aegis.detect.normalize import DEVA, fold, norm_name, unquote_view, visible
from aegis.detect.spans import PRIORITY, PROPAGATED, Cand, resolve
from aegis.types import DIRECT_TYPES, QUASI_TYPES, STRONG_ID_TYPES, Record, RecordResult, empty_evidence

NAME_TYPES = ("PATIENT_NAME", "RELATIVE_NAME")
# two or more of these words mean the sentence is Hinglish (Hindi written in Latin letters)
_HINGLISH = re.compile(r"\b(?:ka|ki|ke|ko|ne|hai|hain|nahi|raha|rahe|rahi|gaya|gayi|diya|liya|se|mein|aur|ji|sahab|behenji|bhai)\b")
_CONDITION_KEYS = ("diagnosis", "diagnoses", "condition", "dx", "icd", "निदान")
_LABEL_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<label>[^:=\n]{1,40}?)\s*(?::(?!\d|//)|=| - | – )[ \t]*(?P<value>.*)$")


# ---------------------------------------------------------------- 1. roles

def _segments(path: str) -> list[str]:
    return [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]


def _json_label(path: str) -> tuple[str, tuple[str, ...]]:
    keys = [p for p in _segments(path) if not p.isdigit()]
    if not keys:
        return "", ()
    return keys[-1], tuple(keys[:-1])


def _fhir_types(records: list[Record]) -> dict[str, str]:
    """pointer of an object -> its FHIR resourceType."""
    return {f["path"].rsplit("/", 1)[0]: f["value"] for r in records for f in r["fields"]
            if f["path"].startswith("/") and f["path"].endswith("/resourceType")}


def _fhir_role(path: str, role: str | None, types: dict[str, str]) -> str | None:
    parts = path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        kind = types.get("/".join(parts[:i]))
        if kind:
            below = [p for p in parts[i:] if not p.isdigit()]
            break
    else:
        return role
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
    for r in records:
        for f in r["fields"]:
            key = (r["record_id"], f["path"])
            if f["kind"] != "value":
                continue
            if f["path"].startswith("col:"):
                role = classify(f["context"] or "")
                columns.setdefault(f["path"], []).append(key)
            else:
                label, parents = _json_label(f["path"])
                role = classify(label, parents)
                if types:
                    role = _fhir_role(f["path"], role, types)
                role = _pair_role(f["path"], by_path) or role
                columns.setdefault(re.sub(r"/\d+(?=/|$)", "/*", f["path"]), []).append(key)
            roles[key] = role
    # unknown column: decide from its values (hidden data renames headers)
    values = {(r["record_id"], f["path"]): f["value"] for r in records for f in r["fields"]}
    # a doctor column without "Dr." in it: the same people are written "Dr. X" somewhere else in the file
    doctors = {" ".join(names.doctor_name(m)) for text in values.values() for m in names.doctor_mentions(text)}
    has_name = any(role in ("patient_name", "name", "first_name") for role in roles.values())
    for keys in columns.values():
        if roles[keys[0]] is None:
            guess = _guess_role([values[k] for k in keys if values[k].strip()])
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
    return roles


def _guess_role(vals: list[str]) -> str | None:
    if len(vals) < 3:
        return None
    if all(re.fullmatch(r"[1-9]\d{2}(?!000)\d{3}", v.strip()) for v in vals):
        return "pin"
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
    return None


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
                continue
            label = lab.group("label")
            if re.search(r"\d{4}", label):
                continue  # "PAN ABCDE1234F: BP 118/76": the "label" holds the number itself
            dashed = not re.match(r"\s*[:=]", m.group(0)[lab.end("label"):])
            # a dash is a weak separator ("Ward 4 - ..."): require the label to be short and digit-free
            if dashed and (len(label.split()) > 5 or any(ch.isdigit() for ch in label)):
                continue
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

    # a record number always has a digit: "patient_ref" holding words is read like any unknown value
    if role == "mrn" and kind == "value" and not re.search(r"\d", text):
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

    if role in (None, "free", "date"):
        found += dates.find_ages(text)
        found += address.find_places(text)
        found += names.find_names(text)
        # in file names, headers and keys "_" separates words
        scan_text = text.replace("_", " ") if kind in ("filename", "header", "key") else text
        found += gazetteer.find_listed_names(scan_text, names.STOP)
        if kind not in ("filename", "header", "key"):
            found += gazetteer.find_joined_names(text, names.STOP)
        found += _labelled(text, dmy)
    found += names.find_path_names(text)
    found += names.find_url_pii(text)
    if kind == "filename":
        found += _b64_filename_cands(text, dmy)
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
    return [c for c in found
            if not (c.type in NAME_TYPES and any(c.start < e and s < c.end for s, e in blocked))]


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
    """The text detect reads: hidden characters removed and URL escapes decoded. For each of its characters, the
    (start, end) it covers in `value` (None: the text is unchanged)."""
    text, kept = visible(value)
    spans = None if kept is None else [(k, k + 1) for k in kept]
    text, inner = unquote_view(text)
    if inner is not None:
        spans = inner if spans is None else [(spans[s][0], spans[e - 1][1]) for s, e in inner]
    return text, spans


def detect_file(records: list[Record]) -> list[RecordResult]:
    """Hidden characters are removed and URL escapes decoded before detection; findings point back into the
    original values."""
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
                    norm = norm_name(f"{given} {last}" if comma else surface) or None
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
