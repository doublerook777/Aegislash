"""Person names in free text, found by the words around them (not by a list of names),
plus the "meaning traps" that protect text which only looks like a name."""
from __future__ import annotations

import re

from aegis.detect.normalize import DEVA
from aegis.detect.spans import Cand

# Words that are capitalised but are not part of a person's name.
STOP = frozenset("""
a an and are as at be been by for from in is it of on or the to was were with no not nil none na yes
dr doctor prof sir madam
patient pt attendant relative informant witness guardian family wife husband son daughter father mother brother sister
name age sex gender address mobile mob phone ph contact email dob uhid mrn ipd opd reg id aadhaar aadhar abha pan
hospital clinic centre center lab laboratory pathology diagnostics diagnostic department dept ward bed medicine
surgery neurology nephrology pulmonology cardiology oncology paediatrics pediatrics orthopaedics gynaecology district
multispeciality charitable institute college medical nursing notes note discharge summary report prescription visitor log
date time day week month year next morning evening night today tomorrow yesterday after before
review advice adv follow up visit round admission admitted discharged treated course history complaints complaint
diagnosis procedure medications medication drug dose tab cap inj syp inh drops cream rx
fever cough cold pain body ache vomiting nausea weakness headache breathlessness diarrhoea loose motions giddiness
fatigue swelling bleeding burning rash chest abdomen
disease syndrome palsy disorder type chronic acute primary essential infection
bp pulse temp rbs fbs spo hb hba tsh wbc haemoglobin hemoglobin platelet creatinine sodium sugar blood random fasting
serum total count sample received collected reported remarks forwarded forward attachment message call called
please kindly stable condition hai ka ki ko se ne mein nahi theek ho gaya gayi rahe raha ab aur
asha anm worker staff sister nurse
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday
village vill gram tehsil distt uttar pradesh india road gali mohalla nagar near opp behind house makan flat plot
low salt diabetic diet rest fluids continue stop start same
dawai dawa marij mareez bukhar khana pet sir dard ulti neend raat aaj kal subah shaam doctor test usko uska uski
unko unka inka iska aap hum ghar sab koi kuch abhi phir dobara sugar pressure thyroid saans khoon
export exports data file files patients records visits backup
education counselling counseling instructions information walk haan namaste theek achha accha ok okay hello thank thanks
""".split())
# common drug, disease and test words: never a person (general medical vocabulary, not taken from any file)
MEDICAL = frozenset("""
paracetamol dolo crocin ibuprofen diclofenac aspirin clopidogrel metformin glimepiride gliclazide sitagliptin insulin
amlodipine telmisartan losartan ramipril enalapril atenolol metoprolol furosemide spironolactone atorvastatin
rosuvastatin pantoprazole omeprazole rabeprazole ranitidine ondansetron domperidone azithromycin amoxicillin
ceftriaxone cefixime doxycycline ciprofloxacin levofloxacin metronidazole artesunate artemether primaquine
chloroquine levothyroxine thyroxine salbutamol budesonide montelukast cetirizine prednisolone dexamethasone
levodopa carbidopa phenytoin valproate rifampicin isoniazid ferrous folic calcium vitamin zinc ors saline glucose
oxygen dengue malaria typhoid tuberculosis pneumonia anaemia anemia diabetes hypertension hypothyroidism asthma
covid dialysis haemodialysis echo ecg usg xray mri scan biopsy endoscopy antibiotic antacid vaccine
""".split())
# words that make "<Capitalised words> <phone number>" an organisation, not a person
_ORG = frozenset("""
city helpline emergency service services pharmacy counter care health life ambulance enquiry inquiry reception office
desk toll free centre center support booking appointment control room police station bank number manager billing
insurance company limited ltd pvt chemist store medicals general government govt trust foundation society apollo
""".split())
STOP = STOP | MEDICAL
# "asha" is both a common first name and the community health worker: names rules decide by context.
_ASHA_WORKER = re.compile(r"\bASHA\b(?! +[A-Z]{2,})|\b(?i:asha)\b(?=\s+(?i:worker|volunteer))")

# Name parts that do not identify anyone on their own.
GENERIC = frozenset("devi kumar kumari singh md mohd mohammad mohammed shri smt kaur bai lal ji prasad ram".split())

_TITLE = r"(?:Mr|Mrs|Ms|Smt|Shri|Sri|Km|Kumari|Master|Baby|Late|Mohd|Md|श्री|श्रीमती|कुमारी|स्व)\b\.?"
_CAP = r"(?:[A-Z][a-z]+(?:'[a-z]+)?|[A-Z]{2,}(?![A-Za-z])|[A-Z]\.(?= ?[A-Z]))"
_DEVA_WORD = r"[ऀ-ॣॱ-ॿ]+"
LATIN_NAME = rf"(?:(?:Mohd|Md)\.? )?{_CAP}(?: {_CAP}){{0,3}}"
DEVA_NAME = rf"{_DEVA_WORD}(?: {_DEVA_WORD}){{0,2}}"
NAME = rf"(?:{LATIN_NAME}|{DEVA_NAME})"

