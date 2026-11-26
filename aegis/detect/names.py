"""Person names in free text, found by the words around them (not by a list of names),
plus the "meaning traps" that protect text which only looks like a name."""
from __future__ import annotations

import re
import urllib.parse

from aegis.detect.labels import classify
from aegis.detect.normalize import DEVA, digits, norm_name
from aegis.detect.spans import PRIORITY, Cand

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
low salt diabetic diet care rest fluids continue stop start same
dawai dawa marij mareez bukhar khana pet sir dard ulti neend raat aaj kal subah shaam doctor test usko uska uski
unko unka inka iska aap hum ghar sab koi kuch abhi phir dobara sugar pressure thyroid saans khoon
export exports data file files patients records visits backup
रात सुबह शाम दोपहर आज कल बच्चे बच्चा माँ दवा मरीज मरीज़ रोगी
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
ORG = frozenset("""
city help helpline emergency service services pharmacy counter care health life ambulance enquiry inquiry reception office
desk toll free centre center support booking appointment control room police station bank number manager billing
insurance company limited ltd pvt chemist store medicals general government govt trust foundation society apollo
""".split())
STOP = STOP | MEDICAL
# "asha" is both a common first name and the community health worker: names rules decide by context.
_ASHA_WORKER = re.compile(r"\bASHA\b(?! +[A-Z]{2,})|\b(?i:asha)\b(?=\s+(?i:worker|volunteer|didi))"
                          r"|(?<![ऀ-ॿ])आशा(?= (?:दीदी|कार्यकर्ता|कार्यकर्त्री|वर्कर|बहू|सहयोगिनी))")

# Name parts that do not identify anyone on their own.
GENERIC = frozenset("devi kumar kumari singh md mohd mohammad mohammed shri smt kaur bai lal ji prasad ram".split())

_TITLE = r"(?:Mr|Mrs|Ms|Smt|Shri|Sri|Km|Kumari|Master|Baby|Late|Mohd|Md|श्री|श्रीमती|कुमारी|स्व)\b\.?"
_CAP = r"(?:[A-Z]'[A-Z][a-z]+|[A-Z][a-z]+(?:'[a-z]+)?|[A-Z]{2,}(?![A-Za-z])|[A-Z]\.(?= ?[A-Z]))"
_DEVA_WORD = r"[ऀ-ॣॱ-ॿ]+"
LATIN_NAME = rf"(?:(?:Mohd|Md)\.? )?{_CAP}(?: {_CAP}){{0,3}}"
DEVA_NAME = rf"{_DEVA_WORD}(?: {_DEVA_WORD}){{0,2}}"
NAME = rf"(?:{LATIN_NAME}|{DEVA_NAME})"

_DOCTOR = re.compile(
    # "Dr. X", "DR X", "DR.(MRS) X"
    rf"(?:\b(?i:dr)\b\.?|\bDOCTOR\b|\bDoctor\b|\bProf\b\.?|डॉ\.?|डा\.|डॉक्टर)"
    rf"(?:\s*\((?i:mrs?|ms|miss|prof|capt|col|maj|major)\.?\))?\s*(?:{LATIN_NAME}|{DEVA_NAME})"
    rf"(?:\s*\([^)\n]*\))?")
_EPONYM = re.compile(rf"\b{_CAP}(?:'s)?(?= (?:[Dd]isease|[Ss]yndrome|[Pp]alsy|[Ss]ign|[Pp]rocedure)\b)")


def name_words(value: str) -> list[str]:
    return [w for w in re.split(r"[ .]+", value.casefold()) if w]


def doctor_mentions(text: str) -> list[str]:
    return [m.group(0) for m in _DOCTOR.finditer(text)]


