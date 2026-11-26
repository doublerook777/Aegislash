"""Unit tests for aegis.privacy (run with: .venv/Scripts/python -m unittest aegis/privacy/test_privacy.py)."""
from __future__ import annotations

import datetime as dt
import os
import unittest

from aegis.privacy import plan, replace, stats
from aegis.types import empty_evidence


def _rec(rid: str, findings=None, **ev_kw):
    ev = empty_evidence(rid)
    ev.update(ev_kw)
    return {"record_id": rid, "findings": findings or [], "evidence": ev}


class PrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_secret = os.environ.get("RAKSHA_SECRET")
        os.environ["RAKSHA_SECRET"] = "practice-test-secret"

    def tearDown(self) -> None:
        if self._old_secret is None:
            os.environ.pop("RAKSHA_SECRET", None)
        else:
            os.environ["RAKSHA_SECRET"] = self._old_secret

    def test_date_formats_and_interval_preservation(self) -> None:
        r1 = _rec("f1#row:0", dob="1977-04-12")
        r2 = _rec("f2#doc")
        r3 = _rec("f3#doc")  # unlinked
        p = plan([r1, r2, r3], {"f1#row:0": "k:1", "f2#doc": "k:1", "f3#doc": None})

        # DMY and MDY disambiguated via norm
        dmy = replace(p, "f1#row:0", {"path": "col:0", "start": 0, "end": 10, "type": "DOB", "text": "12/04/1977", "norm": "1977-04-12", "role": "patient"})
        self.assertEqual(dmy["status"], "generalized")
        self.assertRegex(dmy["text"], r"^\d{2}/\d{2}/\d{4}$")
        self.assertNotEqual(dmy["text"], "12/04/1977")

        # Ambiguous 02/06/2026 as MDY
        mdy = replace(p, "f1#row:0", {"path": "col:1", "start": 0, "end": 10, "type": "DATE", "text": "02/06/2026", "norm": "2026-02-06", "role": "patient"})
        # Interval between two dates for same patient stays exact
        adm = replace(p, "f1#row:0", {"path": "col:2", "start": 0, "end": 10, "type": "DATE", "text": "2026-02-01", "norm": "2026-02-01", "role": "patient"})
        dis = replace(p, "f2#doc", {"path": "text", "start": 0, "end": 10, "type": "DATE", "text": "2026-02-10", "norm": "2026-02-10", "role": "patient"})
        d_adm = dt.date.fromisoformat(adm["text"])
        d_dis = dt.date.fromisoformat(dis["text"])
        d_mdy = dt.datetime.strptime(mdy["text"], "%m/%d/%Y").date()
        self.assertEqual((d_dis - d_adm).days, 9)
        self.assertEqual((d_mdy - d_adm).days, 5)

        # ISO datetime with timezone suffix preserved
        iso_dt = replace(p, "f2#doc", {"path": "/p/s", "start": 0, "end": 25, "type": "DATE", "text": "2026-02-04T18:15:00+05:30", "norm": "2026-02-04", "role": "patient"})
        self.assertTrue(iso_dt["text"].endswith("T18:15:00+05:30"))

        # Numeric with time & month-name & Devanagari digits
        num_t = replace(p, "f2#doc", {"path": "text", "start": 0, "end": 16, "type": "DATE", "text": "01/13/2026 22:00", "norm": "2026-01-13", "role": "patient"})
        self.assertTrue(num_t["text"].endswith(" 22:00"))
        mon = replace(p, "f2#doc", {"path": "text", "start": 0, "end": 11, "type": "DATE", "text": "13-Jan-2026", "norm": "2026-01-13", "role": "patient"})
        self.assertRegex(mon["text"], r"^\d{2}-[A-Z][a-z]{2}-\d{4}$")
        deva = replace(p, "f3#doc", {"path": "col:4", "start": 0, "end": 10, "type": "DOB", "text": "२९-०७-१९७८", "norm": "1978-07-29", "role": "patient"})
        self.assertRegex(deva["text"], r"^[०-९]{2}-[०-९]{2}-[०-९]{4}$")

        # Unparseable date fails closed
        bad = replace(p, "f3#doc", {"path": "text", "start": 0, "end": 9, "type": "DATE", "text": "last week", "norm": None, "role": "patient"})
        self.assertEqual(bad, {"text": "[DATE]", "status": "suppressed"})

    def test_cross_release_unlinkability_and_determinism(self) -> None:
        r1 = _rec("a#row:0")
        r2 = _rec("b#doc")
        p1 = plan([r1, r2], {"a#row:0": "k:99", "b#doc": "k:99"})
        p1_rev = plan([r2, r1], {"b#doc": "k:99", "a#row:0": "k:99"})
        f_dob = {"path": "col:0", "start": 0, "end": 10, "type": "DOB", "text": "12/04/1977", "norm": "1977-04-12", "role": "patient"}
        f_name = {"path": "col:1", "start": 0, "end": 6, "type": "PATIENT_NAME", "text": "Shahid", "norm": "shahid", "role": "patient"}
        self.assertEqual(replace(p1, "a#row:0", f_dob), replace(p1_rev, "a#row:0", f_dob))

        os.environ["RAKSHA_SECRET"] = "different-secret"
        p2 = plan([r1, r2], {"a#row:0": "k:99", "b#doc": "k:99"})
        self.assertNotEqual(replace(p1, "a#row:0", f_dob), replace(p2, "a#row:0", f_dob))
        self.assertNotEqual(replace(p1, "a#row:0", f_name), replace(p2, "a#row:0", f_name))

    def test_ages_pins_villages_and_direct_identifiers(self) -> None:
        r1 = _rec("r1#row:0", district="rae bareli")
        r2 = _rec("r2#doc")
        p = plan([r1, r2], {"r1#row:0": "k:1", "r2#doc": None})

        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 2, "type": "AGE", "text": "48", "norm": "48", "role": "patient"}), {"text": "45-49", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 4, "type": "AGE", "text": "48/M", "norm": "48", "role": "patient"}), {"text": "45-49/M", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 8, "type": "AGE", "text": "46 Yrs/F", "norm": "46", "role": "patient"}), {"text": "45-49 Yrs/F", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 7, "type": "AGE", "text": "47 वर्ष", "norm": "47", "role": "patient"}), {"text": "45-49 वर्ष", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 2, "type": "AGE", "text": "97", "norm": "97", "role": "patient"}), {"text": "85+", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 7, "type": "AGE", "text": "-2 वर्ष", "norm": "-2", "role": "patient"}), {"text": "[AGE]", "status": "suppressed"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 7, "type": "AGE", "text": "Age: 48", "norm": "48", "role": "patient"}), {"text": "Age: 45-49", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 12, "type": "AGE", "text": "उम्र: ४७ वर्ष", "norm": None, "role": "patient"}), {"text": "उम्र: 45-49 वर्ष", "status": "generalized"})

        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 6, "type": "PIN", "text": "229073", "norm": "229073", "role": "patient"}), {"text": "229***", "status": "generalized"})
        self.assertEqual(replace(p, "r1#row:0", {"path": "c", "start": 0, "end": 8, "type": "VILLAGE", "text": "Durgamau", "norm": "durgamau", "role": "patient"}), {"text": "Rae Bareli", "status": "generalized"})
        self.assertEqual(replace(p, "r2#doc", {"path": "c", "start": 0, "end": 8, "type": "VILLAGE", "text": "Durgamau", "norm": "durgamau", "role": "patient"}), {"text": "[VILLAGE]", "status": "suppressed"})

        # Unlinked PATIENT_NAME / MRN -> placeholders
        self.assertEqual(replace(p, "r2#doc", {"path": "c", "start": 0, "end": 6, "type": "PATIENT_NAME", "text": "Shahid", "norm": "shahid", "role": "patient"}), {"text": "[PATIENT]", "status": "sanitized"})
        self.assertEqual(replace(p, "r2#doc", {"path": "c", "start": 0, "end": 5, "type": "MRN", "text": "12345", "norm": "12345", "role": "patient"}), {"text": "[MRN]", "status": "sanitized"})
        self.assertEqual(replace(p, "r2#doc", {"path": "c", "start": 0, "end": 6, "type": "RELATIVE_NAME", "text": "Zubair", "norm": "zubair", "role": "relative"}), {"text": "[RELATIVE]", "status": "sanitized"})

    def test_k_anonymity_and_rare_condition_suppression(self) -> None:
        # 10 common patients in one cell (45-49, M, lucknow, fever) + 1 rare elderly patient
        results = []
        keys = {}
        for i in range(10):
            rid = f"common.csv#row:{i}"
            f_cond = {"path": "col:2", "start": 0, "end": 5, "type": "CONDITION", "text": "Fever", "norm": "fever", "role": None}
            f_age = {"path": "col:0", "start": 0, "end": 2, "type": "AGE", "text": "47", "norm": "47", "role": "patient"}
            f_pin = {"path": "col:1", "start": 0, "end": 6, "type": "PIN", "text": "226001", "norm": "226001", "role": "patient"}
            results.append(_rec(rid, [f_age, f_pin, f_cond], age=47, gender="M", district="lucknow"))
            keys[rid] = f"k:{i}"

        rare_rid = "rare.csv#row:0"
        rare_age = {"path": "col:0", "start": 0, "end": 2, "type": "AGE", "text": "97", "norm": "97", "role": "patient"}
        rare_pin = {"path": "col:1", "start": 0, "end": 6, "type": "PIN", "text": "271001", "norm": "271001", "role": "patient"}
        rare_vil = {"path": "col:2", "start": 0, "end": 7, "type": "VILLAGE", "text": "Amardih", "norm": "amardih", "role": "patient"}
        rare_dist = {"path": "col:3", "start": 0, "end": 8, "type": "DISTRICT", "text": "Bahraich", "norm": "bahraich", "role": "patient"}
        rare_cond = {"path": "col:4", "start": 0, "end": 16, "type": "CONDITION", "text": "Addison disease", "norm": "addison disease", "role": None}
        results.append(_rec(rare_rid, [rare_age, rare_pin, rare_vil, rare_dist, rare_cond], age=97, gender="F", district="bahraich"))
        keys[rare_rid] = "k:rare"

        p = plan(results, keys)
        # Common cell stays normal (5-yr band, PIN prefix)
        self.assertEqual(replace(p, "common.csv#row:0", results[0]["findings"][0])["text"], "45-49")
        self.assertEqual(replace(p, "common.csv#row:0", results[0]["findings"][1])["text"], "226***")
        # Rare cell suppresses PIN, VILLAGE, DISTRICT, widens/top-codes AGE, preserves CONDITION
        self.assertEqual(replace(p, rare_rid, rare_age)["text"], "80+")
        self.assertEqual(replace(p, rare_rid, rare_pin), {"text": "[PIN]", "status": "suppressed"})
        self.assertEqual(replace(p, rare_rid, rare_vil), {"text": "[VILLAGE]", "status": "suppressed"})
        self.assertEqual(replace(p, rare_rid, rare_dist), {"text": "[DISTRICT]", "status": "suppressed"})
        self.assertEqual(replace(p, rare_rid, rare_cond), {"text": None, "status": "sanitized"})

        st = stats(p)
        self.assertEqual(st["records_generalized"], 10)
        self.assertEqual(st["records_suppressed"], 1)

    def test_risk_report_on_synthetic_release(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        from scripts.risk_report import analyze_release

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "sanitized").mkdir()
            (out / "sanitized" / "p.csv").write_text(
                "patient;age;gender;district;visit_date;diagnosis\n"
                "PSN-AAAAAA;45-49;M;Lucknow;2026-03-01;Viral fever\n"
                "PSN-BBBBBB;45-49;M;Lucknow;2026-03-02;Viral fever\n",
                encoding="utf-8",
            )
            (out / "sanitized" / "arr.json").write_text(
                json.dumps([
                    {"patient": "PSN-CCCCCC", "age": "45-49", "gender": "M", "district": "Lucknow", "diagnosis": "Viral fever"},
                    {"patient": "PSN-DDDDDD", "age": "45-49", "gender": "M", "district": "Lucknow", "diagnosis": "Viral fever"},
                ]),
                encoding="utf-8",
            )
            (out / "sanitized" / "esc.json").write_text(
                json.dumps({"visit/log": [{"patient": "PSN-EEEEEE", "age": "45-49", "gender": "M", "district": "Lucknow", "diagnosis": "Rare Addison"}]}),
                encoding="utf-8",
            )
            (out / "records.jsonl").write_text(
                json.dumps({"file": "sanitized/p.csv", "loc": "row:0", "patient": "PSN-AAAAAA"}) + "\n"
                + json.dumps({"file": "sanitized/p.csv", "loc": "row:1", "patient": "PSN-BBBBBB"}) + "\n"
                + json.dumps({"file": "sanitized/arr.json", "loc": "/0", "patient": "PSN-CCCCCC"}) + "\n"
                + json.dumps({"file": "sanitized/arr.json", "loc": "/1", "patient": "PSN-DDDDDD"}) + "\n"
                + json.dumps({"file": "sanitized/esc.json", "loc": "/visit~1log/0", "patient": "PSN-EEEEEE"}) + "\n",
                encoding="utf-8",
            )
            kf = out / "kf.jsonl"
            kf.write_text(
                json.dumps({"rid": "R1", "visit_dates": ["2026-03-01"], "condition_hint": "Fever"}) + "\n"
                + json.dumps({"rid": "R2", "visit_dates": [], "condition_hint": "Rare Addison"}) + "\n",
                encoding="utf-8",
            )
            rep = analyze_release(out, known_facts_path=kf)
            self.assertEqual(rep["linked_psn_profiles"], 5)
            self.assertEqual(rep["k_anon_age_gender_district"]["min_k"], 5)
            # "Fever" matches 4 "Viral fever" profiles -> not rare; only "Rare Addison" (1 profile) hits
            self.assertEqual(rep["simulated_known_facts_attack"]["rare_cond_with_narrow_qi_hits"], 1)
            self.assertEqual(rep["simulated_known_facts_attack"]["exact_date_overlap_hits"], 1)

    def test_at_file_records_excluded_from_profiles_and_stats(self) -> None:
        # 8 real records (< 10 threshold) + 4 #@file records must NOT trigger k-anonymity suppression,
        # and @file findings must not inflate stats(), yet replace() must still work for @file.
        results = []
        keys = {}
        for i in range(4):
            f_rec = _rec(
                f"f{i}.csv#@file",
                [{"path": "filename", "start": 0, "end": 6, "type": "PIN", "text": "226001", "norm": "226001", "role": None}],
            )
            results.append(f_rec)
        for i in range(8):
            rid = f"f{i % 4}.csv#row:{i}"
            pin_f = {"path": "col:0", "start": 0, "end": 6, "type": "PIN", "text": "226001", "norm": "226001", "role": "patient"}
            results.append(_rec(rid, [pin_f], age=47, gender="M", district="lucknow"))
            keys[rid] = f"k:{i}"

        p = plan(results, keys)
        self.assertEqual(replace(p, "f0.csv#@file", results[0]["findings"][0]), {"text": "226***", "status": "generalized"})
        self.assertEqual(replace(p, "f0.csv#row:0", results[4]["findings"][0]), {"text": "226***", "status": "generalized"})
        st = stats(p)
        self.assertEqual(st["records_generalized"], 8)
        self.assertEqual(st["records_suppressed"], 0)


if __name__ == "__main__":
    unittest.main()
