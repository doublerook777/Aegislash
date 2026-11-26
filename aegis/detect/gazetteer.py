"""Names with no cue next to them, found by a list of common Indian surnames.

"Discharged Harpreet Singh Gill in stable condition" has no label or honorific. We accept a run of
capitalised (or Devanagari) words as a person when it holds a given name followed by a known surname,
and is not a hospital, ward, road or staff member. The list is general public knowledge from many
regions and communities; none of it was copied from the practice data's records.
"""
from __future__ import annotations

import re

from aegis.detect.spans import PRIORITY, Cand

SURNAMES = frozenset("""
acharya adhikari agarwal aggarwal agrawal ahluwalia ahmad ahmed ahuja aiyar akhtar alam ali amin anand ansari antony
apte arora arya asthana awasthi azad aziz babu bagchi baghel bagri bahl bais bajaj bajpai bakshi bal balakrishnan
balan balasubramanian bandyopadhyay banerjee bano bansal barik barman barua baruah basak basu baskar bedi begum behera
bhagat bhandari bharadwaj bhardwaj bhargava bhaskar bhat bhatia bhatnagar bhatt bhattacharjee bhattacharya bhosale
bhuiyan bhutia biswal biswas bisht bora borah bordoloi borkar bose brahma chacko chadha chakrabarti chakraborty
chanda chandra chandran chatterjee chaturvedi chaudhari chaudhary chaudhuri chauhan chawla chelliah cherian chettiar
chhetri chopra choubey choudhary choudhury chowdhury correia coutinho dabral dalvi damor dang dangi das dasgupta dash
datta dave dayal deb debbarma dehury deka deol deori desai deshmukh deshpande devar dewan dey dhaliwal dhar dhawan
dhillon dhingra dhruv dikshit dixit dkhar dogra doshi dsouza dubey dutta dwivedi engineer fakir farooqui faruqi
fernandes fernando francis gaikwad gandhi ganesan ganguly garg gautam gawde gehlot george ghosh ghoshal gill goel
gogoi goswami gounder gowda goyal grewal grover guha gujral gulati gupta gurjar gurung hajong haldar handique hansda
hasan hashmi hazarika hegde hembram hooda hussain idrisi iqbal irani iyengar iyer jadeja jadhav jaffer jagtap jain
jaiswal jamatia jana jaiswar jaitley james jangid jaswal jatav jena jha jindal john johri joseph joshi kachhap kakkar
kakoti kale kalita kamat kamble kannan kapadia kapoor karmakar karnik kashyap katiyar kaul kaur kaushik kazi kerketta
khalkho khan khandelwal khandekar khanna khare khatoon khatri khetan khongwir khurana kidwai kindo kisku kispotta
kochar kohli koli konwar koshy kotian kothari krishna krishnamurthy krishnan kujur kulkarni kumari kumawat kundu
kurian kurien kushwah kushwaha kutty lahiri lakra lal lalwani lama laskar lepcha limbu lobo lodhi lohar lyngdoh
madan mahajan mahanta mahapatra mahato mahto maity majhi majumdar malhotra malik mallick mandal mane mani manjhi
marak marandi mascarenhas mathew mathur maurya mazumdar meena meghwal mehra mehrotra mehta meitei menezes menon minj
mirza mishra misra mistry mitra mittal modi mohammed mohanty momin mondal more mukherjee mukhopadhyay mullick munda
murmu murthy muthu muthuswamy nadar nagar naidu naik nair nambiar nambissan nanda nandi nandy naqvi narang
narayan narayanan naskar nath nautiyal nayak nayar negi nigam ninan nishad nongrum ojha oraon padhi padmanabhan pahan
pai pal palekar pande pandey pandian pandit panicker panigrahi pant paramasivam parekh parihar parikh paswan patel
pathak pathan patil patnaik patra paul pereira perumal philip pillai pinto poddar pradhan prajapati prakash prasad
purkayastha purohit quadri qureshi rabha raghavan raghunathan rahman rai raina raizada raj raja rajan rajagopal
rajendran rajput raju ramachandran ramakrishnan raman ramaswamy ramesh rana rangan rangarajan ranganathan rao rastogi
rathi rathod rathore raut rautela ravindran rawal rawat ray razvi reang reddy rego rizvi rodrigues rongmei roy sabharwal
sachdeva sah sahani sahay sahni sahoo sahu saikia saini saiyed saksena saxena sebastian sehgal sen sengupta sequeira
seth sethi shah shaikh shaik sharma shastri shekhawat shenoy sheikh sherpa shetty shinde shrivastava shukla siddiqi
siddiqui sidhu singh singha sinha sisodia sodhi solanki soni soren sridhar srinivasan srivastava subba subramaniam
subramanian sundaram sundaresan suri swain swami swamy syed tagore talukdar tamang tandon tanwar tekam teron thakkar
thakur thapa thatte thomas tiga tigga tirkey tiwari toppo trehan tripathi trivedi tudu tyagi upadhyay uikey usmani
vaidya vajpayee vasudevan varghese varma varshney venkataraman venkatesan verma vishwakarma vyas wadhwa wagh wahlang
walia wani warsi yadav zaidi zaman
amma appa bai devi kumar gowda sahib begam khatun bibi bee murmu kisan mahali baraik purty bodra
bhagwat dhoble gaonkar kelkar phadke ranade sathe sawant tambe thorat zende nimbalkar mohite pawar salunkhe
mukkavilli vemula bandaru gudivada yerramilli kolli nandamuri chintala
ao dar chudasama panda hooda debbarma oswal rabha parmar patidar naz parveen suleman d'souza d'costa d'cruz d'silva
contractor lone bhatkal irulappan velayudhan chettri
sandhu brar randhawa chahal bains sekhon virk mann dhindsa grewal johal atwal bajwa cheema sohal
""".split()) - {"contractor", "engineer", "more"}   # also everyday English words