def doctor_name(mention: str) -> list[str]:
    """The words after the title: "Dr. R. Mehta (MD)" -> ["r", "mehta"]."""
    title = (r"^(?:(?i:dr)\b\.?|DOCTOR|Doctor|Prof\b\.?|डॉ\.?|डा\.|डॉक्टर)"
             r"(?:\s*\((?i:mrs?|ms|miss|prof|capt|col|maj|major)\.?\))?")
    return name_words(re.sub(r"\(.*$", "", re.sub(title, "", mention)))


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Parts of the text that must never be treated as a patient or relative name."""
    return [m.span() for p in (_DOCTOR, _EPONYM, _ASHA_WORKER) for m in p.finditer(text)]


def trim_name(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Shrink a captured span to the real name: drop titles and stop words from both ends."""
    words = [(m.start() + start, m.end() + start) for m in re.finditer(r"[^\s]+", text[start:end])]
    first_word = words[0] if words else None
    def bad(span):
        w = text[span[0]:span[1]].strip(".,'’:;()-")
        # "Md", "Mohd" are part of a name; so is "Kumari" after a first name ("<name> Kumari")
        part_of_name = w in ("Md", "Mohd") or (w == "Kumari" and span != first_word)
        title = re.fullmatch(_TITLE, text[span[0]:span[1]]) is not None and not part_of_name
        return not w or w.casefold() in STOP - {"asha"} or title
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
# "sister" is left out on purpose: "Sister Mary" is usually a nurse
_PERSON_WORD = (r"(?:attendant|attender|relative|informant|caretaker|care ?giver|guardian|neighbou?r|son-in-law|"
                r"daughter-in-law|grand(?:son|daughter|father|mother)|nephew|niece|uncle|aunt|bua|mausi|chacha|"
                r"(?:brother|sister|father|mother)-in-law|cousin|spouse|sasur|"
                r"bro|dtr|sibling|bhabhi|devrani|jethani|bahu|nanad|dadaji|nanaji|"
                r"son|daughter|wife|husband|brother|father|mother)")

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
_cue(rf"(?<![ऀ-ॿ])(?:पुत्र|पुत्री|पत्नी|सुपुत्र)[ :]+(?:श्री )?(?P<name>{DEVA_NAME})", "relative")
_cue(rf"(?<![A-Za-z/])(?i:[fmg]/o)\b[.:]? *(?:(?:{_TITLE}|Baby) )?(?P<name>{LATIN_NAME})", "patient")
# "Attendant: X", "called by X", "witnessed by X"
_cue(rf"\b(?i:{_PERSON_WORD}|informed by|called by|witnessed by|accompanied by|brought by|raised by|reported by)"
     rf"(?: *\([^)\n]{{0,30}}\))?(?:\s*[:\-=] *| +)(?P<name>{LATIN_NAME})", "relative")
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
# family and helper words that may stand where a name does ("Uncle signed the consent"); not in STOP because other cues use them
_NOT_THE_PATIENT = frozenset("uncle aunt aunty cousin neighbour neighbor grandfather grandmother grandson granddaughter "
                             "nephew niece bua mausi chacha mama dada dadi nana nani counsellor counselor technician "
                             "pharmacist dietician dietitian physiotherapist receptionist cashier driver".split())

# Hindi titles: "श्रीमती <name>". A following particle (को, का, ने ...) is not part of the name.
_HINDI_PARTICLE = r"(?:को|का|की|के|ने|से|है|में|पर|जी)(?![ऀ-ॿ])"
_cue(rf"(?<![ऀ-ॿ])(?:श्रीमती|श्री|कुमारी|सुश्री) +(?P<name>{_DEVA_WORD}(?: (?!{_HINDI_PARTICLE}){_DEVA_WORD}){{0,2}})",
     "patient")
# titles and report headings
_cue(rf"\b(?:Mr|Mrs|Ms|Smt|Shri|Km|Master)\b\.? +(?P<name>{LATIN_NAME})", "patient")
_cue(rf"(?P<name>(?:Mohd|Md)\.? {LATIN_NAME})", "patient")
_cue(rf"\b(?i:report of|note for|summary of|results? for|record of|patient|insured|claimant|policy ?holder)(?: *:? +| *= *)(?P<name>{LATIN_NAME})", "patient")
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
    r"(?<![A-Za-z])(?P<name>[A-Z][a-z]+(?:_[A-Z][a-z]+){0,3})(?:_(?:NA|na))?_(?P<mrn>(?:[A-Z]{2,5}[-_]?)?(?:\d{2}[-_]\d{2}|\d{5,}))(?=$|[\\/_.-])"
)


