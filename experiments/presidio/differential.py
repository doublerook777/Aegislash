"""differential.py <main root> <branch root>

Generated inputs run through both detectors. Reports (a) a patient/relative name word that main covers and the
branch does not, and (b) a medical word that the branch flags and main does not. All names are invented.
"""
import collections
import itertools
import json
import subprocess
import sys

NAMES = ["Sumitra Mahanta", "Nandlal Hazarika", "Barsha Kumari", "Kiruba Selvam", "Ompal Rathi", "सुमित्रा महंत"]
DOCTORS = ["Rathi", "Meena Iyer"]
MEDICAL = ["Diabetes Mellitus", "Normal", "Dengue Fever", "Paracetamol", "General Ward", "District Hospital",
           "Hypertension", "Chest Pain", "Not Known", "Atorvastatin", "CBC Report", "Follow Up"]

LINE_TEMPLATES = [
    "{T} {D} {I} {N} admitted", "Ref {T} {D} {I} {N} came today", "{I} {N} seen by {T} {D}", "{T} {D}, {I}: {N}, stable",
    "{K} {N} waiting outside", "{K} = {N} informed", "{K}- {N} informed", "{N} ({K}) gave consent",
    "Patient: {N} came with cough", "Patient: {N} with {K} {N2}", "Patient: {N} came with {K} {N2}",
    "Patient Name- verified: {N}", "Name- {N}", "Patient- {N}", "UHID-->44120987 {N} came", "MR# 31-207-5568 {I} {N}",
    "TPA card no. 55120987 {I} {N}", "{N} near old Hanuman Temple", "PID {N} admitted",
]
TITLES = ["Dr", "Dr.", "DR", "DR.", "dr", "DR.(MRS)", "Dr (Ms)", "Doctor"]
INTROS = ["Patient", "PATIENT", "patient", "PT NAME", "pt", "Mr", "MR", "Mrs", "W/o", "S/O", "wife", "son", ""]
KINS = ["wife", "son", "Son", "bro", "dtr", "sibling", "bahu", "bhabhi", "amma", "papa", "husband", "Attendant"]
HEADERS = ["Patient", "Patient Name", "Relative", "Guardian", "Guardian Contact", "परिजन_संपर्क", "Attendant Mobile",
           "Contact", "Mobile", "Doctor", "Doctor Remarks", "Nurse Note", "Remarks", "zz_unknown", "Landmark", "Nearby",
           "P.I.N.", "PIN", "Student", "Student Remarks", "Brought By", "Relation", "Policy No", "kin_mentioned",
           "Name", "Ward / Patient", "Address", "DOB", "History", "Referred By", "Nearby Hospital", "student_vision",
           "fon_no", "Contact of Bringer", "szFamContact"]
CELLS = ["{N}", "{N} 94127 30518", "94127 30518 {N}", "{K} {N}", "{K} - {N}", "{K} {N}, {K2} {N2}", "{N} ({K})",
         "{N} with {N2}", "{N} came with {K} {N2}", "{N} and {N2}", "Bed 4 - {N}", "ask {N}", "{T} {D} {I} {N}",
         "{N}, village Rampur", "near {N} house"]


def cases():
    out = []
    pick = itertools.cycle(NAMES)
    for template in LINE_TEMPLATES:
        slots = [x for x in ("T", "I", "K") if "{%s}" % x in template]
        pools = {"T": TITLES, "I": INTROS, "K": KINS}
        for combo in itertools.product(*(pools[s] for s in slots)):
            n, n2 = next(pick), next(pick)
            values = dict(zip(slots, combo), N=n, N2=n2, D=DOCTORS[0])
            base = template.format(**values)
            for text in (base, base.upper()) if n.isascii() else (base,):
                up = text != base
                names = [x.upper() if up else x for x in ([n, n2] if "{N2}" in template else [n])]
                out.append({"header": None, "value": text, "names": names, "medical": []})
    for header in HEADERS:
        for template in CELLS:
            for k, k2, n, n2 in zip(KINS, KINS[3:] + KINS[:3], NAMES * 2, (NAMES[2:] + NAMES[:2]) * 2):
                text = template.format(N=n, N2=n2, K=k, K2=k2, T="Dr", D=DOCTORS[1], I="Patient")
                out.append({"header": header, "value": text, "names": [n, n2] if "{N2}" in template else [n], "medical": []})
        for term in MEDICAL:
            out.append({"header": header, "value": term, "names": [], "medical": [term]})
            out.append({"header": header, "value": term + " noted since 2 days", "names": [], "medical": [term]})
    for kin, sep, term in itertools.product(KINS, [" ", " = ", " - ", ": "], MEDICAL):
        out.append({"header": None, "value": f"History {kin}{sep}{term} noted.", "names": [], "medical": [term]})
    for template, term in itertools.product(
            ["Patient- {M} today", "Name- {M}", "PID {M}", "{M} near old building", "DR {M}", "OBX {M}"], MEDICAL):
        out.append({"header": None, "value": template.format(M=term), "names": [], "medical": [term]})
    # whole columns: five values under one unreadable header
    phones = ["9412 7 30518", "70112-904-18", "8800 41 2276", "9435 2 11870"]
    for extra in ["ask wife Barsha Kumari", "{N}", "wife {N}", "not known"]:
        for n in NAMES:
            out.append({"column": phones + [extra.format(N=n)], "header": "zz_reach",
                        "names": [n] if "{N}" in extra or "Barsha" in extra else [], "medical": [], "value": None})
    return out


