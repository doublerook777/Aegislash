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
]


def _run_line(line: str) -> list[str]:
    record = {"record_id": "t.txt#doc", "file": "t.txt", "loc": "doc", "fmt": "text",
              "fields": [{"path": "text", "kind": "text", "context": None, "value": line}]}
    return [f["text"] for f in detect_file([record])[0]["findings"]
            if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]


def main() -> int:
    failed = 0
    for line, must_find, must_keep in CASES:
        found = _run_line(line)
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {line}\n      missed={missed} wrongly_removed={eaten}")
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