def find_path_names(text: str) -> list[Cand]:
    out = []
    for m in _PATH_NAME.finditer(text):
        words = [(w.start() + m.start("name"), w.end() + m.start("name"))
                 for w in re.finditer(r"[^_]+", m.group("name"))]
        while words and text[words[0][0]:words[0][1]].casefold() in STOP - {"asha"}:
            words.pop(0)
        if words and text[words[-1][0]:words[-1][1]].casefold() not in STOP - {"asha"}:
            out.append(Cand(words[0][0], words[-1][1], "PATIENT_NAME", None, "patient"))
        mrn_raw = m.group("mrn")
        mrn_dig = digits(mrn_raw)
        # 5-8 digit suffix (not a 10-digit phone or 12-digit Aadhaar) in an export path
        if 5 <= len(mrn_dig) <= 8:
            out.append(Cand(m.start("mrn"), m.end("mrn"), "MRN", mrn_dig, "patient"))
    return out


_URL_HINT = re.compile(r"://|\bwww\.|%[0-9A-Fa-f]{2}")
_URL_PARAM = re.compile(r"(?<=[?&])(?P<k>[A-Za-z0-9_ऀ-ॿ]{2,24})=(?P<v>[^&\s\n#\"']{2,120})")
_URL_ENC_PATH = re.compile(r"[A-Za-z]%3A(?:%5[Cc]|%2[Ff])[^\s\n\"'<>]{6,120}")


def find_url_pii(text: str) -> list[Cand]:
    """Detect PII inside URL query parameters and percent-encoded file paths."""
    if not _URL_HINT.search(text):
        return []
    out: list[Cand] = []
    for m in _URL_PARAM.finditer(text):
        role = classify(m.group("k"))
        if not role:
            continue
        raw_v = m.group("v")
        dec = urllib.parse.unquote_plus(raw_v).strip()
        if not dec:
            continue
        if role in ("patient_name", "relative_name", "name"):
            kind = "RELATIVE_NAME" if role == "relative_name" else "PATIENT_NAME"
            who = "relative" if role == "relative_name" else "patient"
            end = m.end("v")
            # in decoded text "Priyanka%20Sengupta" reads "Priyanka Sengupta": take the following name words too
            more = re.compile(rf"(?: {_CAP}){{1,3}}").match(text, end) if raw_v[:1].isupper() else None
            if more:
                span = trim_name(text, m.start("v"), more.end())
                if span and span[0] == m.start("v"):
                    end, dec = span[1], text[m.start("v"):span[1]]
            out.append(Cand(m.start("v"), end, kind, norm_name(dec) or None, who, prio=PRIORITY[kind] + 3))
        elif role == "phone":
            d = digits(dec)
            if len(d) >= 7:
                out.append(Cand(m.start("v"), m.end("v"), "PHONE", d[-10:] if len(d) > 10 else d, "patient", prio=PRIORITY["PHONE"] + 3))
        elif role in ("aadhaar", "email", "mrn", "dob", "pin", "pan", "insurance"):
            tmap = {"aadhaar": "AADHAAR", "email": "EMAIL", "mrn": "MRN", "dob": "DOB",
                    "pin": "PIN", "pan": "PAN", "insurance": "INSURANCE_ID"}
            kind = tmap[role]
            norm_v = dec.casefold() if role == "email" else (dec.upper() if role == "pan" else digits(dec) or dec)
            out.append(Cand(m.start("v"), m.end("v"), kind, norm_v, "patient", prio=PRIORITY[kind] + 3))
    for m in _URL_ENC_PATH.finditer(text):
        dec = urllib.parse.unquote(m.group(0))
        if "_" in dec:
            for pm in _PATH_NAME.finditer(dec):
                # Find the raw name segment inside the original text
                raw_name = pm.group("name")
                enc_name = urllib.parse.quote(raw_name)
                for needle in (raw_name, enc_name):
                    idx = text.find(needle, m.start(), m.end())
                    if idx != -1:
                        out.append(Cand(idx, idx + len(needle), "PATIENT_NAME", norm_name(raw_name) or None, "patient", prio=PRIORITY["PATIENT_NAME"] + 2))
                        break
    return out


