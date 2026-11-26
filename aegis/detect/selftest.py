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
    ("Janam tithi 14/05/1988, जन्मतिथि 12-08-1992.", ["14/05/1988", "12-08-1992"], []),
]


def _run_line(line: str) -> list[str]:
    record = {"record_id": "t.txt#doc", "file": "t.txt", "loc": "doc", "fmt": "text",
              "fields": [{"path": "text", "kind": "text", "context": None, "value": line}]}
    return [f["text"] for f in detect_file([record])[0]["findings"]
            if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]


# whole-column cases: (headers, rows, header -> expected finding type for every row, or None = nothing flagged)
TABLES = [
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


# JSON cases: (pointer -> value or key, strings that MUST be found, strings that MUST survive)
DOCS = [
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
    table_failures = _run_tables()
    print(f"{len(TABLES)} column tables checked, {table_failures} problems")
    doc_failures = _run_docs() + _run_filenames()
    print(f"{len(DOCS)} JSON documents and {len(FILENAMES)} file names checked, {doc_failures} problems")
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")  # keep last: tools read the last line
    return 1 if failed or table_failures or doc_failures else 0


if __name__ == "__main__":
    sys.exit(main())