CHILD = """
import json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from aegis.detect import detect_file
result = []
for c in json.load(sys.stdin):
    if c.get("column"):
        records = [{"record_id": f"t.csv#row:{i}", "file": "t.csv", "loc": f"row:{i}", "fmt": "csv",
                    "fields": [{"path": "col:0", "kind": "value", "context": c["header"], "value": v}]}
                   for i, v in enumerate(c["column"])]
        res = detect_file(records)[-1]
        value = c["column"][-1]
    elif c["header"] is None:
        value = c["value"]
        res = detect_file([{"record_id": "t#doc", "file": "t.txt", "loc": "doc", "fmt": "text",
                            "fields": [{"path": "text", "kind": "text", "context": None, "value": value}]}])[0]
    else:
        value = c["value"]
        res = detect_file([{"record_id": "t.csv#row:1", "file": "t.csv", "loc": "row:1", "fmt": "csv",
                            "fields": [{"path": "col:0", "kind": "value", "context": c["header"], "value": value}]}])[0]
    result.append([value, [[f["start"], f["end"], f["type"]] for f in res["findings"]
                           if f["type"] not in ("CONDITION", "DISTRICT", "GENDER", "DATE", "AGE")]])
print(json.dumps(result))
"""


def run(root, items):
    return json.loads(subprocess.run([sys.executable, "-I", "-c", CHILD, root], input=json.dumps(items),
                                     capture_output=True, text=True, check=True).stdout)


def covered(value, spans, needle):
    """Which characters (letters, marks, digits) of every occurrence of needle are flagged."""
    flagged = {i for s, e, _ in spans for i in range(s, e)}
    got, start = set(), value.find(needle)
    while start >= 0:
        got |= {(start, i) for i, ch in enumerate(needle) if start + i in flagged and not ch.isspace()}
        start = value.find(needle, start + 1)
    return got


def main():
    items = cases()
    old, new = run(sys.argv[1], items), run(sys.argv[2], items)
    leaks, eaten, gains = [], [], 0
    for c, (value, a), (_, b) in zip(items, old, new):
        for name in c["names"]:
            before, after = covered(value, a, name), covered(value, b, name)
            if before - after:
                leaks.append((c["header"], value, name))
            gains += bool(after - before)
        for term in c["medical"]:
            if covered(value, b, term) - covered(value, a, term):
                eaten.append((c["header"], value, term))
    print(f"{len(items)} generated inputs; name cases covered better than main: {gains}")
    for title, rows in (("NAMES covered by main but NOT fully by the branch", leaks),
                        ("MEDICAL text flagged by the branch but not by main", eaten)):
        print(f"\n{title}: {len(rows)}")
        groups = collections.defaultdict(list)
        for header, value, what in rows:
            shape = value.replace(what, "<X>")
            for name in NAMES + [n.upper() for n in NAMES]:
                shape = shape.replace(name, "<N>")
            groups[(header, shape if header is None else shape[:40])].append(value)
        by_header = collections.Counter(h for h, _ in groups)
        print("  by header:", dict(by_header.most_common(15)))
        for key in list(groups)[:45]:
            print("   ", key[0], "|", groups[key][0][:100])


if __name__ == "__main__":
    main()
