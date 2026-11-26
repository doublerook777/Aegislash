"""One label classifier for CSV headers, JSON keys and "Label: value" lines.

Hidden data renames columns, so we match on the *words* inside a label, not on exact strings.
`classify("pt_mob_no")` and `classify("Mobile No")` both give "phone".
"""
from __future__ import annotations

import re

_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_SPLIT = re.compile(r"[^a-z0-9ऀ-ॿ]+")


def tokens(label: str) -> list[str]:
    return [t for t in _SPLIT.split(_CAMEL.sub(" ", label or "").casefold()) if t]


def _words(s: str) -> frozenset[str]:
    return frozenset(s.split())


_DOCTOR = _words("doctor dr consultant physician surgeon nurse referred ref author practitioner डॉक्टर चिकित्सक")
_RELATIVE = _words("guardian relative relatives kin nok father fathers husband husbands mother mothers spouse attendant informant careof pita "
                   "pati parent caregiver witness nominee पिता पति अभिभावक माता")
_PHONE = _words("phone ph mobile mob tel telephone whatsapp cell callback contactno msisdn फ़ोन फोन मोबाइल दूरभाष")
_MRN = _words("uhid mrn umr crno uid_h भर्ती_संख्या पंजीकरण आईपीडी")
_ID_WORDS = _words("id no num number ref code सं संख्या")
_DOB = _words("dob birth birthdate janm जन्म")
_AGE = _words("age umar umr aayu yrs आयु उम्र")
_GENDER = _words("gender sex ling लिंग")
_PIN = _words("pin pincode zip zipcode postal postalcode पिन")
_DISTRICT = _words("district distt dist jila zila zilla जिला ज़िला")
_TEHSIL = _words("tehsil taluk taluka tahsil block तहसील")
_VILLAGE = _words("village vill gaon gaanv gaav gav gram city town गांव गाँव ग्राम")
_ADDRESS = _words("address addr street pata residence mohalla locality area house पता निवास")
_NAME = _words("name nm naam fname lname fullname नाम")
_SUBJECT = _words("patient pt beneficiary member subject client person insured मरीज़ मरीज रोगी")
# labels whose values are medical / administrative: never look for names in them
_KEEP = _words("diagnosis dx drug drugs medicine medication test tests result results unit range loinc procedure "
               "department dept ward bed hospital facility lab package status category code display strength "
               "frequency duration vitals amount form schedule system type title state country specimen panel panels "
               "coding schema profile निदान विभाग दवा")
_NOT_PERSON = _words("hospital facility lab test tests drug medicine panel panels coding file organization org "
                     "department ward package scheme insurer company payer_org user username device software")
_NOT_MRN = _words("visit bill invoice sample claim policy ticket trip report order txn receipt encounter")
_FREE = _words("notes note remarks remark comment comments complaints complaint history narrative advice summary")
_DATE = _words("date dated datetime tarikh तारीख दिनांक collected reported registered admitted discharged at on")


def classify(label: str, parents: tuple[str, ...] = ()) -> str | None:
    """Role of a value, from its label and (for JSON) the keys above it.

    Returns one of: doctor, relation, relative_name, email, abha_address, abha, aadhaar, pan,
    insurance, phone, mrn, dob, age_sex, age, gender, pin, district, tehsil, village, address,
    first_name, last_name, patient_name, name, free, date, keep, or None (unknown).
    """
    t = tokens(label)
    if not t:
        return None
    s = set(t)
    joined = "".join(t)
    up = {w for p in parents for w in tokens(p)}

    if s & _DOCTOR and not s & _PHONE:
        return "doctor"
    if s & _FREE and not s & _ADDRESS:
        return "free"
    if s & {"email", "mail", "ईमेल"} or joined.endswith("email"):
        return "email"
    if "abha" in joined or "healthid" in joined or "आभा" in s:
        return "abha_address" if s & {"address", "addr"} else "abha"
    if s & {"aadhaar", "aadhar", "adhaar", "adhar", "uidai", "आधार", "uid"} or "aadha" in joined:
        return "aadhaar"
    if "pan" in s or joined.endswith("panno"):
        return "pan"
    if s & {"policy", "pmjay", "insurance", "ayushman", "tpa", "abpmjay"}:
        return "insurance"
    if s & _PHONE or re.search(r"(mobile|phone|contact(no|number|num))", joined):
        return "phone"
    if s & _DOB or "dateofbirth" in joined:
        return "dob"
    if s & {"relation", "relationship", "संबंध"}:
        return "relation"
    if s & _RELATIVE and (not s & _ADDRESS or s & _NAME):
        return "relative_name"
    if not s & _NOT_MRN and not s & _NAME:
        if s & _MRN or "uhid" in joined or "पंजीकरण" in label or "आईपीडी" in label:
            return "mrn"
        if s & {"reg", "regn", "registration", "ipd", "ip", "admission", "adm", "cr", "mr", "hospital"} and s & _ID_WORDS:
            return "mrn"
        if s & _SUBJECT and s & _ID_WORDS:
            return "mrn"
    if s & _AGE and s & _GENDER:
        return "age_sex"
    if s & _AGE:
        return "age"
    if s & _GENDER:
        return "gender"
    if s & _PIN:
        return "pin"
    if s & _DISTRICT:
        return "district"
    if s & _TEHSIL:
        return "tehsil"
    if s & _VILLAGE:
        return "village"
    if s & _ADDRESS or (s & {"line"} and up & _ADDRESS):
        return "address"
    if s & _DATE and not s & _NAME:
        return "date"

    is_name_label = bool(s & _NAME) or joined.endswith("name") or joined in ("ptnm", "fname", "lname")
    # {"name": {"first": ..., "last": ..., "local": ..., "text": ...}} and FHIR given/family
    under_name = bool(up & {"name"})
    if s & {"first", "given", "fname", "firstname"} and (is_name_label or under_name) or joined in ("firstname", "given"):
        return "first_name"
    if s & {"last", "surname", "family", "lname", "lastname"} and (is_name_label or under_name) or joined in (
            "lastname", "surname", "family"):
        return "last_name"
    if under_name and s & {"local", "text", "full", "display", "value"}:
        is_name_label = True
    if is_name_label:
        if (s | up) & _NOT_PERSON:
            return "keep"
        if up & _RELATIVE:
            return "relative_name"
        if (s | up) & _SUBJECT:
            return "patient_name"
        if up & _DOCTOR:
            return "doctor"
        return "name"
    if s & _SUBJECT and not s & _ID_WORDS and not s & _KEEP:
        return "patient_name"
    if s & _KEEP:
        return "keep"
    return None