# Cues that are weaker than a label, so every word of the name must look like a name (two words or more).
_FULL = rf"{_CAP}(?: {_CAP}){{1,3}}"
_ONE_OR_MORE = rf"{_CAP}(?: {_CAP}){{0,3}}"
_DEVA_ONE_OR_MORE = rf"{_DEVA_WORD}(?: {_DEVA_WORD}){{0,2}}"
_KIN_HINDI = r"(?:bete|beta|beti|patni|pati|dharmapatni|maa|mata|pita|bhai|behen|chacha|mama|mausi|bua)"
_STRICT_CUES: list[tuple[re.Pattern, str]] = [(re.compile(p), role) for p, role in (
    # "Tenzing Lepcha, 54 yrs", "Harpreet Gill (46 yrs)"
    (rf"(?P<name>{_FULL}) *[,(] *\d{{1,3}} *(?i:yrs?|years?|y/o|saal)\b", "patient"),
    (rf"\b(?i:admitted|discharged|belongs to|signed by|allocated to|history (?:was )?taken from|workup for|"
     rf"follow[- ]?up (?:visit )?of|consent (?:signed |given )?by|referral letter *:) +(?P<name>{_FULL})", "patient"),
    # "<name> ki patni <name>"
    (rf"(?P<name>{_FULL}) +(?:ke|ki) +{_KIN_HINDI}\b", "patient"),
    (rf"\b(?:ke|ki|unke|unki|uske|uski) +{_KIN_HINDI} +(?P<name>{_FULL})", "relative"),
)]
_STRICT_CUES.append((re.compile(rf"(?<![A-Za-z])(?i:ptn|pt|patient|subj(?:ect)?|nok)[ ]?(?:->|[~#|])+ *(?P<name>{_FULL})"), "patient"))
# call logs: "caller=<name>"
_STRICT_CUES.append((re.compile(rf"(?<![A-Za-z])(?i:caller|callee) *[:=] *(?P<name>{_FULL})"), "relative"))
# Action-cue person patterns across English, Hinglish, and Devanagari Hindi (handles 1-word & unlisted names)
_CLAUSE_START = r"(?:^|\n|[।.!?]\s+|:\s+|,\s+|\b(?:and|aur)\s+|(?:और|तथा)\s+)"
# A verb alone is not enough: reports are also "verified" and "signed", and insurance "expired". The words after
# the verb must be something that only happens to, or is done by, a person.
_PERSON_DOES = (
    r"discharged +(?:home|on request|against|from (?:the )?(?:hospital|ward)|in +(?:a +)?(?:[a-z]+ +)?condition)"
    r"|took discharge|absconded"
    r"|(?:signed|verified) +(?:(?:the|a|his|her) +)?(?:[a-z]+ +){0,2}(?:consent|form|bond|undertaking|declaration|identity|signature|address"
    r"|bills?|slip|receipt|voucher|register|documents?|paperwork|papers)"
    r"|called +(?:up|back|to +(?:ask|enquire|inquire|inform|confirm|request))"
    r"|expired +(?:despite|during +(?:treatment|admission))"
)
_ACTION_CUES: list[tuple[re.Pattern, str]] = [(re.compile(p), role) for p, role in (
    # English clinical subject-verb: "Satyendra discharged in stable condition", "Priyanka signed the surgical consent form"
    (rf"{_CLAUSE_START}(?P<name>{_ONE_OR_MORE}) +(?:was )?(?:{_PERSON_DOES})\b", "patient"),
    # English person-object cues: "given to Devika", "Follow up with Pema Choden", "Co-admitted: Devika Rao"
    (rf"(?:\b(?i:given to|handed over to|handover to|follow[- ]?up with|spoke (?:to|with)|discussed with|verified by|co-admitted)\s*[:\-]?\s*)(?P<name>{_ONE_OR_MORE})", "patient"),
    # Hinglish action cues: "Satyendra ko chhutti mili", "Priyanka ne sign kiya"
    (rf"{_CLAUSE_START}(?P<name>{_ONE_OR_MORE}) +(?:ko +(?:chhutti|discharge|admit|ward|bed|ilaj)|ne +(?:sign|hastakshar|call|phone|verify|bulaya|bulaaya))\b", "patient"),
    # Devanagari Hindi action cues: "रमेश को छुट्टी दी गई", "प्रिया ने हस्ताक्षर किए"
    (rf"{_CLAUSE_START}(?P<name>{_DEVA_ONE_OR_MORE}) +(?:को +(?:छुट्टी|भर्ती|दवा|बेड|वार्ड|इलाज)|ने +(?:हस्ताक्षर|साइन|फ़ोन|फोन|कॉल|सत्यापित|बताया))(?![ऀ-ॿ])", "patient"),
)]
_FOLLOWUP_AND = re.compile(rf" +(?:and|aur) +(?P<name>{_ONE_OR_MORE})| +(?:और|तथा) +(?P<name_hi>{_DEVA_ONE_OR_MORE})")
_NEVER_IN_NAME = frozenset("under to into via through with without after before general emergency".split())
_PRONOUNS = frozenset("""
he she they we i you it who this that these those someone anyone everyone nobody somebody anybody everybody
both all none each other another there here
child baby infant neonate boy girl male female man woman lady gentleman
woh wo yeh ye unhone inhone maine humne koi sabhi वह यह उन्होंने इन्होंने मैंने हमने कोई सभी
""".split())


