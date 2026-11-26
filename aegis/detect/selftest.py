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
    (["fullName", "familyHeadRelation", "orderingClinician", "labRchId", "Village/Mohalla"],
     [["Renu Bhagat", "Father Suraj Bhagat", "Gautam Pillai", "RCH-JH-25-11902", "Rampur Kalan"]],
     {"familyHeadRelation": "RELATIVE_NAME", "orderingClinician": None, "labRchId": "MRN", "Village/Mohalla": "VILLAGE"}),
    (["पता_ग्राम_पिन", "वार्ड"], [["मकान नं. 5/ए, ग्राम रामपुर, 263139", "कस्तूरबा वार्ड"]],
     {"पता_ग्राम_पिन": "HOUSE", "वार्ड": None}),
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
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")  # keep last: tools read the last line
    return 1 if failed or table_failures else 0


if __name__ == "__main__":
    sys.exit(main())
