"""Self-test for detect on made-up text that does NOT come from the practice data.

    python -m aegis.detect.selftest

The practice score cannot show whether we generalise, because the rules were written while
looking at practice data. Add a case here whenever you find a miss or a false alarm.
All names and numbers are invented. main.py never imports this file.
"""
from __future__ import annotations

import sys

from aegis.detect import detect_file

# (line, strings that MUST be found, strings that MUST survive)
CASES = [
    # medical and staff text that only looks like a name
    ("Paracetamol ko continue karein.", [], ["Paracetamol"]),
    ("Metformin ka dose badha diya.", [], ["Metformin"]),
    ("Insulin ki zarurat hai.", [], ["Insulin"]),
    ("Amlodipine ke saath Telmisartan lena hai.", [], ["Amlodipine", "Telmisartan"]),
    ("Dengue ne bahut kamzor kar diya.", [], ["Dengue"]),
    ("Echo ka report pending hai.", [], ["Echo"]),
    ("City Diagnostics 9876543210", ["9876543210"], ["City Diagnostics"]),
    ("Apollo Pharmacy Counter ph 9876511111", ["9876511111"], ["Apollo Pharmacy Counter"]),
    ("C/O Chest Pain since 2 days", [], ["Chest Pain"]),
    ("K/C/O DM2 x 9 yrs, HTN on treatment.", [], ["DM2", "HTN", "9 yrs"]),
    ("Cushing's syndrome and Graves disease.", [], ["Cushing", "Graves"]),
    ("Dr. Anil Mehta ji ne dekha.", [], ["Anil Mehta"]),
    ("ASHA didi ne visit kiya.", [], ["ASHA"]),
    ("Patient Education given about diet.", [], ["Education"]),
    ("BP 112/78, Tab Meclizine 25 mg 1-0-1 x 5 days", [], ["112/78", "25 mg", "1-0-1", "5 days"]),
    ("Platelet Count 150000-410000 /uL", [], ["150000-410000"]),
    # personal data in wording the practice files do not use
    ("Name of the Patient - Lakshmi Iyer", ["Lakshmi Iyer"], []),
    ("Her husband Venkat informed us.", ["Venkat"], []),
    ("Spoke to Mr Ramakrishnan, reachable on 098450 33221.", ["Ramakrishnan", "098450 33221"], []),
    ("Discussed with daughter Priya on phone.", ["Priya"], []),
    ("Lakshmi ko kal se chakkar aa raha hai.", ["Lakshmi"], ["chakkar"]),
    ("Dinesh ka BP 120/80 hai.", ["Dinesh"], ["120/80"]),
    ("Hosp. No.: KGH/0042917", ["0042917"], []),
    ("रोगी का नाम - लक्ष्मी अय्यर, निवासी ग्राम बेलापुर, मो. ९८४५०११२२३",
     ["लक्ष्मी अय्यर", "बेलापुर", "९८४५०११२२३"], []),
    ("Address: Qtr 17/B, Shastri Colony, beside Water Tank, Belapur",
     ["Qtr 17/B", "Shastri Colony", "beside Water Tank", "Belapur"], []),
    # found by cheap-model stress cases: labels in the middle of a line, unfamiliar ID formats and relative words
    ("Rec# : HOSP/2023/07/00123, Diagnosis: Hypertension.", ["HOSP/2023/07/00123"], ["Hypertension"]),
    ("Seen today; C.R. No. 55/24; BP 118/76 mmHg", ["55/24"], ["118/76"]),
    ("Pt ID: #A1B2C3, Rx: Lisinopril 10mg", ["A1B2C3"], ["Lisinopril 10mg"]),
    ("Aadhaar No: 1111-2222-3333, prescribed Levothyroxine 50 mcg.", ["1111-2222-3333"], ["Levothyroxine"]),
    ("PAN QWXDE7391K on file", ["QWXDE7391K"], []),
    ("Informant (H: 98.50.44.2211); ferritin 9 ng/mL", ["98.50.44.2211"], ["ferritin 9"]),
    ("guardian: maternal uncle Prakash Jha; Azithromycin 250 mg OD", ["Prakash Jha"], ["Azithromycin"]),
    ("attendant - bua (paternal aunt) Kamlesh; bill INR 4200", ["Kamlesh"], ["INR 4200"]),
    ("insured Rahul Deshmukh; fasting glucose 102 mg/dL", ["Rahul Deshmukh"], ["102 mg/dL"]),
    ("c/o- 14, Nehru Marg, Model Town, Karnal; SpO2 98% on room air", ["Nehru Marg", "Model Town"], ["SpO2 98%"]),
    ("Near: Lotus Temple, Diagnosis: Migraine.", ["Lotus Temple"], ["Migraine"]),
    ("श्रीमती अंजलि वर्मा को 10mg दवा दी गई।", ["अंजलि वर्मा"], ["10mg"]),
    ("Village: Rampur, Diagnosis: Malaria, WBC 12,000", ["Rampur"], ["Malaria", "WBC 12,000"]),
    # round 2: names with no label, address chains, more ID shapes (all invented)
    ("Discharged Gurleen Kaur Sandhu in stable condition on Tab. Metformin.", ["Gurleen Kaur Sandhu"], ["Metformin"]),
    ("Handover: bed 4 given to Pallavi Hegde, afebrile overnight.", ["Pallavi Hegde"], ["afebrile"]),
    ("History taken from Tshering Wangdi, 61 yrs, via phone.", ["Tshering Wangdi"], []),
    ("आज सुबह गोविंद नारायण शुक्ला को भर्ती किया गया।", ["गोविंद नारायण शुक्ला"], ["भर्ती"]),
    ("Harbans Lal ki patni Kiran Bala dawa lene aayi.", ["Harbans Lal", "Kiran Bala"], ["dawa"]),
    ("F/o Ishani Ghosh signed the consent form.", ["Ishani Ghosh"], ["consent form"]),
    ("Flat 14, Teynampet, 600018; Tab. Dapsone 100mg", ["Flat 14", "Teynampet", "600018"], ["Dapsone 100mg"]),
    ("Seen at home, Kothapet, 522001. Gopal Naidu was resting.", ["Kothapet", "522001", "Gopal Naidu"], []),
    ("Ref MRN-GWL-55210-C and IPD#25/66120 today", ["MRN-GWL-55210-C", "IPD#25/66120"], []),
    ("MRN IPD-2025-061 reviewed", ["IPD-2025-061"], ["reviewed"]),
    ("Mob 97 31 20 45 88, Door No. 12-3-45, Opp. Water Tanki", ["97 31 20 45 88", "12-3-45", "Opp. Water Tanki"], []),
    ("Claim ref NIVA-POL-7731204 approved", ["NIVA-POL-7731204"], ["approved"]),
    # round 2 traps: places, staff and report text that hold surname-like or capitalised words
    ("Referred to Ram Manohar Lohia Hospital for further care.", [], ["Ram Manohar Lohia"]),
    ("Treated at Sharma Nursing Home, report from Gupta Diagnostics.", [], ["Sharma", "Gupta"]),
    ("Seen by Nurse Mary Thomas and Sister Anita Nair.", [], ["Mary Thomas", "Anita Nair"]),
    ("पाटलिपुत्र केयर अस्पताल में जांच हुई।", [], ["केयर"]),
    ("Platelet Count, 150000, WBC, 11000, normal.", [], ["150000", "11000"]),
    ("Total bill, 148500, paid in cash.", [], ["148500"]),
    ("Review at Village Health Nutrition Day camp.", [], ["Health Nutrition"]),
    ("रात को नींद की दवा दी गई।", [], ["रात"]),
    # round 3: whole stretches of medical text must not disappear with a nearby ID or address label
    ("PAN QWXPE4412L: BP 122/80 mmHg, Amoxyclav 625mg 1-0-1.", ["QWXPE4412L"], ["BP 122/80", "Amoxyclav 625mg", "1-0-1"]),
    ("मरीज (पता: शिवाजी पेठ, 411030) को डॉ. नीलम राव ने एस्प्रिन 75mg 0-1-0 दी, कुल खर्च रु. 6,100 रहा।",
     ["शिवाजी पेठ", "411030"], ["एस्प्रिन 75mg", "0-1-0", "रु. 6,100"]),
    ("आशा दीदी रजनी के साथ आई।", [], ["आशा"]),
    ("Seen at Sardar Patel PHC today.", [], ["Sardar Patel"]),
    ("Platelets, 245100 and WBC, 118200 today.", [], ["245100", "118200"]),
    # round 3: more shapes
    ("Joseph D'Mello D/o Peter D'Mello admitted.", ["Joseph D'Mello", "Peter D'Mello"], []),
    ("Ref IP#NICU-25-771 and NGP/CHW/25/40021", ["NICU-25-771", "NGP/CHW/25/40021"], []),
    ("यूएचआईडी KDR/7714 दर्ज", ["KDR/7714"], []),
    ("Claim TPA-MEDI-771204 under PMJAY-MH-25-884210", ["TPA-MEDI-771204", "PMJAY-MH-25-884210"], []),
    ("Collected from Shastri Ward area, Nehru Nagar, 440012 yesterday.", ["Nehru Nagar", "440012"], []),
    ("सुखदेव उइके को भर्ती किया।", ["सुखदेव उइके"], []),
    # lowercase PAN, more phone layouts, key=value logs, lowercase names
    ("billing: pan mkrpd4821q noted, Tab. Cefixime 200 mg", ["mkrpd4821q"], ["Cefixime 200 mg"]),
    ("Reach on (912) 455-7781 or 934/221/6650; SpO2 97%", ["(912) 455-7781", "934/221/6650"], ["SpO2 97%"]),
    ("Landline 0512-2345678, alt (0581) 456789 and 022 2567 8901.",
     ["0512-2345678", "(0581) 456789", "022 2567 8901"], []),
    ("Ward office 0591-245566 open till 5; lot 0042-118, batch 0007-123456789",
     ["0591-245566"], ["0042-118", "0007-123456789"]),
    ("BP 130/80/72, counts 150/900/1100, ref range 4000-11000, dose 0.5-1.0 mg", [], ["130/80/72", "4000-11000", "0.5-1.0"]),
    ("caller=devika ranganathan dial=912/450/7781", ["devika ranganathan", "912/450/7781"], []),
    ("caller=Barnali Thengal status=resolved", ["Barnali Thengal"], ["resolved"]),
    ("patient=stable name=unknown pt=afebrile", [], ["stable", "unknown", "afebrile"]),
    ("pt devika ranganathan ko do din se bukhar hai", ["devika ranganathan"], ["bukhar"]),
    ("mahesh tripathi s/o ramnaresh tripathi admitted kal raat", ["mahesh tripathi", "ramnaresh tripathi"], ["admitted"]),
    ("pichle das din se pet dard, lal chakte, x ray normal, khan pan theek", [],
     ["das din", "pet dard", "lal chakte", "x ray normal", "khan pan"]),
    ("patient has chest pain and mild fever, advised rest at home", [], ["chest pain", "mild fever", "rest at home"]),
    # lowercase "h.no"; "q4h no 2" is a dose schedule, not a house
    ("Lives at h.no 58/C, since 2019.", ["h.no 58/C"], []),
    ("Old record says hno. 212 only.", ["hno. 212"], []),
    ("Syrup q4h no 2 more doses today.", [], ["q4h no 2"]),
    # "r/o" also means "rule out": a disease after it is not a village
    ("Tremor, r/o Parkinson's disease, advise MRI.", [], ["Parkinson"]),
    ("Fever 3 days, r/o Dengue.", [], ["Dengue"]),
    ("Chest pain, r/o MI.", [], ["MI"]),
    ("Persistent cough, R/O TB.", [], ["TB"]),
    ("Weakness, r/o Guillain Barre syndrome.", [], ["Guillain"]),
    ("RLQ pain, r/o Appendicitis.", [], ["Appendicitis"]),
    ("65 yr male R/o Barhalganj, seen in OPD.", ["Barhalganj"], []),
    ("Pt r/o Sikandarpur fever since 3 days.", ["Sikandarpur"], []),
    # a real village must still go, whatever follows it or however its name ends
    ("R/o Barhalganj Patient stable today.", ["Barhalganj"], []),
    ("Woman r/o Sikandarpur heart disease on treatment.", ["Sikandarpur"], []),
    ("Man r/o Phuluria for ten years.", ["Phuluria"], []),
    # dotted and "+91/" phones, mixed Aadhaar separators
    ("Call 97.31.20.45.88 or +91/8123/004455; Na 138.5", ["97.31.20.45.88", "+91/8123/004455"], ["138.5"]),
    ("ID seen 5821-7734 9012 at desk, HbA1c 7.2", ["5821-7734 9012"], ["HbA1c 7.2"]),
    # zero-width characters, look-alike letters, accents (typed whole or as separate marks)
    ("Patient: Bar\u200bnali Then\u200dgal, mob 97312\u200b04588", ["Bar\u200bnali Then\u200dgal", "97312\u200b04588"], []),
    ("Patient: B\u0430rn\u0430li Thengal (44/F)", ["B\u0430rn\u0430li Thengal"], []),
    ("Patient Name: H\u00e9ctor Pereira", ["H\u00e9ctor Pereira"], []),
    ("Patient Name: He\u0301ctor Pereira", ["He\u0301ctor Pereira"], []),
    ("TSH 2.1 \u03bcIU/mL, dose 50 \u00b5g, TNF-\u03b1 raised", [], ["\u03bcIU/mL", "50 \u00b5g", "TNF-\u03b1"]),
    # years from 1800: the date is found and shifted; a 4-digit time of day is not a year
    ("DOB 14/03/1893, seen 02 Feb 1895", ["14/03/1893", "02 Feb 1895"], []),
    ("Born 1889-07-21; registered 1889/07/22", ["1889-07-21", "1889/07/22"], []),
    ("Admitted 12 Mar 1830 hrs with BP 120/80, Tab Aspirin 75 mg 0-1-0", [], ["1830 hrs", "BP 120/80", "Aspirin 75 mg"]),
    # URL escapes: found where they stand in the original text, and the words between them are not read as a name
    ("Scan: https://his.example/files/Tarun%20Wadhwa%5Creport.pdf?tel=%2B91%2098765%2043210",
     ["Tarun%20Wadhwa", "%2B91%2098765%2043210"], ["report.pdf"]),
    ("file:///D%3A%5CRecords%5CKavya_Chaudhary%5Ccase_notes.pdf", ["Kavya_Chaudhary"], ["case_notes"]),
    ("Open summary_Zubin_Pathak_2026.pdf and Lab_Reports_Singh_Block.csv", ["Zubin_Pathak"], ["Lab_Reports", "Singh_Block"]),
    ("view?patient=Agust%C3%ADn%20Fonseca&visit=3", ["Agust%C3%ADn%20Fonseca"], ["visit=3"]),
    ("log: patient=Zorawar Khetarpal ward=3 status=stable", ["Zorawar Khetarpal"], ["ward=3", "status=stable"]),
    ("SpO2 96%, 5%DEXTROSE drip at 40%20 ml/hr, Tab Paracetamol 650 mg", [], ["96%", "5%DEXTROSE", "Paracetamol 650 mg"]),
    ("Keep 100%25 oxygen; Hb 9.8 g/dL", [], ["Hb 9.8 g/dL"]),
    # given names with no surname: only where the sentence says the person did something ("signed the", "took discharge")
    ("Meenal signed the surgical consent form.", ["Meenal"], ["consent form"]),
    ("Tarun took discharge against medical advice on 14/08/2026.", ["Tarun"], ["medical advice"]),
    ("Consent signed by guardian. Nurse signed the form. Uncle signed the consent. Dr. Rao signed the order.", [],
     ["Consent", "Nurse", "Uncle", "guardian"]),
    ("Wheezing returned after 2 days. Itching signed off by physician. Pharmacy signed the bill.", [],
     ["Wheezing", "Itching", "Pharmacy"]),
    # Scrubadub-inspired improvements + English/Hindi/Hinglish translations
    ("Contact ramesh.verma at gmail dot com or ph 98.45.01.12.23; BP 118/76.",
     ["ramesh.verma at gmail dot com", "98.45.01.12.23"], ["118/76"]),
    ("Patient: Ra\u200bhul\u200d Chatur\u200bvedi, Mob: 73053\u200b31651, Co-admitted: Dеvikа Rаo.",
     ["Ra\u200bhul\u200d Chatur\u200bvedi", "73053\u200b31651", "Dеvikа Rаo"], []),
    ("URL ref: https://portal.example/view?patient=Priyanka%20Sengupta&tel=%2B91%207759130735",
     ["Priyanka%20Sengupta", "%2B91%207759130735"], []),
    ("Satyendra discharged in stable condition on Tab Azithromycin 500 mg.",
     ["Satyendra"], ["Azithromycin 500 mg"]),
    ("Priyanka ne sign kiya aur Rohan ko chhutti mili; BP 120/80.",
     ["Priyanka", "Rohan"], ["120/80"]),
    ("रमेश ने हस्ताक्षर किए और प्रिया को छुट्टी दी गई; पैरासिटामोल 500mg जारी।",
     ["रमेश", "प्रिया"], ["पैरासिटामोल 500mg"]),
    ("Follow up with Pema Choden and Agustín Fonseca; PAN gxlpv2692s.",
     ["Pema Choden", "Agustín Fonseca", "gxlpv2692s"], []),
    # the same new rules must leave report and ward text alone
    ("Culture verified, Repeat CBC signed.", [], ["Culture", "Repeat CBC"]),
    ("Troponin, Negative called to physician.", [], ["Negative"]),
    ("Seen at 10 at AIIMS dot in OPD.", [], ["AIIMS"]),
    ("Lobsang verified the payment receipt at the counter.", ["Lobsang"], []),
    ("Culture verified the organism; Smear signed out by pathologist.", [], ["Culture", "Smear"]),
    ("Janam tithi 14/05/1988, जन्मतिथि 12-08-1992.", ["14/05/1988", "12-08-1992"], []),
    # Kumari and Devi after a first name are part of the name, not a title
    ("Patient: Km. Barsha Kumari came with cough.", ["Barsha Kumari"], ["cough"]),
    # doctor titles in capitals or with a courtesy title in brackets
    ("Chemo plan by DR.(MRS) TARULATA MAHANTA today.", [], ["TARULATA MAHANTA"]),
    # relation words and separators
    ("Consent taken. Son = Nandlal. Will pay tomorrow.", ["Nandlal"], ["Consent"]),
    ("elder bro Ompal waiting outside, will sign.", ["Ompal"], ["waiting"]),
    ("sibling Kiruba also screened, report normal.", ["Kiruba"], ["screened"]),
    ("Call bahu Jasleen if he wanders at night.", ["Jasleen"], ["night"]),
    ("dtr Rituparna will collect the reports.", ["Rituparna"], ["reports"]),
    ("Family history: sibling Diabetes since 2019.", [], ["Diabetes"]),
    # record and insurance numbers announced by a label
    ("UHID-->QRS/OP/0045127 || BP 130/84", ["QRS/OP/0045127"], ["130/84"]),
    ("Old file MR# 31-207-5568 traced.", ["31-207-5568"], ["traced"]),
    ("TPA card no. ZXC7-00518837-04 pending, bill Rs 12,500", ["ZXC7-00518837-04"], ["12,500"]),
    ("आयुष्मान कार्ड संख्या RJ-QX-66120934 दर्ज, खुराक 500mg", ["RJ-QX-66120934"], ["500mg"]),
    ("TPA card not available, HbA1c 8.1% noted.", [], ["HbA1c 8.1%", "not available"]),
    # birth dates written with a Hindi or roman-numeral month
    ("जन्मतिथि ३ फ़रवरी १९७९, वज़न 62 kg", ["३ फ़रवरी १९७९"], ["62 kg"]),
    ("DOB 21/XI/1958, on Telmisartan.", ["21/XI/1958"], ["Telmisartan"]),
    ("Stage II/IV disease, grade III/2020 criteria.", [], ["II/IV", "III/2020"]),
    # "Name- value" with a dash and no space before it
    ("पंजीकरण काउंटर; नाम- सुमित्रा महंत", ["सुमित्रा महंत"], ["काउंटर"]),
    ("Follow- up after two weeks.", [], ["up after two weeks"]),
    # HL7 style names, and HL7 doctors and test names that look similar
    ("PID Mahanta^Tarulata admitted to HDU.", ["Mahanta^Tarulata"], ["HDU"]),
    ("Attending Dr^Rathi^Ompal on call.", [], ["Rathi", "Ompal"]),
    ("OBX Glucose^Fasting 102 mg/dL", [], ["Glucose^Fasting"]),
    # "near old <place>"
    ("Lives near old Hanuman Temple, on Amlodipine.", ["near old Hanuman Temple"], ["Amlodipine"]),

    # a tight dash only introduces a value after a label that says "name"
    ("Patient- stable today, BP 120/80.", [], ["stable"]),
    ("मरीज- को बुखार है, खुराक 500mg", [], ["बुखार"]),
    # doctor protection must never spread over the patient who follows, whatever the capitals
    ("REF DR RATHI PATIENT SUMITRA MAHANTA ADMITTED", ["SUMITRA MAHANTA"], []),
    ("SEEN BY DR RATHI PT NAME NANDLAL HAZARIKA", ["NANDLAL HAZARIKA"], []),
    ("Ref DR RATHI Mrs Barsha Hazarika came", ["Barsha Hazarika"], []),
    ("ref dr Rathi Patient Sumitra Mahanta admitted", ["Sumitra Mahanta"], []),
    ("UNDER DR RATHI MR OMPAL MAHANTA BP 120/80", ["OMPAL MAHANTA"], ["120/80"]),
    ("Ref Dr Rathi Patient Sumitra Mahanta admitted", ["Sumitra Mahanta"], []),
    ("DR.(MRS) MAHANTA PATIENT NANDLAL HAZARIKA", ["NANDLAL HAZARIKA"], []),
    # a dash after a name label never takes over from a later colon
    ("Patient Name- verified: Barsha Hazarika", ["Barsha Hazarika"], []),
    # a leading word that is not a name must not take the name after it down with it
    ("Witness Barsha Hazarika tel 9412730518", ["Barsha Hazarika", "9412730518"], []),
    ("Admitted Ompal (father: Nandlal Mahanta) of H.No. 9, 781014", ["Ompal", "Nandlal Mahanta"], []),
]