def _valid_action_name(raw: str) -> bool:
    words = [w.strip(".,").casefold() for w in raw.split()]
    if not words or any(w in (STOP - {"asha"}) | ORG | _NEVER_IN_NAME | _PRONOUNS | _NOT_THE_PATIENT for w in words):
        return False
    # "Repeat CBC": a lab or test short form next to ordinary words is not a name
    shouted = [w.isascii() and len(w.strip(".")) > 1 and w.strip(".").isupper() for w in raw.split()]
    return not any(shouted) or all(shouted)


def _strict_names(text: str) -> list[Cand]:
    out = []
    for pattern, role in _STRICT_CUES:
        for m in pattern.finditer(text):
            words = [w.strip(".").casefold() for w in m.group("name").split()]
            if any(w in (STOP - {"asha"}) | ORG | _NEVER_IN_NAME for w in words):
                continue
            kind = "RELATIVE_NAME" if role == "relative" else "PATIENT_NAME"
            out.append(Cand(*m.span("name"), kind, None, role))
    for pattern, role in _ACTION_CUES:
        for m in pattern.finditer(text):
            s, e = m.span("name")
            if _STAFF_BEFORE_SIMPLE.search(text[max(0, s - 20):s]):
                continue
            if not _valid_action_name(m.group("name")):
                continue
            kind = "RELATIVE_NAME" if role == "relative" else "PATIENT_NAME"
            out.append(Cand(s, e, kind, None, role))
            # Handle "Follow up with Pema Choden and Agustín Fonseca" (or Hinglish/Hindi "aur"/"और")
            m2 = _FOLLOWUP_AND.match(text, e)
            if m2:
                grp = "name" if m2.group("name") else "name_hi"
                if _valid_action_name(m2.group(grp)):
                    out.append(Cand(m2.start(grp), m2.end(grp), kind, None, role))
    return out


_STAFF_BEFORE_SIMPLE = re.compile(
    r"(?:\b(?i:dr|doctor|prof|nurse|sister|asha|anm|pharmacist|technician|surgeon|consultant|"
    r"physician|resident|counsellor)\b\.?|डॉ\.?|डा\.|डॉक्टर|नर्स|आशा|सिस्टर)[ :\-]*$"
)


def find_names(text: str) -> list[Cand]:
    out = []
    for index, (pattern, role, relation, hinglish) in enumerate(_CUES):
        for m in pattern.finditer(text):
            s, e = m.span("name")
            if index >= _PHONE_ADJACENT_FROM and set(text[s:e].casefold().split()) & (ORG | MEDICAL):
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
    return out + _strict_names(text)