_DOCTOR = re.compile(
    rf"(?:\bDr\b\.?|\bDOCTOR\b|\bDoctor\b|\bProf\b\.?|डॉ\.?|डा\.|डॉक्टर)\s*(?:{LATIN_NAME}|{DEVA_NAME})"
    rf"(?:\s*\([^)\n]*\))?")
_EPONYM = re.compile(rf"\b{_CAP}(?:'s)?(?= (?:[Dd]isease|[Ss]yndrome|[Pp]alsy|[Ss]ign|[Pp]rocedure)\b)")


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Parts of the text that must never be treated as a patient or relative name."""
    return [m.span() for p in (_DOCTOR, _EPONYM, _ASHA_WORKER) for m in p.finditer(text)]


def trim_name(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Shrink a captured span to the real name: drop titles and stop words from both ends."""
    words = [(m.start() + start, m.end() + start) for m in re.finditer(r"[^\s]+", text[start:end])]
    def bad(span):
        w = text[span[0]:span[1]].strip(".,'’:;()-")
        return not w or w.casefold() in STOP - {"asha"} or re.fullmatch(_TITLE, text[span[0]:span[1]]) is not None
    while words and bad(words[0]):
        words.pop(0)
    # stop at the first stop word inside ("Fatima Bano Age" -> "Fatima Bano")
    for i in range(1, len(words)):
        if bad(words[i]):
            del words[i:]
            break
    if not words:
        return None
    s, e = words[0][0], words[-1][1]
    while e > s and text[e - 1] in ".,'’:;()- ":
        e -= 1
    if text[s:e].endswith("'s"):
        e -= 2
    piece = text[s:e]
    if len(piece) < 2 or any(c.isdigit() for c in piece):
        return None
    return s, e


_KIN_REL = "bhaiya|chacha|chachu|chachi|mama|mami|papa|tau|tai|mummy|beta|beti"
_KIN_PAT = "ji|jee|sahab|saheb|sahib|bhai|behen|behenji|behanji|didi|amma|babu|bhabhi|uncle|aunty|aunti"
_DEVA_HON = "जी|साहब|साहिब|बहन|बहनजी|भाई|अम्मा|दीदी|बाबू"
_PERSON_WORD = r"(?:attendant|relative|informant|caretaker|care ?giver|son|daughter|wife|husband|brother|father|mother)"

# (regex with group "name", role, relation, hinglish?)
_CUES: list[tuple[re.Pattern, str, str | None, bool]] = []


def _cue(pattern: str, role: str, relation: str | None = None, hinglish: bool = False, flags: int = 0):
    _CUES.append((re.compile(pattern, flags), role, relation, hinglish))


# relatives: S/o, D/o, W/o (never H/O, which means "history of")
for _rel in ("S/o", "D/o", "W/o"):
    _cue(rf"(?<![A-Za-z])(?i:{_rel[0]}/o)\b[.:]? *(?:(?:{_TITLE}) )?(?P<name>{NAME})", "relative", _rel)
    _cue(rf"(?P<name>{NAME}) *,? *\(?(?<![A-Za-z])(?i:{_rel[0]}/o)\b", "patient")
_cue(rf"(?<![A-Za-z/])[Cc]/[Oo]\b *(?:(?:{_TITLE}) )?(?P<name>{NAME})", "relative", "C/O")
_cue(rf"\b(?i:son|daughter|wife|husband|father|mother) (?:of|name:?) (?:(?:{_TITLE}) )?(?P<name>{NAME})", "relative")
_cue(rf"(?:पुत्र|पुत्री|पत्नी|सुपुत्र)[ :]+(?:श्री )?(?P<name>{DEVA_NAME})", "relative")
# "Attendant: X", "called by X", "witnessed by X"
_cue(rf"\b(?i:{_PERSON_WORD}|informed by|called by|witnessed by|accompanied by|brought by|raised by|reported by)"
     rf"(?:\s*[:\-] *| +)(?P<name>{LATIN_NAME})", "relative")