# often a middle name: "Jaswinder Kaur <surname>", "Ashok Kumar <surname>"
_MIDDLE = frozenset("kaur singh kumar kumari devi prasad chandra lal ram bai begum bano".split())

_DEVA_SURNAMES = frozenset("""
अंसारी अग्रवाल अवस्थी अय्यर अली अहमद आजमी आर्य उपाध्याय ओझा कटियार कपूर कश्यप कुमार कुमारी कुलकर्णी कुशवाहा कौर
कौशिक खन्ना खातून खान गर्ग गांधी गायकवाड़ गिल गुप्ता गुर्जर गोयल गोस्वामी गौड़ा गौतम घोष चक्रवर्ती चटर्जी चतुर्वेदी
चौधरी चौबे चौहान जयसवाल जायसवाल जाटव जैन जोशी झा टंडन टेकाम ठाकुर डिसूज़ा ढिल्लों तिर्की तिवारी त्यागी त्रिपाठी
त्रिवेदी दत्त दत्ता दयाल दास दासगुप्ता दीक्षित दुबे देव देवी देशपांडे देशमुख द्विवेदी नकवी नक़वी नायक नायडू नायर निगम
निषाद नेगी पटनायक पटेल पांडे पांडेय पाटिल पाठक पाल पासवान पिल्लई पुरोहित प्रजापति प्रसाद फातिमा फ़ातिमा बघेल बंसल
बनर्जी बर्मन बसु बाई बाजपेयी बानो बिष्ट बीबी बेग बेगम बोस भट्ट भट्टाचार्य भदौरिया भाटिया भारती भारद्वाज भार्गव भोंसले
मंडल मलिक मल्होत्रा महतो मांझी माझी मिश्र मिश्रा मित्तल मीणा मीना मुखर्जी मुंडा मुर्मू मेनन मेहता मोदी मौर्य यादव
रस्तोगी राजपूत राठौड़ राठौर राणा रानी राम राय राव रावत रिज़वी रेड्डी लाल लोधी वर्मा वाजपेयी विश्वकर्मा व्यास शर्मा
शाक्य शाह शुक्ल शुक्ला शेख शेख़ शेट्टी श्रीवास्तव सक्सेना सरकार सहनी सागर साहू सिंह सिद्दीकी सिद्दीक़ी सिन्हा सेन सैनी
सोनकर सोलंकी सोरेन सोनी हसन हांसदा हुसैन अम्मा गोप निराला वाल्मीकि कनौजिया पासी सैयद ज़ैदी जैदी उस्मानी उइके पाटीदार देसाई परवीन रहीम आलम इब्राहिम पांडा बोरकर मरावी धुर्वे नेताम डिसूजा
""".split())