def _run_line(line: str) -> list[str]:
    record = {"record_id": "t.txt#doc", "file": "t.txt", "loc": "doc", "fmt": "text",
              "fields": [{"path": "text", "kind": "text", "context": None, "value": line}]}
    return [f["text"] for f in detect_file([record])[0]["findings"]
            if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]


# whole-column cases: (headers, rows, header -> expected finding type for every row, or None = nothing flagged)
TABLES = [
    # recent years under an unreadable header are events, not birth years
    (["Q_YR"], [["2009"], ["2014"], ["2021"], ["2024"]], {"Q_YR": None}),
    # "Surname, Given" in an unreadable column, a birth-year column, Hindi-in-Latin headers
    (["PX_LBL", "X_YOB", "CLIN_TXT"], [["Thengal, Barnali", "1968", "stable"], ["Pereira, Hector", "1981", "afebrile"],
                                       ["Oraon, Suraj", "2003", "review"]],
     {"PX_LBL": "PATIENT_NAME", "X_YOB": "DOB", "CLIN_TXT": None}),
    (["rogee", "pehchaan_sankhya", "postal6", "nidan"], [["Barnali Thengal", "1234 5678 9012", "781001", "Anemia"]],
     {"rogee": "PATIENT_NAME", "pehchaan_sankhya": "AADHAAR", "postal6": "PIN", "nidan": None}),
    (["P_NOM", "K_SUP", "M_RXR", "Q_LOC", "Z_6D", "N_MEMO"],
     [["Anirban Sen", "Mitali Sen", "Farhan Qureshi", "21A Lake Road, Near City Park", "700029", "seen by Dr. Farhan Qureshi"],
      ["Lalita Oraon", "Birsu Oraon", "Neha Kapoor", "H.No. 4, Station Road, Ranchi", "834001", "Dr. Neha Kapoor advised rest"],
      ["Joseph Kurien", "Anna Kurien", "Farhan Qureshi", "Flat 9, Gandhi Nagar, Near Bus Stand", "682020", "stable"]],
     {"P_NOM": "PATIENT_NAME", "K_SUP": "RELATIVE_NAME", "M_RXR": None, "Q_LOC": "HOUSE", "Z_6D": "PIN"}),
    # one patient shares a doctor's name: the column is still the patients
    (["P_NOM", "MEMO"], [["Amit Sharma", "stable"], ["Renu Bhagat", "stable"], ["Suraj Oraon", "stable"],
                         ["Lalita Nair", "seen by Dr. Amit Sharma"]], {"P_NOM": "PATIENT_NAME"}),
    (["fullName", "familyHeadRelation", "orderingClinician", "labRchId", "Village/Mohalla"],
     [["Renu Bhagat", "Father Suraj Bhagat", "Gautam Pillai", "RCH-JH-25-11902", "Rampur Kalan"]],
     {"familyHeadRelation": "RELATIVE_NAME", "orderingClinician": None, "labRchId": "MRN", "Village/Mohalla": "VILLAGE"}),
    (["पता_ग्राम_पिन", "वार्ड"], [["मकान नं. 5/ए, ग्राम रामपुर, 263139", "कस्तूरबा वार्ड"]],
     {"पता_ग्राम_पिन": "HOUSE", "वार्ड": None}),
    # "ref" does not mean doctor; real referrer and reference-range columns are still kept
    (["case_sheet_ref", "patient_ref", "mrn_ref", "ref_by", "ref_doctor", "ref_range", "dak_code", "sample_code"],
     [["31145549", "31147001", "31149002", "Neha Kapoor", "Farhan Qureshi", "4000-11000", "226010", "880123"]],
     {"case_sheet_ref": "MRN", "patient_ref": "MRN", "mrn_ref": "MRN", "ref_by": None, "ref_doctor": None,
      "ref_range": None, "dak_code": "PIN", "sample_code": None}),
    # an unreadable header over phone numbers written with odd spacing; other long numbers are not phones
    (["zz_reach", "zz_bill"], [["9412 7 30518", "4500.00"], ["70112-904-18", "1200.50"], ["8800 41 2276", "980.00"]],
     {"zz_reach": "PHONE", "zz_bill": None}),
]


