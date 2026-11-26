#!/usr/bin/env python3
"""Adversarial / Stress-Test Dataset Generator for Aegislash ("Secret Wards").

Designed specifically to expose edge cases, blind spots, and failure modes across:
  1. Unseen/obfuscated schemas (cryptic CSV headers, camelCase JSON keys, Surname-First, YOB)
  2. Evasion techniques (zero-width chars, Cyrillic homoglyphs, \\u escapes, URL-encoding, accented/rare names)
  3. Unlabeled & narrative free text (one-word names, uncommon surnames, unfamiliar ID formats, Devanagari phones)
  4. Hidden side channels (accented/base64/Devanagari filenames, CSV headers, JSON keys, _export_meta)
  5. Clinical preservation traps (eponyms, doctor names without Dr., C/O dual meaning, large lab/bill numbers)
  6. Linkage & anti-over-merge traps (triple homonyms, transitive chain attack, cross-script, ambiguous notes)
  7. Privacy & A5 re-identification traps (ages 97/102/0, rare conditions, leap/Devanagari/partial dates)
  8. 8 planted canaries in non-standard channels
  9. IO robustness traps (BOM-less UTF-16LE, semicolon/pipe CSV, ragged CSV, Binary FHIR, deep/corrupt/binary)
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import random
import shutil
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

REF_DATE = dt.date(2026, 11, 20)

_D_TABLE = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P_TABLE = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV_TABLE = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_aadhaar(rng: random.Random) -> str:
    digits = [rng.randint(2, 9)] + [rng.randint(0, 9) for _ in range(10)]
    c = 0
    for i, item in enumerate(reversed(digits), start=1):
        c = _D_TABLE[c][_P_TABLE[i % 8][item]]
    digits.append(_INV_TABLE[c])
    return "".join(str(d) for d in digits)


def deva_digits(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "०१२३४५६७८९"))


def _ent(
    etype: str, surface: str, person: str | None, role: str = "patient",
    script: str = "latin", channel: str = "content", match: str = "text",
    critical: bool = False, **extra: Any,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "type": etype, "surface": surface, "person": person, "role": role,
        "script": script, "channel": channel, "match": match, "critical": critical,
    }
    if match == "name":
        d["tokens"] = [t.casefold() for t in surface.split() if t]
        d["full"] = len(d["tokens"]) >= 2
    elif match in ("digits", "digits_exact"):
        d["key"] = "".join(ch for ch in surface if ch.isdigit())
    elif "key" not in extra:
        d["key"] = surface.casefold()
    d.update(extra)
    return d


def _name_ent(etype: str, surface: str, person: str | None, role: str = "patient",
              script: str = "latin", channel: str = "content", critical: bool = True,
              full: bool | None = None) -> dict[str, Any]:
    e = _ent(etype, surface, person, role=role, script=script, channel=channel, match="name", critical=critical)
    if full is not None:
        e["full"] = full
    return e


def _pres(text: str, kind: str, weight: float = 1.0, **extra: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"text": text, "kind": kind, "weight": weight}
    d.update(extra)
    return d


ADV_CANARIES = [
    ("C01", "Kezang Dema", "9811770011"),
    ("C02", "Ngangom Bimol", "9711770022"),
    ("C03", "Imlibenla Ao", "9611770033"),
    ("C04", "Lalhmangaiha Sailo", "9511770044"),
    ("C05", "Tshering Wangdi", "9411770055"),
    ("C06", "Choden Wangmo", "9311770066"),
    ("C07", "Adán Chávez", "9211770077"),
    ("C08", "Zothanpuia Ralte", "9111770088"),
]


def build_adversarial_patients(rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Craft specific adversarial patient personas + background population
    specs = [
        # P00001-P00003: Triple Homonym! Exact same name "Sunil Verma", totally different districts/ages/relatives
        {"first": "Sunil", "last": "Verma", "first_hi": "सुनील", "last_hi": "वर्मा", "g": "M", "age": 34, "rel": "Ramesh Verma", "rel_hi": "रमेश वर्मा", "rel_type": "S/o", "dist": "Lucknow", "vil": "Bakshi Talab", "pin": "226201", "rare": None},
        {"first": "Sunil", "last": "Verma", "first_hi": "सुनील", "last_hi": "वर्मा", "g": "M", "age": 61, "rel": "Mohan Verma", "rel_hi": "मोहन वर्मा", "rel_type": "S/o", "dist": "Varanasi", "vil": "Pindra Kalan", "pin": "221206", "rare": None},
        {"first": "Sunil", "last": "Verma", "first_hi": "सुनील", "last_hi": "वर्मा", "g": "M", "age": 49, "rel": "Kishan Verma", "rel_hi": "किशन वर्मा", "rel_type": "S/o", "dist": "Jhansi", "vil": "Mauranipur", "pin": "284204", "rare": None},
        # P00004-P00005: Transitive Chain Trap! Both "Ramesh Kumar" with relative "Suresh Kumar", DIFFERENT DOB & phones
        {"first": "Ramesh", "last": "Kumar", "first_hi": "रमेश", "last_hi": "कुमार", "g": "M", "age": 42, "rel": "Suresh Kumar", "rel_hi": "सुरेश कुमार", "rel_type": "S/o", "dist": "Unnao", "vil": "Purwa", "pin": "209825", "rare": None},
        {"first": "Ramesh", "last": "Kumar", "first_hi": "रमेश", "last_hi": "कुमार", "g": "M", "age": 29, "rel": "Suresh Kumar", "rel_hi": "सुरेश कुमार", "rel_type": "S/o", "dist": "Unnao", "vil": "Safipur", "pin": "209871", "rare": None},
        # P00006: Cross-script + Mohammad/Mohd./मोहम्मद linkage
        {"first": "Mohammad Tariq", "last": "Khan", "first_hi": "मोहम्मद तारिक", "last_hi": "खान", "g": "M", "age": 44, "rel": "Salim Khan", "rel_hi": "सलीम खान", "rel_type": "S/o", "dist": "Sitapur", "vil": "Biswan", "pin": "261201", "rare": None},
        # P00007-P00008: Ambiguous fragmentary pair! Two "Anjali"s married to two "Rajesh"s
        {"first": "Anjali", "last": "Tiwari", "first_hi": "अंजलि", "last_hi": "तिवारी", "g": "F", "age": 31, "rel": "Rajesh Tiwari", "rel_hi": "राजेश तिवारी", "rel_type": "W/o", "dist": "Hardoi", "vil": "Sandila", "pin": "241204", "rare": None},
        {"first": "Anjali", "last": "Mishra", "first_hi": "अंजलि", "last_hi": "मिश्रा", "g": "F", "age": 39, "rel": "Rajesh Mishra", "rel_hi": "राजेश मिश्रा", "rel_type": "W/o", "dist": "Hardoi", "vil": "Bilgram", "pin": "241301", "rare": None},
        # P00009-P00013: Extreme Age & Rare Condition A5 Re-ID Traps (0/F, 97/M, 102/F, 94/M, 89/F)
        {"first": "Kavya", "last": "Shukla", "first_hi": "काव्या", "last_hi": "शुक्ला", "g": "F", "age": 0, "rel": "Anurag Shukla", "rel_hi": "अनुराग शुक्ला", "rel_type": "D/o", "dist": "Gorakhpur", "vil": "Keshavpur", "pin": "273209", "rare": ("E83.01", "Wilson's disease")},
        {"first": "Bhagwan", "last": "Das", "first_hi": "भगवान", "last_hi": "दास", "g": "M", "age": 97, "rel": "Ramphal Das", "rel_hi": "रामफल दास", "rel_type": "S/o", "dist": "Ayodhya", "vil": "Sohawal", "pin": "224188", "rare": ("B55.0", "Visceral leishmaniasis (kala-azar)")},
        {"first": "Shyama", "last": "Kaur", "first_hi": "श्यामा", "last_hi": "कौर", "g": "F", "age": 102, "rel": "Baldev Singh", "rel_hi": "बलदेव सिंह", "rel_type": "W/o", "dist": "Aligarh", "vil": "Khair", "pin": "202138", "rare": ("G70.0", "Myasthenia gravis")},
        {"first": "Harbans", "last": "Lal", "first_hi": "हरबंस", "last_hi": "लाल", "g": "M", "age": 94, "rel": "Gopal Lal", "rel_hi": "गोपाल लाल", "rel_type": "S/o", "dist": "Prayagraj", "vil": "Phulpur", "pin": "212402", "rare": ("A82.9", "Rabies, unspecified")},
        {"first": "Rukmani", "last": "Devi", "first_hi": "रुक्मणी", "last_hi": "देवी", "g": "F", "age": 89, "rel": "Shivcharan", "rel_hi": "शिवचरण", "rel_type": "W/o", "dist": "Barabanki", "vil": "Haidergarh", "pin": "225124", "rare": ("E27.1", "Addison's disease")},
        # P00014-P00018: Uncommon non-gazetteer / accented / Doctor-homonym / Eponym-adjacent patients
        {"first": "Radhika", "last": "Kulkarni", "first_hi": "राधिका", "last_hi": "कुलकर्णी", "g": "F", "age": 54, "rel": "Vasant Kulkarni", "rel_hi": "वसंत कुलकर्णी", "rel_type": "W/o", "dist": "Pune", "vil": "Kothrud", "pin": "411038", "rare": ("G61.0", "Guillain-Barré syndrome")},
        {"first": "Pranav", "last": "Deshmukh", "first_hi": "प्रणव", "last_hi": "देशमुख", "g": "M", "age": 47, "rel": "Sharad Deshmukh", "rel_hi": "शरद देशमुख", "rel_type": "S/o", "dist": "Nagpur", "vil": "Kamptee", "pin": "441002", "rare": None},
        {"first": "Meera", "last": "Deshpande", "first_hi": "मीरा", "last_hi": "देशपांडे", "g": "F", "age": 38, "rel": "Anil Deshpande", "rel_hi": "अनिल देशपांडे", "rel_type": "W/o", "dist": "Lucknow", "vil": "Alambagh", "pin": "226005", "rare": None},
        {"first": "Pema", "last": "Choden", "first_hi": "पेमा", "last_hi": "चोदेन", "g": "F", "age": 28, "rel": "Dorje Wangchuk", "rel_hi": "दोरजे वांगचुक", "rel_type": "D/o", "dist": "Darjeeling", "vil": "Kurseong", "pin": "734203", "rare": None},
        {"first": "Agustín", "last": "Fonseca", "first_hi": "अगस्टिन", "last_hi": "फोन्सेका", "g": "M", "age": 52, "rel": "Mateo Fonseca", "rel_hi": "मातेओ फोन्सेका", "rel_type": "S/o", "dist": "Goa", "vil": "Mapusa", "pin": "403507", "rare": None},
        # P00019-P00024: General evasion / narrative / zero-width / homoglyph patients
        {"first": "Devika", "last": "Rao", "first_hi": "देविका", "last_hi": "राव", "g": "F", "age": 33, "rel": "Rameshwar Rao", "rel_hi": "रामेश्वर राव", "rel_type": "D/o", "dist": "Varanasi", "vil": "Raja Talab", "pin": "221311", "rare": None},
        {"first": "Priyanka", "last": "Sengupta", "first_hi": "प्रियंका", "last_hi": "सेनगुप्ता", "g": "F", "age": 41, "rel": "Subrata Sengupta", "rel_hi": "सुब्रत सेनगुप्ता", "rel_type": "W/o", "dist": "Gorakhpur", "vil": "Sahjanwa", "pin": "273209", "rare": None},
        {"first": "Rohan", "last": "Awasthi", "first_hi": "रोहन", "last_hi": "अवस्थी", "g": "M", "age": 26, "rel": "Mahesh Awasthi", "rel_hi": "महेश अवस्थी", "rel_type": "S/o", "dist": "Ayodhya", "vil": "Bikapur", "pin": "224204", "rare": None},
        {"first": "Rahul", "last": "Chaturvedi", "first_hi": "राहुल", "last_hi": "चतुर्वेदी", "g": "M", "age": 58, "rel": "Dinesh Chaturvedi", "rel_hi": "दीनेश चतुर्वेदी", "rel_type": "S/o", "dist": "Jhansi", "vil": "Garautha", "pin": "284203", "rare": None},
        {"first": "Lakshmi", "last": "Iyer", "first_hi": "लक्ष्मी", "last_hi": "अय्यर", "g": "F", "age": 66, "rel": "Venkat Iyer", "rel_hi": "वेंकट अय्यर", "rel_type": "W/o", "dist": "Prayagraj", "vil": "Soraon", "pin": "212502", "rare": None},
        {"first": "Gurleen", "last": "Sandhu", "first_hi": "गुरलीन", "last_hi": "संधू", "g": "F", "age": 45, "rel": "Harpreet Sandhu", "rel_hi": "हरप्रीत संधू", "rel_type": "W/o", "dist": "Aligarh", "vil": "Atrauli", "pin": "202280", "rare": None},
    ]

    people: list[dict[str, Any]] = []
    used_phones: set[str] = set()
    used_aadhaars: set[str] = set()

    def next_phone() -> str:
        while True:
            p = str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randint(0, 9)) for _ in range(9))
            if p not in used_phones:
                used_phones.add(p)
                return p

    def next_aadhaar() -> str:
        while True:
            a = verhoeff_aadhaar(rng)
            if a not in used_aadhaars:
                used_aadhaars.add(a)
                return a

    # Populate 24 adversarial patients + 96 background registry non-patients (120 total)
    for idx in range(1, 121):
        if idx <= len(specs):
            sp = specs[idx - 1]
            first_en, sur_en = sp["first"], sp["last"]
            first_hi, sur_hi = sp["first_hi"], sp["last_hi"]
            gender, age = sp["g"], sp["age"]
            rel_en, rel_hi, relation = sp["rel"], sp["rel_hi"], sp["rel_type"]
            dist_en, vil_en, pin = sp["dist"], sp["vil"], sp["pin"]
            rare = sp["rare"]
        else:
            # Background registry entries sharing districts/age bands to test A2/A4 & homonym noise
            base = specs[(idx - 1) % len(specs)]
            first_en = rng.choice(["Amit", "Neha", "Vikas", "Pooja", "Ravi", "Seema", "Suresh", "Kiran"])
            sur_en = base["last"]
            first_hi, sur_hi = first_en, base["last_hi"]
            gender = base["g"]
            age = max(1, base["age"] + rng.randint(-3, 3))
            rel_en, rel_hi, relation = "Mohan " + sur_en, "मोहन", base["rel_type"]
            dist_en, vil_en, pin = base["dist"], base["vil"], base["pin"]
            rare = None

        dob = dt.date(REF_DATE.year - age, rng.randint(1, 12), rng.randint(1, 28))
        if age == 0:
            dob = REF_DATE - dt.timedelta(days=45)
        phone = next_phone()
        aadhaar = next_aadhaar()
        full_en = f"{first_en} {sur_en}"
        full_hi = f"{first_hi} {sur_hi}"
        p = {
            "pid": f"P{idx:05d}",
            "rid": f"ADV{1000000 + idx * 71:07d}",
            "first_en": first_en, "sur_en": sur_en, "full_en": full_en,
            "first_hi": first_hi, "sur_hi": sur_hi, "full_hi": full_hi,
            "relation": relation, "rel_en": rel_en, "rel_hi": rel_hi,
            "gender": gender, "age": age, "dob": dob,
            "house_num": str(rng.randint(10, 499)),
            "vil_en": vil_en, "dist_en": dist_en, "dist_key": dist_en.casefold(),
            "village_code": f"{dist_en.casefold()}:0:0", "pin": pin,
            "phone": phone, "aadhaar": aadhaar,
            "email": f"{first_en.lower().replace(' ','')}.{sur_en.lower()}{idx}@example.com",
            "pan": f"QWX{chr(65 + idx % 20)}E{1000 + idx}L",
            "abha": f"91-{1000+idx}-{2000+idx}-{3000+idx}",
            "uhid_a": f"KGH/2026/{9000 + idx:04d}",
            "uhid_b": f"ADV-{70000 + idx * 11:06d}",
            "rare": rare is not None,
            "diag_code": rare[0] if rare else "I10",
            "diag_desc": rare[1] if rare else "Essential (primary) hypertension",
        }
        if idx <= len(specs):
            p["patient_id"] = f"PT{idx:05d}"
        people.append(p)

    return people, people[:len(specs)]


def generate_adversarial(out_dir: Path, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    if out_dir.exists():
        for child in ["input", "truth", "attacker", "dataset_manifest.json", "out"]:
            t = out_dir / child
            if t.is_dir():
                shutil.rmtree(t)
            elif t.exists():
                t.unlink()

    inp = out_dir / "input"
    truth_dir = out_dir / "truth"
    att_dir = out_dir / "attacker"
    for sub in ["unseen_schema", "evasion", "narrative_leaks", "hidden_channels", "clinical_traps",
                "linkage_traps", "privacy_traps", "canaries", "io_traps", "clean"]:
        (inp / sub).mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    att_dir.mkdir(parents=True, exist_ok=True)

    people, patients = build_adversarial_patients(rng)
    files_truth: dict[str, Any] = {}
    known_facts: list[dict[str, Any]] = []

    def reg(rel: str, raw: bytes, fmt: str, enc: str, delim: str | None, expect: str, cat: str,
            clean: bool, hint: str, gen: list[str], units: dict[str, Any]) -> None:
        p = inp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        files_truth[rel] = {
            "path": rel, "format": fmt, "encoding": enc, "delimiter": delim,
            "expect": expect, "category": cat, "clean": clean, "date_hint": hint,
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
            "generalizable": gen, "units": units,
        }

    # ------------------------------------------------------------------
    # 1. UNSEEN SCHEMA (cryptic headers, Surname-First, YOB, BOM-less UTF-16LE, camelCase JSON)
    # ------------------------------------------------------------------
    # 1a. Cryptic CSV with Surname, Given + YOB + pipe delimiter (BOM-less UTF-16LE!)
    p13, p14, p16, p17 = patients[13], patients[14], patients[16], patients[17]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="|", lineterminator="\n")
    w.writerow(["P_NOM", "K_SUP", "X_YOB", "Z_6D", "PAT_TEL_1", "AADH_NO", "CLIN_MEMO"])
    u1 = {}
    for idx, p in enumerate([p13, p14, p16, p17]):
        rev_name = f"{p['sur_en']}, {p['first_en']}"
        yob = str(p["dob"].year)
        w.writerow([rev_name, p["rel_en"], yob, p["pin"], p["phone"], p["aadhaar"], f"BP 122/80; {p['diag_desc']}"])
        u1[f"row:{idx}"] = {
            "loc": f"row:{idx}", "patient": p["patient_id"], "cid": f"{p['patient_id']}#0", "link": "required", "tags": ["unseen_schema"],
            "entities": [
                _name_ent("PATIENT_NAME", p["first_en"], p["pid"], critical=True, full=False),
                _name_ent("PATIENT_NAME", p["sur_en"], p["pid"], critical=True, full=False),
                _name_ent("RELATIVE_NAME", p["rel_en"], p["pid"], role="relative", critical=False),
                _ent("DOB", yob, p["pid"], match="text"),
                _ent("PIN", p["pin"], p["pid"], match="digits_exact"),
                _ent("PHONE", p["phone"], p["pid"], match="digits", critical=True),
                _ent("AADHAAR", p["aadhaar"], p["pid"], match="digits", critical=True),
            ],
            "preserve": [_pres("122/80", "vital", 1.0), _pres(p["diag_desc"], "diagnosis", 1.0)],
            "dates": [], "fields": [{"kind": "pin", "true": p["pin"], "path": "col:Z_6D", "patient": p["patient_id"]}], "exclude": [],
        }
    reg("unseen_schema/cryptic_pipe_utf16le.csv", buf.getvalue().encode("utf-16-le"),
        "csv", "utf-16-le", "|", "sanitize", "unseen_schema", False, "dmy", ["col:Z_6D"], u1)

    # 1b. Unseen camelCase JSON + FHIR-like {url, valueString} unfamiliar extension
    ext_obj = {
        "schemaVersion": "x9",
        "records": [
            {
                "recRef": f"CR.No. 771/26",
                "subjectFullName": p16["full_en"],
                "kinGuardian": p16["rel_en"],
                "birthYear": p16["dob"].year,
                "postal6": p16["pin"],
                "contactDigits": f"98.45.01.12.23",
                "extensions": [{"url": "https://example.org/ext/mothers-maiden-handle", "valueString": "Choden Wangmo"}],
                "wardEncounterDate": "2026-09-14",
                "clinicalSummary": f"K/C/O {p16['diag_desc']}; Tab Metformin 500 mg 1-0-1",
            }
        ],
    }
    reg("unseen_schema/unfamiliar_keys.json", json.dumps(ext_obj, indent=2).encode("utf-8"),
        "json", "utf-8", None, "sanitize", "unseen_schema", False, "iso", [], {
            "/records/0": {
                "loc": "/records/0", "patient": p16["patient_id"], "cid": f"{p16['patient_id']}#0", "link": "required", "tags": ["unseen_schema"],
                "entities": [
                    _ent("MRN", "771/26", p16["pid"], match="digits", critical=True),
                    _name_ent("PATIENT_NAME", p16["full_en"], p16["pid"], critical=True),
                    _name_ent("RELATIVE_NAME", p16["rel_en"], p16["pid"], role="relative", critical=False),
                    _ent("PIN", p16["pin"], p16["pid"], match="digits_exact"),
                    _ent("PHONE", "98.45.01.12.23", p16["pid"], match="digits", critical=True),
                    _name_ent("RELATIVE_NAME", "Choden Wangmo", p16["pid"], role="relative", critical=False),
                ],
                "preserve": [_pres("Metformin 500 mg", "medication", 1.0), _pres("1-0-1", "dose", 1.0)],
                "dates": [{"true": "2026-09-14", "event": "visit", "patient": p16["patient_id"], "hint": "iso", "path": "/records/0/wardEncounterDate"}],
                "fields": [],
            }
        })

    # ------------------------------------------------------------------
    # 2. EVASION TECHNIQUES (zero-width chars, Cyrillic homoglyphs, \u escapes, URL-encoded, deep nested b64)
    # ------------------------------------------------------------------
    p18, p19, p21 = patients[18], patients[19], patients[21]
    zw_name = "Ra\u200bhul\u200d Chatur\u200bvedi"
    zw_phone = f"{p21['phone'][:5]}\u200b{p21['phone'][5:]}"
    zw_aadh = f"{p21['aadhaar'][:4]}\u200b{p21['aadhaar'][4:8]}\u200b{p21['aadhaar'][8:]}"
    # Cyrillic 'а' (U+0430) and 'е' (U+0435) homoglyphs inside Latin name
    homo_name = "D\u0435vik\u0430 R\u0430o"
    ev_txt = (
        f"Patient: {zw_name}, Mob: {zw_phone}, Aadhaar: {zw_aadh}.\n"
        f"Co-admitted: {homo_name}, contact {p18['phone']}.\n"
        f"URL ref: https://portal.example/view?patient={urllib.parse.quote(p19['full_en'])}&tel={urllib.parse.quote('+91 ' + p19['phone'])}\n"
        f"BP 118/76 mmHg, Tab Paracetamol 650 mg 1-1-1 x 5 days.\n"
    )
    reg("evasion/obfuscated_tokens.txt", ev_txt.encode("utf-8"), "text", "utf-8", None, "sanitize", "evasion", False, "dmy", [], {
        "doc": {
            "loc": "doc", "patient": p21["patient_id"], "cid": f"{p21['patient_id']}#0", "link": "required", "tags": ["evasion"],
            "entities": [
                _name_ent("PATIENT_NAME", zw_name, p21["pid"], critical=True),
                _ent("PHONE", zw_phone, p21["pid"], match="digits", critical=True),
                _ent("AADHAAR", zw_aadh, p21["pid"], match="digits", critical=True),
                _name_ent("PATIENT_NAME", homo_name, p18["pid"], critical=True),
                _ent("PHONE", p18["phone"], p18["pid"], match="digits", critical=True),
                _name_ent("PATIENT_NAME", urllib.parse.quote(p19["full_en"]), p19["pid"], critical=True),
                _ent("PHONE", p19["phone"], p19["pid"], match="digits", critical=True),
            ],
            "preserve": [_pres("118/76", "vital", 1.0), _pres("Paracetamol 650 mg", "medication", 1.0)],
            "dates": [], "fields": [],
        }
    })

    # 2b. \uXXXX-escaped Devanagari + nested base64 under non-standard key "payload_blob"
    u_esc_json = (
        '{\n'
        f'  "note_hi": "\\u0930\\u093e\\u0939\\u0941\\u0932 \\u091a\\u0924\\u0941\\u0930\\u094d\\u0935\\u0947\\u0926\\u0940 \\u0915\\u094b \\u092c\\u0941\\u0916\\u093e\\u0930 \\u0939\\u0948",\n'
        f'  "payload_blob": "{base64.b64encode(f"Patient {p19["full_en"]}, phone {p19["phone"]}".encode()).decode()}",\n'
        '  "diagnosis": "Typhoid fever"\n'
        '}\n'
    )
    reg("evasion/escaped_and_blob.json", u_esc_json.encode("utf-8"), "json", "utf-8", None, "sanitize", "evasion", False, "dmy", [], {
        "doc": {
            "loc": "doc", "patient": p21["patient_id"], "cid": f"{p21['patient_id']}#0", "link": "required", "tags": ["evasion"],
            "entities": [
                _name_ent("PATIENT_NAME", "राहुल चतुर्वेदी", p21["pid"], script="deva", critical=True),
                _name_ent("PATIENT_NAME", p19["full_en"], p19["pid"], channel="base64", critical=True),
                _ent("PHONE", p19["phone"], p19["pid"], channel="base64", match="digits", critical=True),
            ],
            "preserve": [_pres("Typhoid fever", "diagnosis", 1.0)],
            "dates": [], "fields": [],
        }
    })

    # ------------------------------------------------------------------
    # 3. NARRATIVE & UNLABELED FREE TEXT (one-word names, rare surnames, Devanagari phone, odd IDs)
    # ------------------------------------------------------------------
    p20, p22, p23 = patients[20], patients[22], patients[23]
    nar_txt = (
        f"Handover: Bed 4 given to {p18['first_en']}, afebrile overnight.\n"
        f"{p19['first_en']} signed the surgical consent form.\n"
        f"{p20['first_en']} took discharge against medical advice on 14/08/2026.\n"
        f"Follow up with {p16['full_en']} and {p17['full_en']} at 10 am.\n"
        f"रोगी का नाम - {p22['full_hi']}, मो. {deva_digits(p22['phone'])}, निवासी ग्राम {p22['vil_en']}।\n"
        f"Rec# : HOSP/2026/09/00441, IP#NICU-26-771, Pt ID: #A1B2C3, PAN {p23['pan']}.\n"
        f"Lives behind Old Post Office, Shastri Colony, Pin {p23['pin']}.\n"
        f"BP 120/80 mmHg, Tab Azithromycin 500 mg OD x 5 days.\n"
    )
    reg("narrative_leaks/unlabeled_ward_handover.txt", nar_txt.encode("utf-8"), "text", "utf-8", None, "sanitize", "narrative", False, "dmy", [], {
        "doc": {
            "loc": "doc", "patient": None, "cid": None, "link": "none", "tags": ["narrative"],
            "entities": [
                _name_ent("PATIENT_NAME", p18["first_en"], p18["pid"], critical=True, full=False),
                _name_ent("PATIENT_NAME", p19["first_en"], p19["pid"], critical=True, full=False),
                _name_ent("PATIENT_NAME", p20["first_en"], p20["pid"], critical=True, full=False),
                _name_ent("PATIENT_NAME", p16["full_en"], p16["pid"], critical=True),
                _name_ent("PATIENT_NAME", p17["full_en"], p17["pid"], critical=True),
                _name_ent("PATIENT_NAME", p22["full_hi"], p22["pid"], script="deva", critical=True),
                _ent("PHONE", deva_digits(p22["phone"]), p22["pid"], script="deva", match="digits", critical=True),
                _ent("MRN", "HOSP/2026/09/00441", None, match="digits", critical=True),
                _ent("MRN", "NICU-26-771", None, match="digits", critical=True),
                _ent("MRN", "A1B2C3", None, match="text", critical=True),
                _ent("PAN", p23["pan"], p23["pid"], critical=True),
                _ent("PIN", p23["pin"], p23["pid"], match="digits_exact"),
            ],
            "preserve": [_pres("120/80", "vital", 1.0), _pres("Azithromycin 500 mg", "medication", 1.0)],
            "dates": [], "fields": [],
        }
    })

    # ------------------------------------------------------------------
    # 4. HIDDEN CHANNELS (accented filename, Devanagari filename, b64 filename, key PII, header PII)
    # ------------------------------------------------------------------
    reg(f"hidden_channels/{p17['first_en']}_{p17['sur_en']}_{p17['phone']}.txt",
        f"Routine OPD checkup complete. Temp 98.6 F. Paracetamol 650 mg SOS.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "hidden", False, "dmy", [], {
            "@filename": {"loc": "@filename", "patient": None, "cid": None, "link": "none", "tags": [],
                          "entities": [_name_ent("PATIENT_NAME", f"{p17['first_en']}_{p17['sur_en']}", p17["pid"], channel="filename", critical=True),
                                       _ent("PHONE", p17["phone"], p17["pid"], channel="filename", match="digits", critical=True)],
                          "preserve": [], "dates": [], "fields": []},
            "doc": {"loc": "doc", "patient": p17["patient_id"], "cid": None, "link": "none", "tags": [], "entities": [],
                    "preserve": [_pres("Paracetamol 650 mg", "medication", 1.0)], "dates": [], "fields": []},
        })

    reg(f"hidden_channels/{p22['first_hi']}_{p22['sur_hi']}_पर्चा.txt",
        "BP 110/70, Tab Pantoprazole 40 mg 1-0-0.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "hidden", False, "dmy", [], {
            "@filename": {"loc": "@filename", "patient": None, "cid": None, "link": "none", "tags": [],
                          "entities": [_name_ent("PATIENT_NAME", f"{p22['first_hi']}_{p22['sur_hi']}", p22["pid"], script="deva", channel="filename", critical=True)],
                          "preserve": [], "dates": [], "fields": []},
            "doc": {"loc": "doc", "patient": p22["patient_id"], "cid": None, "link": "none", "tags": [], "entities": [],
                    "preserve": [_pres("110/70", "vital", 1.0)], "dates": [], "fields": []},
        })

    b64_fn = base64.urlsafe_b64encode(f"{p14['full_en']}_{p14['phone']}".encode()).decode().rstrip("=")
    reg(f"hidden_channels/{b64_fn}.txt",
        "Stable on discharge. Follow up in 1 week.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "hidden", False, "dmy", [], {
            "@filename": {"loc": "@filename", "patient": None, "cid": None, "link": "none", "tags": [],
                          "entities": [_ent("PATIENT_NAME", b64_fn, p14["pid"], channel="filename", critical=True)],
                          "preserve": [], "dates": [], "fields": []},
            "doc": {"loc": "doc", "patient": p14["patient_id"], "cid": None, "link": "none", "tags": [], "entities": [],
                    "preserve": [], "dates": [], "fields": []},
        })

    reg("hidden_channels/phone_keyed_index.json",
        json.dumps({p14["phone"]: {"visits": 2, "ward": "Ward 3"}, p14["full_en"]: p14["uhid_a"]}, indent=2).encode("utf-8"),
        "json", "utf-8", None, "sanitize", "hidden", False, "dmy", [], {
            "@file": {"loc": "@file", "patient": None, "cid": None, "link": "none", "tags": [],
                      "entities": [_ent("PHONE", p14["phone"], p14["pid"], channel="key", match="digits", critical=True),
                                   _name_ent("PATIENT_NAME", p14["full_en"], p14["pid"], channel="key", critical=True),
                                   _ent("MRN", p14["uhid_a"], p14["pid"], match="digits", critical=True)],
                      "preserve": [], "dates": [], "fields": []},
        })

    # ------------------------------------------------------------------
    # 5. CLINICAL PRESERVATION TRAPS (doctor without Dr., C/O dual meaning, large lab/bill numbers, eponyms)
    # ------------------------------------------------------------------
    p15 = patients[15]  # Meera Deshpande (also a doctor name trap!)
    clin_txt = (
        f"Patient: {p15['full_en']}, UHID: {p15['uhid_a']}, Mob: {p15['phone']}\n"
        f"Attending consultant Dr. Meera Deshpande reviewed the chart; Meera Deshpande ordered CBC.\n"
        f"C/O chest pain x 2 days; c/o {p15['rel_en']}, House {p15['house_num']}, {p15['vil_en']}.\n"
        f"K/C/O Hashimoto's thyroiditis, Parkinson's disease, Cushing's syndrome, Addison's disease.\n"
        f"Platelets, 245100 and WBC, 118200 today. Total bill, 148500, paid in cash.\n"
        f"Seen by Nurse Mary Thomas and Sister Anita Nair. ASHA didi Kavita accompanied.\n"
        f"Referred from Ram Manohar Lohia Hospital and Sharma Nursing Home.\n"
        f"Tab Telmisartan 40 mg 1-0-0, Inj Ceftriaxone 1g IV BD x 7 days.\n"
    )
    reg("clinical_traps/trap_dense_note.txt", clin_txt.encode("utf-8"), "text", "utf-8", None, "sanitize", "clinical_traps", False, "dmy", [], {
        "doc": {
            "loc": "doc", "patient": p15["patient_id"], "cid": f"{p15['patient_id']}#0", "link": "required", "tags": ["clinical_traps"],
            "entities": [
                _name_ent("PATIENT_NAME", p15["full_en"], p15["pid"], critical=True),
                _ent("MRN", p15["uhid_a"], p15["pid"], match="digits", critical=True),
                _ent("PHONE", p15["phone"], p15["pid"], match="digits", critical=True),
                _name_ent("RELATIVE_NAME", p15["rel_en"], p15["pid"], role="relative", critical=False),
                _ent("HOUSE", f"House {p15['house_num']}", p15["pid"]),
                _ent("VILLAGE", p15["vil_en"], p15["pid"]),
            ],
            "preserve": [
                _pres("Dr. Meera Deshpande", "doctor", 0.5, trap="doctor"),
                _pres("chest pain", "complaint", 1.0),
                _pres("Hashimoto's thyroiditis", "eponym", 1.0),
                _pres("Parkinson's disease", "eponym", 1.0),
                _pres("Cushing's syndrome", "eponym", 1.0),
                _pres("Addison's disease", "eponym", 1.0),
                _pres("245100", "lab", 1.0),
                _pres("118200", "lab", 1.0),
                _pres("148500", "billing", 1.0),
                _pres("Mary Thomas", "staff", 1.0),
                _pres("Anita Nair", "staff", 1.0),
                _pres("Ram Manohar Lohia Hospital", "hospital", 1.0),
                _pres("Sharma Nursing Home", "hospital", 1.0),
                _pres("Telmisartan 40 mg", "medication", 1.0),
            ],
            "dates": [], "fields": [],
        }
    })

    # ------------------------------------------------------------------
    # 6. LINKAGE & ANTI-OVER-MERGE TRAPS (triple homonym, transitive chain, cross-script, ambiguous)
    # ------------------------------------------------------------------
    # 6a. Triple homonym registration CSV (3 distinct Sunil Vermas)
    p0, p1, p2 = patients[0], patients[1], patients[2]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["UHID", "Patient Name", "Gender", "Age", "DOB", "Relation", "Relative Name", "Village", "District", "PIN", "Mobile"])
    hom_u = {}
    for idx, p in enumerate([p0, p1, p2]):
        dob_s = p["dob"].strftime("%d/%m/%Y")
        w.writerow([p["uhid_a"], p["full_en"], p["gender"], str(p["age"]), dob_s, p["relation"], p["rel_en"], p["vil_en"], p["dist_en"], p["pin"], p["phone"]])
        hom_u[f"row:{idx}"] = {
            "loc": f"row:{idx}", "patient": p["patient_id"], "cid": f"{p['patient_id']}#0", "link": "required", "tags": ["homonym"],
            "entities": [
                _ent("MRN", p["uhid_a"], p["pid"], match="digits", critical=True),
                _name_ent("PATIENT_NAME", p["full_en"], p["pid"], critical=True),
                _ent("DOB", dob_s, p["pid"], match="dob", key=p["dob"].isoformat()),
                _name_ent("RELATIVE_NAME", p["rel_en"], p["pid"], role="relative", critical=False),
                _ent("VILLAGE", p["vil_en"], p["pid"]),
                _ent("PIN", p["pin"], p["pid"], match="digits_exact"),
                _ent("PHONE", p["phone"], p["pid"], match="digits", critical=True),
            ],
            "preserve": [_pres(p["dist_en"], "district", 0.3)], "dates": [], "fields": [
                {"kind": "age", "true": p["age"], "path": "col:Age", "patient": p["patient_id"]},
                {"kind": "district", "true": p["dist_key"], "path": "col:District", "patient": p["patient_id"]},
            ],
        }
    reg("linkage_traps/triple_homonym.csv", buf.getvalue().encode("utf-8-sig"),
        "csv", "utf-8-sig", ",", "sanitize", "linkage", False, "dmy", ["col:Age", "col:DOB", "col:PIN", "col:Village"], hom_u)

    # Secondary note for Sunil Verma #2 (matches by Name + Village + Age±1 ONLY, no ID)
    reg("linkage_traps/homonym_2_note.txt",
        f"OPD Follow-up: {p1['full_en']}, Age {p1['age'] + 1} yrs, Gram {p1['vil_en']}, Distt. {p1['dist_en']}. BP 130/84.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "linkage", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p1["patient_id"], "cid": f"{p1['patient_id']}#1", "link": "required", "tags": ["homonym"],
                    "entities": [_name_ent("PATIENT_NAME", p1["full_en"], p1["pid"], critical=True),
                                 _ent("VILLAGE", p1["vil_en"], p1["pid"])],
                    "preserve": [_pres("130/84", "vital", 1.0)], "dates": [], "fields": [{"kind": "age", "true": p1["age"], "path": None, "patient": p1["patient_id"]}]}
        })

    # 6b. Transitive Chain Attack: two different "Ramesh Kumar"s with relative "Suresh Kumar", DIFFERENT phones/DOBs
    p3, p4 = patients[3], patients[4]
    chain_obj = {
        "entries": [
            {"name": "Ramesh", "phone": p3["phone"], "note": "Admitted with fever"},
            {"name": p3["full_en"], "phone": p3["phone"], "relative": "S/o Suresh Kumar", "dob": p3["dob"].isoformat()},
            {"name": p4["full_en"], "phone": p4["phone"], "relative": "S/o Suresh Kumar", "dob": p4["dob"].isoformat()},
        ]
    }
    reg("linkage_traps/transitive_chain.json", json.dumps(chain_obj, indent=2).encode("utf-8"),
        "json", "utf-8", None, "sanitize", "linkage", False, "iso", [], {
            "/entries/0": {"loc": "/entries/0", "patient": p3["patient_id"], "cid": f"{p3['patient_id']}#0", "link": "required", "tags": ["transitive"],
                           "entities": [_name_ent("PATIENT_NAME", "Ramesh", p3["pid"], critical=False, full=False),
                                        _ent("PHONE", p3["phone"], p3["pid"], match="digits", critical=True)],
                           "preserve": [], "dates": [], "fields": []},
            "/entries/1": {"loc": "/entries/1", "patient": p3["patient_id"], "cid": f"{p3['patient_id']}#1", "link": "required", "tags": ["transitive"],
                           "entities": [_name_ent("PATIENT_NAME", p3["full_en"], p3["pid"], critical=True),
                                        _ent("PHONE", p3["phone"], p3["pid"], match="digits", critical=True),
                                        _name_ent("RELATIVE_NAME", "Suresh Kumar", p3["pid"], role="relative", critical=False),
                                        _ent("DOB", p3["dob"].isoformat(), p3["pid"], match="dob", key=p3["dob"].isoformat())],
                           "preserve": [], "dates": [], "fields": [{"kind": "dob", "true": p3["dob"].isoformat(), "path": "/entries/1/dob", "patient": p3["patient_id"]}]},
            "/entries/2": {"loc": "/entries/2", "patient": p4["patient_id"], "cid": f"{p4['patient_id']}#0", "link": "required", "tags": ["transitive"],
                           "entities": [_name_ent("PATIENT_NAME", p4["full_en"], p4["pid"], critical=True),
                                        _ent("PHONE", p4["phone"], p4["pid"], match="digits", critical=True),
                                        _name_ent("RELATIVE_NAME", "Suresh Kumar", p4["pid"], role="relative", critical=False),
                                        _ent("DOB", p4["dob"].isoformat(), p4["pid"], match="dob", key=p4["dob"].isoformat())],
                           "preserve": [], "dates": [], "fields": [{"kind": "dob", "true": p4["dob"].isoformat(), "path": "/entries/2/dob", "patient": p4["patient_id"]}]},
        })

    # 6c. Cross-script Mohammad/Mohd./मोहम्मद linkage across 3 files
    p5 = patients[5]
    reg("linkage_traps/tariq_latin.txt",
        f"Patient: Mohammad Tariq Khan, DOB: {p5['dob'].strftime('%d/%m/%Y')}, S/o Salim Khan, Mob: {p5['phone']}\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "linkage", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p5["patient_id"], "cid": f"{p5['patient_id']}#0", "link": "required", "tags": [],
                    "entities": [_name_ent("PATIENT_NAME", "Mohammad Tariq Khan", p5["pid"], critical=True),
                                 _ent("DOB", p5["dob"].strftime("%d/%m/%Y"), p5["pid"], match="dob", key=p5["dob"].isoformat()),
                                 _name_ent("RELATIVE_NAME", "Salim Khan", p5["pid"], role="relative", critical=False),
                                 _ent("PHONE", p5["phone"], p5["pid"], match="digits", critical=True)],
                    "preserve": [], "dates": [], "fields": [{"kind": "dob", "true": p5["dob"].isoformat(), "path": None, "patient": p5["patient_id"]}]}
        })
    reg("linkage_traps/tariq_deva.txt",
        f"रोगी: मोहम्मद तारिक खान, पिता: सलीम खान, जन्मतिथि: {p5['dob'].strftime('%d-%m-%Y')}\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "linkage", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p5["patient_id"], "cid": f"{p5['patient_id']}#1", "link": "required", "tags": [],
                    "entities": [_name_ent("PATIENT_NAME", "मोहम्मद तारिक खान", p5["pid"], script="deva", critical=True),
                                 _name_ent("RELATIVE_NAME", "सलीम खान", p5["pid"], role="relative", script="deva", critical=False),
                                 _ent("DOB", p5["dob"].strftime("%d-%m-%Y"), p5["pid"], match="dob", key=p5["dob"].isoformat())],
                    "preserve": [], "dates": [], "fields": [{"kind": "dob", "true": p5["dob"].isoformat(), "path": None, "patient": p5["patient_id"]}]}
        })
    reg("linkage_traps/tariq_hinglish.txt",
        "Mohd. Tariq sahab (S/o Salim Khan) ka BP 124/78 hai. Tab Amlodipine 5 mg diya.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "linkage", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p5["patient_id"], "cid": f"{p5['patient_id']}#2", "link": "required", "tags": [],
                    "entities": [_name_ent("PATIENT_NAME", "Mohd. Tariq sahab", p5["pid"], script="hinglish", critical=True),
                                 _name_ent("RELATIVE_NAME", "Salim Khan", p5["pid"], role="relative", critical=False)],
                    "preserve": [_pres("124/78", "vital", 1.0)], "dates": [], "fields": []}
        })

    # 6d. Ambiguous Anjali W/o Rajesh (two distinct Anjalis share first name + husband first name)
    p6, p7 = patients[6], patients[7]
    reg("linkage_traps/anjali_reg.csv",
        (
            "uhid,name,rel,dob,district\n"
            f"{p6['uhid_a']},{p6['full_en']},W/o {p6['rel_en']},{p6['dob'].strftime('%d/%m/%Y')},{p6['dist_en']}\n"
            f"{p7['uhid_a']},{p7['full_en']},W/o {p7['rel_en']},{p7['dob'].strftime('%d/%m/%Y')},{p7['dist_en']}\n"
        ).encode("utf-8"),
        "csv", "utf-8", ",", "sanitize", "linkage", False, "dmy", ["col:dob"], {
            "row:0": {"loc": "row:0", "patient": p6["patient_id"], "cid": f"{p6['patient_id']}#0", "link": "required", "tags": [],
                      "entities": [_ent("MRN", p6["uhid_a"], p6["pid"], match="digits", critical=True),
                                   _name_ent("PATIENT_NAME", p6["full_en"], p6["pid"], critical=True),
                                   _name_ent("RELATIVE_NAME", p6["rel_en"], p6["pid"], role="relative", critical=False),
                                   _ent("DOB", p6["dob"].strftime("%d/%m/%Y"), p6["pid"], match="dob", key=p6["dob"].isoformat())],
                      "preserve": [], "dates": [], "fields": []},
            "row:1": {"loc": "row:1", "patient": p7["patient_id"], "cid": f"{p7['patient_id']}#0", "link": "required", "tags": [],
                      "entities": [_ent("MRN", p7["uhid_a"], p7["pid"], match="digits", critical=True),
                                   _name_ent("PATIENT_NAME", p7["full_en"], p7["pid"], critical=True),
                                   _name_ent("RELATIVE_NAME", p7["rel_en"], p7["pid"], role="relative", critical=False),
                                   _ent("DOB", p7["dob"].strftime("%d/%m/%Y"), p7["pid"], match="dob", key=p7["dob"].isoformat())],
                      "preserve": [], "dates": [], "fields": []},
        })
    reg("linkage_traps/anjali_ambiguous_note.txt",
        "Discharge note: Anjali, W/o Rajesh, discharged in stable condition. BP 116/74.\n".encode("utf-8"),
        "text", "utf-8", None, "sanitize", "linkage", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p6["patient_id"], "cid": None, "link": "ambiguous", "tags": ["ambiguous"],
                    "entities": [_name_ent("PATIENT_NAME", "Anjali", p6["pid"], critical=False, full=False),
                                 _name_ent("RELATIVE_NAME", "Rajesh", p6["pid"], role="relative", critical=False, full=False)],
                    "preserve": [_pres("116/74", "vital", 1.0)], "dates": [], "fields": []}
        })

    # ------------------------------------------------------------------
    # 7. PRIVACY, EXTREME AGE, DATE FORMAT & A5 RE-IDENTIFICATION TRAPS
    # ------------------------------------------------------------------
    for p_idx, p in enumerate(patients[8:13]):  # 0/F, 97/M, 102/F, 94/M, 89/F with rare conditions!
        adm = dt.date(2024, 2, 29) if p_idx == 0 else dt.date(2026, 3 + p_idx, 10)
        stay = 14 if p_idx % 2 == 0 else 21
        dis = adm + dt.timedelta(days=stay)
        age_str = f"{p['age']}/{p['gender']}" if p_idx < 3 else f"Age: {p['age']} Yrs"
        date_adm = deva_digits(adm.strftime("%d/%m/%Y")) if p_idx == 4 else adm.strftime("%d/%m/%Y")
        date_dis = dis.strftime("%d %B %Y") if p_idx == 2 else f"{dis.isoformat()}T23:55:00+05:30"
        txt = (
            f"DISCHARGE SUMMARY - Rare Disease Registry\n"
            f"Name: {p['full_en']} ({age_str})   UHID: {p['uhid_a']}\n"
            f"Village: {p['vil_en']}, District: {p['dist_en']}, PIN: {p['pin']}\n"
            f"Admission: {date_adm}   Discharge: {date_dis}   Follow-up: Nov 2026\n"
            f"Diagnosis: {p['diag_desc']} ({p['diag_code']})\n"
            f"Procedure: Deep brain stimulation\n"
        )
        reg(f"privacy_traps/extreme_rare_{p_idx}.txt", txt.encode("utf-8"), "text", "utf-8", None, "sanitize", "privacy", False, "dmy", [], {
            "doc": {"loc": "doc", "patient": p["patient_id"], "cid": f"{p['patient_id']}#0", "link": "required", "tags": ["rare_trap"],
                    "entities": [
                        _name_ent("PATIENT_NAME", p["full_en"], p["pid"], critical=True),
                        _ent("MRN", p["uhid_a"], p["pid"], match="digits", critical=True),
                        _ent("VILLAGE", p["vil_en"], p["pid"]),
                        _ent("PIN", p["pin"], p["pid"], match="digits_exact"),
                    ],
                    "preserve": [_pres(p["diag_desc"], "diagnosis", 1.0), _pres("Deep brain stimulation", "procedure", 1.0)],
                    "dates": [
                        {"true": adm.isoformat(), "event": "admission", "patient": p["patient_id"], "hint": "dmy"},
                        {"true": dis.isoformat(), "event": "discharge", "patient": p["patient_id"], "hint": "dmy"},
                    ],
                    "fields": [
                        {"kind": "age", "true": p["age"], "path": None, "patient": p["patient_id"]},
                        {"kind": "gender", "true": p["gender"], "path": None, "patient": p["patient_id"]},
                        {"kind": "district", "true": p["dist_key"], "path": None, "patient": p["patient_id"]},
                    ]}
        })
        known_facts.append({"rid": p["rid"], "visit_dates": [adm.isoformat()], "hospital": "Navjeevan Multispeciality Hospital", "condition_hint": p["diag_desc"], "stay_days": stay})

    # ------------------------------------------------------------------
    # 8. 8 CANARIES IN NON-STANDARD CHANNELS
    # ------------------------------------------------------------------
    # C01: base64 inside a JSON array (not an object Attachment)
    c1_b64 = base64.b64encode(f"Witness {ADV_CANARIES[0][1]} tel {ADV_CANARIES[0][2]}".encode()).decode()
    reg("canaries/c01_b64_array.json", json.dumps({"blobs": [c1_b64]}).encode("utf-8"), "json", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [],
                "entities": [_ent("CANARY", ADV_CANARIES[0][1], None, channel="base64", critical=True),
                             _ent("PHONE", ADV_CANARIES[0][2], None, channel="base64", match="digits", critical=True)],
                "preserve": [], "dates": [], "fields": []}
    })
    # C02: JSON key canary
    reg("canaries/c02_json_key.json", json.dumps({ADV_CANARIES[1][1]: {"ext": ADV_CANARIES[1][2]}}).encode("utf-8"), "json", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "@file": {"loc": "@file", "patient": None, "cid": None, "link": "none", "tags": [],
                  "entities": [_ent("CANARY", ADV_CANARIES[1][1], None, channel="key", critical=True),
                               _ent("PHONE", ADV_CANARIES[1][2], None, match="digits", critical=True)],
                  "preserve": [], "dates": [], "fields": []}
    })
    # C03: CSV header canary
    reg("canaries/c03_csv_header.csv", f"time,{ADV_CANARIES[2][1]} {ADV_CANARIES[2][2]}\n08:00,120/80\n".encode("utf-8"), "csv", "utf-8", ",", "sanitize", "canary", False, "dmy", [], {
        "@header": {"loc": "@header", "patient": None, "cid": None, "link": "none", "tags": [],
                    "entities": [_ent("CANARY", ADV_CANARIES[2][1], None, channel="header", critical=True),
                                 _ent("PHONE", ADV_CANARIES[2][2], None, channel="header", match="digits", critical=True)],
                    "preserve": [], "dates": [], "fields": []},
        "row:0": {"loc": "row:0", "patient": None, "cid": None, "link": "none", "tags": [], "entities": [], "preserve": [_pres("120/80", "vital", 1.0)], "dates": [], "fields": []},
    })
    # C04: Filename canary
    reg(f"canaries/memo_{ADV_CANARIES[3][1].replace(' ', '_')}_{ADV_CANARIES[3][2]}.txt", b"Routine ward memo.\n", "text", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "@filename": {"loc": "@filename", "patient": None, "cid": None, "link": "none", "tags": [],
                      "entities": [_ent("CANARY", ADV_CANARIES[3][1].replace(" ", "_"), None, channel="filename", critical=True),
                                   _ent("PHONE", ADV_CANARIES[3][2], None, channel="filename", match="digits", critical=True)],
                      "preserve": [], "dates": [], "fields": []},
        "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [], "entities": [], "preserve": [], "dates": [], "fields": []},
    })
    # C05: \u-escaped JSON string canary
    c5_esc = "".join(f"\\u{ord(ch):04x}" for ch in ADV_CANARIES[4][1])
    reg("canaries/c05_unicode_escape.json", f'{{"reviewer": "{c5_esc}", "callback": "{ADV_CANARIES[4][2]}"}}\n'.encode("utf-8"), "json", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [],
                "entities": [_ent("CANARY", ADV_CANARIES[4][1], None, critical=True),
                             _ent("PHONE", ADV_CANARIES[4][2], None, match="digits", critical=True)],
                "preserve": [], "dates": [], "fields": []}
    })
    # C06: Zero-width obfuscated canary in free text
    c6_zw = "\u200b".join(ADV_CANARIES[5][1].split())
    reg("canaries/c06_zerowidth.txt", f"Called by {c6_zw} on {ADV_CANARIES[5][2]}.\n".encode("utf-8"), "text", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [],
                "entities": [_ent("CANARY", c6_zw, None, critical=True),
                             _ent("PHONE", ADV_CANARIES[5][2], None, match="digits", critical=True)],
                "preserve": [], "dates": [], "fields": []}
    })
    # C07: Accented canary in unlabeled narrative
    reg("canaries/c07_accented.txt", f"{ADV_CANARIES[6][1]} verified the billing slip, tel {ADV_CANARIES[6][2]}.\n".encode("utf-8"), "text", "utf-8", None, "sanitize", "canary", False, "dmy", [], {
        "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [],
                "entities": [_ent("CANARY", ADV_CANARIES[6][1], None, critical=True),
                             _ent("PHONE", ADV_CANARIES[6][2], None, match="digits", critical=True)],
                "preserve": [], "dates": [], "fields": []}
    })
    # C08: Semicolon CSV cell canary
    reg("canaries/c08_semicolon.csv", f"id;notes\n1;contact {ADV_CANARIES[7][1]} {ADV_CANARIES[7][2]}\n".encode("utf-8"), "csv", "utf-8", ";", "sanitize", "canary", False, "dmy", [], {
        "row:0": {"loc": "row:0", "patient": None, "cid": None, "link": "none", "tags": [],
                  "entities": [_ent("CANARY", ADV_CANARIES[7][1], None, critical=True),
                               _ent("PHONE", ADV_CANARIES[7][2], None, match="digits", critical=True)],
                  "preserve": [], "dates": [], "fields": []}
    })

    # ------------------------------------------------------------------
    # 9. IO ROBUSTNESS & MALFORMED TRAPS
    # ------------------------------------------------------------------
    # Ragged semicolon CSV with cp1252 smart quotes
    reg("io_traps/ragged_semicolon_cp1252.csv",
        (
            "id;patient;note\n"
            f"1;{p14['full_en']};“Fever 101°F”\n"
            f"2;{p16['full_en']};extra_col_1;extra_col_2\n"
        ).encode("cp1252"),
        "csv", "cp1252", ";", "either", "io_traps", False, "dmy", [], {
            "row:0": {"loc": "row:0", "patient": p14["patient_id"], "cid": None, "link": "none", "tags": [],
                      "entities": [_name_ent("PATIENT_NAME", p14["full_en"], p14["pid"], critical=True)], "preserve": [], "dates": [], "fields": []},
            "row:1": {"loc": "row:1", "patient": p16["patient_id"], "cid": None, "link": "none", "tags": [],
                      "entities": [_name_ent("PATIENT_NAME", p16["full_en"], p16["pid"], critical=True)], "preserve": [], "dates": [], "fields": []},
        })
    # FHIR Bundle with Binary resource carrying base64 PII
    bin_b64 = base64.b64encode(f"Discharge attachment for {p13['full_en']} ({p13['phone']})".encode()).decode()
    fhir_bin = {
        "resourceType": "Bundle", "id": str(uuid.UUID(int=rng.getrandbits(128))), "type": "collection",
        "entry": [
            {"fullUrl": "urn:uuid:pat-1", "resource": {"resourceType": "Patient", "id": "pat-1", "name": [{"text": p13["full_en"]}], "birthDate": p13["dob"].isoformat()}},
            {"fullUrl": "urn:uuid:bin-1", "resource": {"resourceType": "Binary", "id": "bin-1", "contentType": "text/plain", "data": bin_b64}},
        ],
    }
    reg("io_traps/fhir_binary_resource.json", json.dumps(fhir_bin, indent=2).encode("utf-8"), "fhir", "utf-8", None, "sanitize", "fhir", False, "iso", [], {
        "doc": {"loc": "doc", "patient": p13["patient_id"], "cid": f"{p13['patient_id']}#1", "link": "required", "tags": ["binary_fhir"],
                "entities": [_name_ent("PATIENT_NAME", p13["full_en"], p13["pid"], critical=True),
                             _ent("PHONE", p13["phone"], p13["pid"], channel="base64", match="digits", critical=True),
                             _ent("DOB", p13["dob"].isoformat(), p13["pid"], match="dob", key=p13["dob"].isoformat())],
                "preserve": [], "dates": [], "fields": [{"kind": "dob", "true": p13["dob"].isoformat(), "path": "/entry/0/resource/birthDate", "patient": p13["patient_id"]}]}
    })
    # Malformed / unsupported
    reg("io_traps/empty.json", b"", "json", "utf-8", None, "either", "malformed", False, "dmy", [], {})
    reg("io_traps/mislabeled.tsv", json.dumps({"patient": p14["full_en"], "aadhaar": p14["aadhaar"]}).encode("utf-8"),
        "json", "utf-8", None, "either", "malformed", False, "dmy", [], {
            "@file": {"loc": "@file", "patient": None, "cid": None, "link": "none", "tags": [],
                      "entities": [_name_ent("PATIENT_NAME", p14["full_en"], p14["pid"], critical=True)], "preserve": [], "dates": [], "fields": []}
        })
    reg("io_traps/deep_1500.json", (b'{"k":' * 1500) + json.dumps({"name": p14["full_en"]}).encode() + (b"}" * 1500),
        "json", "utf-8", None, "either", "malformed", False, "dmy", [], {
            "@file": {"loc": "@file", "patient": None, "cid": None, "link": "none", "tags": [],
                      "entities": [_name_ent("PATIENT_NAME", p14["full_en"], p14["pid"], critical=True)], "preserve": [], "dates": [], "fields": []}
        })
    reg("io_traps/corrupt_bytes.txt", f"Note for {p14['full_en']} ".encode() + b"\xff\xfe\xc3\x28\n",
        "text", "utf-8", None, "either", "malformed", False, "dmy", [], {
            "@file": {"loc": "@file", "patient": None, "cid": None, "link": "none", "tags": [],
                      "entities": [_name_ent("PATIENT_NAME", p14["full_en"], p14["pid"], critical=True)], "preserve": [], "dates": [], "fields": []}
        })

    # Clean file (must stay untouched!)
    reg("clean/protocol.txt", b"Dengue NS1 protocol: Platelet < 20000 /uL -> Ward 5. Paracetamol 650 mg QID. Dr. Meera Deshpande.\n",
        "text", "utf-8", None, "sanitize", "clean", True, "dmy", [], {
            "doc": {"loc": "doc", "patient": None, "cid": None, "link": "none", "tags": [], "entities": [],
                    "preserve": [_pres("Paracetamol 650 mg", "medication", 1.0), _pres("Dr. Meera Deshpande", "doctor", 0.5)], "dates": [], "fields": []}
        })

    # ------------------------------------------------------------------
    # WRITE TRUTH, ATTACKER, MANIFEST
    # ------------------------------------------------------------------
    truth_obj = {
        "schema": "raksha-truth/1", "generator_version": "1.0.0", "seed": f"adversarial-{seed}",
        "profile": "adversarial", "chaos": True, "ref_date": REF_DATE.isoformat(), "files": files_truth,
    }
    truth_bytes = json.dumps(truth_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    (truth_dir / "truth.json").write_bytes(truth_bytes)

    reg_buf = io.StringIO()
    rw = csv.writer(reg_buf, lineterminator="\n")
    rw.writerow(["rid", "name", "relation", "relative_name", "gender", "age", "house_no", "mohalla", "village", "tehsil", "district", "pin", "phone", "email", "aadhaar_last4"])
    for p in people:
        rw.writerow([p["rid"], p["full_en"], p["relation"], p["rel_en"], p["gender"], p["age"], p["house_num"], "", p["vil_en"], "", p["dist_en"], p["pin"], p["phone"], p["email"], p["aadhaar"][-4:]])
    reg_bytes = reg_buf.getvalue().encode("utf-8")
    (att_dir / "registry.csv").write_bytes(reg_bytes)

    for dec in people[30:40]:
        known_facts.append({"rid": dec["rid"], "visit_dates": ["2026-06-15"], "hospital": "Navjeevan Multispeciality Hospital", "condition_hint": "Dengue fever"})
    kf_bytes = ("\n".join(json.dumps(x, ensure_ascii=False) for x in known_facts) + "\n").encode("utf-8")
    (att_dir / "known_facts.jsonl").write_bytes(kf_bytes)

    h_in = hashlib.sha256()
    for rel in sorted(files_truth.keys()):
        h_in.update(rel.encode("utf-8"))
        h_in.update(files_truth[rel]["sha256"].encode("utf-8"))
    manifest = {
        "schema": "raksha-dataset/1", "generator_version": "1.0.0", "profile": "adversarial", "chaos": True,
        "seed_sha256": hashlib.sha256(str(seed).encode()).hexdigest(), "ref_date": REF_DATE.isoformat(),
        "counts": {
            "files": len(files_truth),
            "records": sum(len(f["units"]) for f in files_truth.values()),
            "patients": len(patients),
            "population": len(people),
            "required_link_units": sum(1 for f in files_truth.values() for u in f["units"].values() if u.get("link") == "required"),
            "ambiguous_link_units": sum(1 for f in files_truth.values() for u in f["units"].values() if u.get("link") == "ambiguous"),
        },
        "hashes": {"input": h_in.hexdigest(), "truth": hashlib.sha256(truth_bytes).hexdigest(), "attacker": hashlib.sha256(reg_bytes + kf_bytes).hexdigest()},
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--seed", type=int, default=9991337)
    args = ap.parse_args()
    print(json.dumps(generate_adversarial(Path(args.out), args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