# a run that holds (or is followed by) one of these is a place or an organisation, not a person
_PLACE_OR_ORG = frozenset("""
hospital hospitals phc chc aiims clinic memorial nursing home institute college university trust foundation society centre center
care sadan seva sewa kendra ward wing block unit icu nicu opd diagnostics diagnostic pathology laboratory lab labs
pharmacy medical medicals stores store agency school mandir temple masjid church gurudwara chowk crossing road marg
lane street nagar colony vihar puram enclave park market bazar bazaar station chauraha gate tower bhawan bhavan complex
scheme yojana bank office district tehsil village gram path sarani circle layout extension sector maternity charitable
multispeciality superspeciality disease syndrome palsy sign test score scale method procedure
""".split())
NOT_A_PERSON_WORDS = _PLACE_OR_ORG
_DEVA_PLACE_OR_ORG = frozenset("""
अस्पताल हॉस्पिटल चिकित्सालय क्लिनिक नर्सिंग होम स्मारक मेमोरियल संस्थान कॉलेज विद्यालय ट्रस्ट केंद्र केन्द्र सेंटर केयर
सदन सेवा वार्ड विभाग लैब पैथोलॉजी मेडिकल स्टोर मंदिर मस्जिद चौक चौराहा रोड मार्ग गली नगर कॉलोनी विहार पार्क बाजार बाज़ार
स्टेशन भवन जिला तहसील योजना बैंक मेटरनिटी रोग सिंड्रोम
""".split())
# words that may sit next to a name but are never part of it
_NOT_NAME = frozenset("""
admitted discharged brought referred spoke consent letter handover transferred shifted seen saw examined reviewed
informed inform called met visit followup follow case subject subj pt patient patients attendant attender relative
guardian insured claimant beneficiary donor child baby boy girl male female ward bed room opd icu er
nurse sister asha anm staff doctor dr prof surgeon consultant pharmacist technician counsellor driver
mr mrs ms smt shri sri km kumari-ji late master
for of the by from with and or but to in on at as is was has had who whose her his their our this that these
chacha chachu chachi mama mami tau tai bua mausi nana nani dada dadi bhai behen bahen bete beta beti pita maa mata
patni pati dharmapatni putr putra putri suputra wife husband spouse son daughter father mother brother
aur ki ke ka ko ne se mein hai hain tha thi aaj kal subah shaam raat phir bhi wale wali wala
mareez marij rogi naam nam gaon gram vill village tehsil jila zila district near opp behind
insurance policy card claim bill amount mail email phone mobile contact aadhaar abha pan uhid mrn ipd id no
""".split())
# a capitalised word right before the run that shows it is staff, not the patient
_STAFF_BEFORE = re.compile(r"(?:\b(?i:dr|doctor|prof|nurse|sister|asha|anm|pharmacist|technician|surgeon|consultant|"
                           r"physician|resident|counsellor)\b\.?|डॉ\.?|डा\.|डॉक्टर|नर्स|आशा|सिस्टर)(?:[ ](?i:worker|didi|sahiya)|[ ]कार्यकर्ता)?[ :\-]*$")
_RELATIVE_BEFORE = re.compile(
    r"(?:\b(?i:attendant|attender|relative|informant|guardian|wife|husband|spouse|son|daughter|father|mother|brother|"
    r"sister|neighbou?r|patni|pati|dharmapatni|beta|bete|beti|maa|mata|pita|chacha|mama|bhai|bua|mausi|putr|putra|"
    r"putri|suputra)\b|[SDWCFM]/[Oo]\b|पत्नी|पति|पुत्र|पुत्री|सुपुत्र|बेटे|बेटा|बेटी|पिता|माता|माँ|मां|चाचा|मामा|भाई|बहन|"
    r"अभिभावक|परिचर)[ :.\-)(]*(?:(?:श्री|श्रीमती|स्व\.?|Shri|Smt|Late) )?$")

_WORD = r"(?:(?:Md|Mohd)\.(?= [A-Z])|[A-Z]'[A-Z][a-z]+|[A-Z][a-z]+(?:'[A-Z]?[a-z]+)?|[A-Z]{2,}(?![A-Za-z])|[A-Z]\.(?= ?[A-Z]))"
_RUN = re.compile(rf"(?<![A-Za-z0-9]){_WORD}(?:(?: |(?<=\.)|-(?=[A-Z])){_WORD})*(?![a-z0-9])")
_PART = re.compile(r"(?:Md|Mohd)\.|[A-Z]'[A-Z][a-z]+|[A-Z][a-z]+(?:'[A-Z]?[a-z]+)?|[A-Z]{2,}|[A-Z]\.")