def _run_tables() -> int:
    failed = 0
    for headers, rows, expected in TABLES:
        records = [{"record_id": f"t.csv#row:{n}", "file": "t.csv", "loc": f"row:{n}", "fmt": "csv",
                    "fields": [{"path": f"col:{i}", "kind": "value", "context": h, "value": v}
                               for i, (h, v) in enumerate(zip(headers, row))]} for n, row in enumerate(rows, 1)]
        for n, result in enumerate(detect_file(records)):
            for header, kind in expected.items():
                found = [f["type"] for f in result["findings"] if f["path"] == f"col:{headers.index(header)}"]
                if (kind is None and found) or (kind is not None and kind not in found):
                    failed += 1
                    print(f"FAIL  column {header} row {n + 1}: expected {kind}, got {found}")
    return failed


# one column: (header, cell, strings that MUST be found, strings that MUST survive). The header is only a hint:
# a "PIN" column may hold the whole address, and "Ward / Patient" holds a bed number and a person
CELLS = [
    ("res_pin", "7/21, Teliarganj, 211004", ["7/21", "Teliarganj", "211004"], []),
    ("Postal Entry", "Flat 6-C, Ulubari, 781007", ["Flat 6-C", "Ulubari", "781007"], []),
    ("Dwelling/PIN", "Kachhi Basti, opp. Water Tank, 302016", ["Kachhi Basti", "opp. Water Tank", "302016"], []),
    ("PIN Code", "211004", ["211004"], []),
    ("pin_code", "PIN 211004", ["211004"], ["PIN"]),
    ("Pincode", "not recorded, ask later", [], ["not recorded", "ask later"]),
    ("Ward / Patient", "Bed 21 - Ishrat Jahan Ansari", ["Ishrat Jahan Ansari"], ["Bed 21"]),
    ("bed_patient", "Cot 3: Thangkhal Haokip", ["Thangkhal Haokip"], ["Cot 3"]),
    ("Patient", "Bed 8 - Devika Ranganathan", ["Devika Ranganathan"], ["Bed 8"]),
    ("Patient", "Ward 3 Bed 8 - Devika Ranganathan", ["Devika Ranganathan"], ["Ward 3", "Bed 8"]),
    ("Ward / Patient", "Female Medical Ward", [], ["Female Medical Ward"]),
    ("Ward / Patient", "Surgical Ward B", [], ["Surgical Ward"]),
    ("bed_patient", "Bed 14", [], ["Bed 14"]),
    ("Ward / Patient", "Ward 4 - Male Surgical", [], ["Male Surgical"]),
    ("Ward / Patient", "Ishrat Jahan Ansari", ["Ishrat Jahan Ansari"], []),
    ("patient_ward", "Maternity", [], ["Maternity"]),
    # dotted short forms in headers
    ("P.I.N.", "781014", ["781014"], []),
    ("U.H.I.D.", "55-204-9911", ["55-204-9911"], []),
    # landmark and neighbourhood headers
    ("Landmark", "next to the old post office", ["old post office"], []),
    ("ptNbhd", "Lalpur Basti", ["Lalpur Basti"], []),
    ("Nearby", "dairy booth", ["dairy booth"], []),
    # a notes column stays a notes column even when a nurse or doctor writes it
    ("wardNurseNote", "son Nandlal informed, BP 120/80", ["Nandlal"], ["BP 120/80"]),
    ("Doctor Remarks", "Continue Metformin 500 mg, wife Jasleen counselled", ["Jasleen"], ["Metformin 500 mg"]),
    ("Doctor", "Tarulata Mahanta", [], ["Tarulata Mahanta"]),
    ("Student", "Barsha Hazarika", ["Barsha Hazarika"], []),
    # relative columns that put the relation first, or in brackets after the name
    ("kin_mentioned", "amma - Kiruba", ["Kiruba"], []),
    ("Relative", "papa Nandlal, didi Barsha", ["Nandlal", "Barsha"], []),
    ("Relative", "devrani Sumitra", ["Sumitra"], []),
    ("Brought By (with relation)", "Jasleen Gill (wife)", ["Jasleen Gill"], []),
    ("Brought By (with relation)", "self (walk in)", [], ["self"]),
    # an insurance number with an Aadhaar-looking tail is removed whole
    ("Policy No", "ACMEGEN-4821-5530-9917", ["ACMEGEN-4821-5530-9917"], []),

    # a name cell that runs into a sentence stops there, but never when another person follows
    ("Patient", "Barsha came with cough", ["Barsha"], ["cough"]),
    ("Patient", "Barsha with Nandlal", ["Barsha", "Nandlal"], []),
    ("Patient", "Barsha came with husband nandlal", ["Barsha", "nandlal"], []),
    # a header that is newly understood must not switch off the search for names
    ("P.I.N.", "wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("PIN", "ask wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("Student", "Ompal Rathi came with wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("Landmark", "Ompal Rathi came with wife Barsha Hazarika", ["Ompal Rathi", "Barsha Hazarika"], []),
    ("Landmark", "Paracetamol given since 2 days", [], ["Paracetamol"]),
    ("fon_no", "9412 7 30518", ["9412 7 30518"], []),
    ("fon_no", "ask wife Barsha Hazarika", ["Barsha Hazarika"], []),
    # only a plain "student" column holds names; a hospital near by is not a landmark of a home
    ("student_vision", "normal both eyes", [], ["normal"]),
    ("Student Remarks", "attends regularly, weight low", [], ["attends"]),
    ("Nearby Hospital", "District Hospital Sehore", [], ["District Hospital"]),
    # "relative contact" columns hold a name, a number or both, even though "contact" reads as a phone label
    ("परिजन_संपर्क", "भाई नंदलाल महंत", ["नंदलाल महंत"], []),
    ("Guardian Contact", "Barsha Hazarika 94127-30518", ["Barsha Hazarika", "94127-30518"], []),
    ("Guardian Contact", "94127 30518", ["94127 30518"], []),
    ("Attendant Mobile", "not available", [], ["not available"]),
]


def _run_mixed_column() -> int:
    """Mostly phone numbers under an unreadable header: the one cell that names a person must still be searched."""
    values = ["9412 7 30518", "70112-904-18", "8800 41 2276", "9435 2 11870", "ask wife Barsha Hazarika"]
    records = [{"record_id": f"t.csv#row:{n}", "file": "t.csv", "loc": f"row:{n}", "fmt": "csv",
                "fields": [{"path": "col:0", "kind": "value", "context": "zz_reach2", "value": v}]}
               for n, v in enumerate(values, 1)]
    found = [f["text"] for f in detect_file(records)[-1]["findings"]]
    if not any("Barsha Hazarika" in f for f in found):
        print(f"FAIL  mixed phone column: found {found}")
        return 1
    return 0


def _run_cells() -> int:
    failed = 0
    for header, value, must_find, must_keep in CELLS:
        record = {"record_id": "t.csv#row:1", "file": "t.csv", "loc": "row:1", "fmt": "csv",
                  "fields": [{"path": "col:0", "kind": "value", "context": header, "value": value}]}
        found = [f["text"] for f in detect_file([record])[0]["findings"]
                 if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {header}: {value}\n      missed={missed} wrongly_removed={eaten}")
    return failed


# JSON cases: (pointer -> value or key, strings that MUST be found, strings that MUST survive)
DOCS = [
    # an unlisted two-word value is a person only when its label says so
    ({"organism": "Escherichia Coli", "sign": "Murphy Positive", "reviewer": "Tshering Wangdi"},
     ["Tshering Wangdi"], ["Escherichia Coli", "Murphy Positive"]),
    # lookup tables keyed by people, whatever the table is called
    ({"on_call_map": {"Barnali Thengal": "bed 3"}}, ["Barnali Thengal"], ["bed 3"]),
    ({"drug_index": {"Amlodipine Besylate": "5 mg"}, "ward_map": {"General Ward": "2"},
      "vital_signs": {"Heart Rate": "88", "Chief Complaint": "cough"}},
     [], ["Amlodipine Besylate", "General Ward", "Heart Rate", "Chief Complaint"]),
    ({"column_map": {"Referral Source": "ref_src"}, "patient_tests": [{"name": "Lipid Profile"}]},
     [], ["Referral Source", "Lipid Profile"]),
    # a table whose name says nothing about people keeps its keys
    ({"billing_map": {"Room Rent": "1200"}, "symptom_index": {"Joint Stiffness": "1"}, "discount_map": {"Senior Citizen": "10"},
      "organization": {"contact": {"name": "Help Desk"}}}, [], ["Room Rent", "Joint Stiffness", "Senior Citizen", "Help Desk"]),
    # the closest parent decides whose name it is
    ({"organization": {"patient": {"name": "Barnali Thengal"}, "contact": {"name": "Devika Ranganathan"}}},
     ["Barnali Thengal", "Devika Ranganathan"], []),
    ({"organization": {"name": "Sunrise Care Centre", "department": {"name": "Cardiology"}},
      "patient": {"insurer": {"name": "Star Health"}}}, [], ["Sunrise Care Centre", "Cardiology", "Star Health"]),
]


def _walk(node, ptr=""):
    items = node.items() if isinstance(node, dict) else enumerate(node)
    for k, v in items:
        child = f"{ptr}/{k}"
        if isinstance(node, dict):
            yield {"path": f"key:{child}", "kind": "key", "context": None, "value": k}
        if isinstance(v, (dict, list)):
            yield from _walk(v, child)
        else:
            yield {"path": child, "kind": "value", "context": str(k), "value": str(v)}


def _run_docs() -> int:
    failed = 0
    for data, must_find, must_keep in DOCS:
        record = {"record_id": "t.json#doc", "file": "t.json", "loc": "doc", "fmt": "json", "fields": list(_walk(data))}
        found = [f["text"] for f in detect_file([record])[0]["findings"]
                 if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]
        missed = [x for x in must_find if x not in found]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {data}\n      missed={missed} wrongly_removed={eaten}")
    return failed


# a name run together or in lowercase inside a file name: (file name, text, expected pieces found in the file name)
FILENAMES = [
    ("बरनाली_शर्मा_पर्चा.txt", "BP 110/70\n", ["बरनाली_शर्मा"]),
    ("ds-barnalithengal-31145549.txt", "Patient Name: Barnali Thengal\n", ["barnalithengal"]),
    ("ds_devika_ranganathan.txt", "Patient Name: Devika Ranganathan\n", ["devika_ranganathan"]),
]


def _run_filenames() -> int:
    failed = 0
    for name, text, expected in FILENAMES:
        records = [{"record_id": f"{name}#@file", "file": name, "loc": "@file", "fmt": "text",
                    "fields": [{"path": "filename", "kind": "filename", "context": None, "value": name}]},
                   {"record_id": f"{name}#doc", "file": name, "loc": "doc", "fmt": "text",
                    "fields": [{"path": "text", "kind": "text", "context": None, "value": text}]}]
        found = [f["text"] for f in detect_file(records)[0]["findings"]]
        if not all(any(x in f for f in found) for x in expected):
            failed += 1
            print(f"FAIL  file name {name}: found {found}")
    return failed


def main() -> int:
    failed = 0
    for line, must_find, must_keep in CASES:
        found = _run_line(line)
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {line}\n      missed={missed} wrongly_removed={eaten}")
    table_failures = _run_tables() + _run_mixed_column()
    print(f"{len(TABLES)} column tables checked, {table_failures} problems")
    cell_failures = _run_cells()
    print(f"{len(CELLS)} single cells checked, {cell_failures} problems")
    table_failures += cell_failures
    doc_failures = _run_docs() + _run_filenames()
    print(f"{len(DOCS)} JSON documents and {len(FILENAMES)} file names checked, {doc_failures} problems")
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")  # keep last: tools read the last line
    return 1 if failed or table_failures or doc_failures else 0


if __name__ == "__main__":
    sys.exit(main())