_cue(rf"(?P<name>{LATIN_NAME})'s +(?i:{_PERSON_WORD})", "patient")
_cue(rf"(?P<name>{LATIN_NAME}) *\( *(?i:{_PERSON_WORD})", "relative")
# Hinglish honorifics: "Shahid sahab", "Anita behenji", "Kamal Bhaiya"
_cue(rf"(?P<name>{LATIN_NAME}) +(?i:{_KIN_REL})\b", "relative", None, True)
_cue(rf"(?P<name>{LATIN_NAME}) +(?i:{_KIN_PAT})\b", "patient", None, True)
_cue(rf"(?P<name>{DEVA_NAME}) +(?:{_DEVA_HON})(?![ऀ-ॿ])", "patient")
# a sentence that starts with a bare name: "Dinesh ka BP ...", "Sunita ko 3 din se ...". The words after it must be
# about a person's state, otherwise "Metformin ka dose" would count as a name.
_ABOUT_PATIENT = (r"(?:(?:ka|ki|ke|ko) +(?i:bp|blood pressure|pulse|temp|temperature|bukhar|condition|tabiyat|haalat|haal|"
                  r"wazan|weight|saans|operation|discharge|ilaj|dard|sugar|pet|sir)\b"
                  r"|ko +(?:[a-z0-9]+ +){0,4}(?:bukhar|chakkar|khansi|dard|ulti|kamzori|dast|sujan|takleef|saans)\b"
                  r"|ko +\d+ +(?:din|hafte|mahine|saal)\b)")
_cue(rf"(?:^|\n|[.!?] |- )(?P<name>{_CAP}(?: {_CAP}){{0,2}}) +(?={_ABOUT_PATIENT})", "patient", None, True)
# titles and report headings
_cue(rf"\b(?:Mr|Mrs|Ms|Smt|Shri|Km|Master)\b\.? +(?P<name>{LATIN_NAME})", "patient")
_cue(rf"(?P<name>(?:Mohd|Md)\.? {LATIN_NAME})", "patient")
_cue(rf"\b(?i:report of|note for|summary of|results? for|record of|patient) *:? +(?P<name>{LATIN_NAME})", "patient")
# "14:00 - Brajesh Yadav - K/C/O typhoid"
_cue(rf"(?P<name>{LATIN_NAME}) +- +(?:K/C/O|H/O|C/O)\b", "patient")
# a Hindi sentence "<name> को 9 दिन से बुखार है"
_cue(rf"(?:^|\n)(?P<name>{DEVA_NAME}) को ", "patient")
# a full name right before a phone number: "... called by <Name> 94054-71434"
_cue(rf"(?P<name>{_CAP}(?: {_CAP}){{1,2}})[ ,:(-]*(?:(?i:mob|mobile|ph|phone|contact|tel)\b\.?[ :]*)?(?=\+?\d[\d -]{{8,}}\d)",
     "relative")
_PHONE_ADJACENT_FROM = len(_CUES) - 1
_cue(rf"(?P<name>{_CAP}(?: {_CAP}){{1,2}}) *, *(?i:mob|mobile|ph|phone|contact|tel)\b", "relative")


# export paths and file names: "...\\Sunita_Patel_084999\\...", "Summary_Sunita_Patel_ABC-12345"
_PATH_NAME = re.compile(
    r"(?<![A-Za-z])(?P<name>[A-Z][a-z]+(?:_[A-Z][a-z]+){0,3})(?:_(?:NA|na))?_(?=(?:[A-Z]{2,5}[-_]?)?(?:\d{2}[-_]\d{2}|\d{5,}))")


def find_path_names(text: str) -> list[Cand]:
    out = []
    for m in _PATH_NAME.finditer(text):
        words = [(w.start() + m.start("name"), w.end() + m.start("name"))
                 for w in re.finditer(r"[^_]+", m.group("name"))]
        while words and text[words[0][0]:words[0][1]].casefold() in STOP - {"asha"}:
            words.pop(0)
        if words and text[words[-1][0]:words[-1][1]].casefold() not in STOP - {"asha"}:
            out.append(Cand(words[0][0], words[-1][1], "PATIENT_NAME", None, "patient"))
    return out


def find_names(text: str) -> list[Cand]:
    out = []
    for index, (pattern, role, relation, hinglish) in enumerate(_CUES):
        for m in pattern.finditer(text):
            s, e = m.span("name")
            if index >= _PHONE_ADJACENT_FROM and set(text[s:e].casefold().split()) & (_ORG | MEDICAL):
                continue
            if relation == "C/O" and not text[s].isupper() and not DEVA.match(text[s]):
                continue
            # a title or stop word right after C/O means a complaint or a doctor, not a relative
            if relation == "C/O" and text[s:e].split()[0].strip(".").casefold() in STOP:
                continue
            span = trim_name(text, s, e)
            if not span:
                continue
            s, e = span
            kind = "RELATIVE_NAME" if role == "relative" else "PATIENT_NAME"
            out.append(Cand(s, e, kind, None, role, relation=relation, hinglish=hinglish))
    return out