# Chat messages and machine logs are often all lowercase. There capital letters cannot help, so only surnames of four
# or more letters that are not also everyday English or Hindi words count.
_LOWER_AMBIGUOUS = frozenset("""
amma anand bora dang dash dave deka dubey engineer gandhi gill hand kale kali kamat khan krishna lama lone mali
mane mani master mistry modi more nagar nanda nath nayak naik panda pandit pant patra prakash raja rajan rana
raman roth sagar sahib saha soni suri swami tiga wagh wani bibi begam sahib kumari bhat kutty
""".split())
_LOWER_SURNAMES = frozenset(w for w in SURNAMES if len(w) >= 4) - _LOWER_AMBIGUOUS
# words that can stand before a surname in a sentence but are not a first name
_LOWER_NOT_GIVEN = frozenset("""
ask asked tell told give gave sent send took take lene liye diya diye liya aaya aaye aayi gaya gaye gayi mila mile
wala unke uske unka uska mera meri apne naya purana saath lekin toh tak par bhi phir called calls meet met say says said
""".split())
_LOWER_RUN = re.compile(r"(?<![A-Za-z0-9_@.])[a-z]{3,}(?: [a-z]{3,})*(?![A-Za-z0-9_@])")

_DEVA_TOKEN = re.compile(r"[ऀ-ॣॱ-ॿ]+")
_DEVA_NOT_NAME = frozenset("""
को का की के ने से में पर है हैं था थी थे और या एवं तथा व भी ही जी तो कि जो वह यह उन उस इस उनके उनकी उनका उसके उसकी उसका
रोगी रोगिणी मरीज मरीज़ मरीज़ों पेशेंट नाम श्री श्रीमती कुमारी-जी सुश्री स्व स्वर्गीय डॉ डा डॉक्टर नर्स आशा सिस्टर
पत्नी पति पुत्र पुत्री सुपुत्र सुपुत्री बेटा बेटे बेटी पिता माता माँ मां भाई बहन चाचा मामा दादा दादी नाना नानी धर्मपत्नी
अभिभावक परिचर रिश्तेदार संबंधी कार्यकर्ता कार्यकर्त्री आज कल सुबह शाम रात दोपहर दिन बाद पहले साथ आई आए आया आये गई गए गया
भर्ती वाले वाली वाला हेतु लिए लिये द्वारा निवासी ग्राम गाँव गांव मोहल्ला पता फोन फ़ोन मोबाइल नोट लेबल बिना टिप्पणी विवरण
जांच जाँच रिपोर्ट दवा टैबलेट इंजेक्शन बुखार दर्ज बताया कहा दिया दी गई
""".split())


def _clean(word: str) -> str:
    return word.casefold().strip(".")


def _kind(text: str, start: int) -> tuple[str, str]:
    if _RELATIVE_BEFORE.search(text[max(0, start - 28):start]):
        return "RELATIVE_NAME", "relative"
    return "PATIENT_NAME", "patient"


def _cand(text: str, start: int, end: int) -> Cand:
    kind, role = _kind(text, start)
    return Cand(start, end, kind, None, role, prio=PRIORITY["PATIENT_NAME"] - 1)


def _segments(words: list[tuple[int, int, str]], stop: frozenset[str]):
    """Split a run of words at words that cannot be part of a name."""
    segment: list[tuple[int, int, str]] = []
    for word in words:
        if _clean(word[2]) in stop:
            if segment:
                yield segment, word
            segment = []
        else:
            segment.append(word)
    if segment:
        yield segment, None


def _latin(text: str, stop: frozenset[str]) -> list[Cand]:
    out = []
    for run in _RUN.finditer(text):
        words = [(m.start() + run.start(), m.end() + run.start(), m.group(0)) for m in _PART.finditer(run.group(0))]
        if len(words) < 2:
            continue
        # a place or organisation word anywhere after the name ("Ram Manohar Lohia Hospital") rejects the run
        tail = re.match(r"(?:[ ,'’]{1,2}(?:s )?[A-Za-z]+){0,1}", text[run.end():]).group(0)
        if {_clean(w[2]) for w in words} & _PLACE_OR_ORG or set(re.findall(r"[a-z]+", tail.casefold())) & _PLACE_OR_ORG:
            continue
        for segment, _ in _segments(words, stop | _NOT_NAME):
            hits = [i for i, w in enumerate(segment) if i and _clean(w[2]) in SURNAMES]
            if not hits or len(segment) > 5:
                continue
            last = hits[-1]
            if _clean(segment[last][2]) in _MIDDLE and last + 1 < len(segment):
                last += 1
            start, end = segment[0][0], segment[last][1]
            if _STAFF_BEFORE.search(text[max(0, start - 20):start]):
                continue
            out.append(_cand(text, start, end))
    return out


def _lower(text: str, stop: frozenset[str]) -> list[Cand]:
    """"pt <first name> <surname> ko bukhar hai": only on lines that have no capital letter at all."""
    out = []
    never = stop | _NOT_NAME | _PLACE_OR_ORG | _LOWER_NOT_GIVEN
    for line in re.finditer(r"[^\n]+", text):
        if re.search(r"[A-Z]", line.group(0)):
            continue
        for run in _LOWER_RUN.finditer(line.group(0)):
            offset = line.start() + run.start()
            words = [(m.start() + offset, m.end() + offset, m.group(0)) for m in re.finditer(r"[a-z]+", run.group(0))]
            i = 1
            while i < len(words):
                if words[i][2] not in _LOWER_SURNAMES or words[i - 1][2] in never:
                    i += 1
                    continue
                first, last = i - 1, i
                if first and words[first][2] in _MIDDLE and words[first - 1][2] not in never:
                    first -= 1
                while last + 1 < len(words) and words[last + 1][2] in _LOWER_SURNAMES:
                    last += 1
                start, end = words[first][0], words[last][1]
                following = {w[2] for w in words[last + 1:last + 2]}
                if not following & _PLACE_OR_ORG and not _STAFF_BEFORE.search(text[max(0, start - 20):start]):
                    out.append(_cand(text, start, end))
                i = last + 1
    return out


def _deva(text: str) -> list[Cand]:
    out = []
    # words separated by single spaces form a run; punctuation breaks it
    for run in re.finditer(r"[ऀ-ॣॱ-ॿ]+(?: [ऀ-ॣॱ-ॿ]+)*", text):
        words = [(m.start() + run.start(), m.end() + run.start(), m.group(0)) for m in _DEVA_TOKEN.finditer(run.group(0))]
        i = 0
        while i < len(words):
            if words[i][2] not in _DEVA_SURNAMES:
                i += 1
                continue
            last = i
            while last + 1 < len(words) and words[last + 1][2] in _DEVA_SURNAMES:
                last += 1
            first = i
            while first > 0 and i - first < 2 and words[first - 1][2] not in _DEVA_NOT_NAME | _DEVA_PLACE_OR_ORG:
                first -= 1
            following = {w[2] for w in words[last + 1:last + 3]}
            if last > first and not following & _DEVA_PLACE_OR_ORG:
                start, end = words[first][0], words[last][1]
                if not _STAFF_BEFORE.search(text[max(0, start - 20):start]):
                    out.append(_cand(text, start, end))
            i = last + 1
    return out


# "Rukhsana_Bhattacharya" in an export path or a URL: capitalised words joined by "_"; more "_word" parts may follow
_JOINED = re.compile(r"(?<![A-Za-z0-9])[A-Z][a-z]+(?:_[A-Z][a-z]+)+(?![A-Za-z])")


def find_joined_names(text: str, stop: frozenset[str]) -> list[Cand]:
    """A given name and a listed surname written with "_" between them. "_" becomes a space (same length), then the
    usual rules decide; only candidates that cover an "_" are kept, the rest are found elsewhere."""
    if "_" not in text:
        return []
    out = []
    for m in _JOINED.finditer(text):
        piece = m.group(0).replace("_", " ")
        for c in find_listed_names(piece, stop):
            if "_" in m.group(0)[c.start:c.end]:
                out.append(c._replace(start=c.start + m.start(), end=c.end + m.start()))
    return out


def find_listed_names(text: str, stop: frozenset[str]) -> list[Cand]:
    """`stop` is the caller's list of words that are never names (medicines, report words)."""
    never = stop - SURNAMES - {"asha"}
    return _latin(text, never) + _lower(text, never) + _deva(text)


_PERSON_KEY_RUN = re.compile(r"^(?:[A-Z][a-z]{1,20}(?: [A-Z][a-z]{1,20}){1,2}|[ऀ-ॣॱ-ॿ]{2,20}(?: [ऀ-ॣॱ-ॿ]{2,20}){1,2})$")


def find_unlisted_person(text: str, stop: frozenset[str]) -> list[Cand]:
    """Detect 2-3 word TitleCase or Devanagari person names without requiring a surname hit.

    Intended for structured person-like slots (JSON keys, unknown non-clinical JSON fields)
    guarded by the disallow-list (`stop | _PLACE_OR_ORG | _NOT_NAME`), inspired by Scrubadub's
    disallowed-noun proper-noun filter.
    """
    s = text.strip()
    if not _PERSON_KEY_RUN.fullmatch(s):
        return []
    words = [w.casefold() for w in s.split()]
    disallow = (stop - {"asha"}) | _PLACE_OR_ORG | _DEVA_PLACE_OR_ORG | _NOT_NAME | _DEVA_NOT_NAME
    if any(w in disallow for w in words):
        return []
    start = text.index(s)
    return [Cand(start, start + len(s), "PATIENT_NAME", None, "patient", prio=PRIORITY["PATIENT_NAME"] - 2)]
