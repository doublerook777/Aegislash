"""Unit and end-to-end tests for aegis.io (JSON Lines, base64 layouts, base64 file names, leak gate).

All names, numbers and files are invented. Run: .venv/bin/python -m pytest -q aegis/io
"""
from __future__ import annotations

import base64
import json
import re

import pytest

from aegis.io import formats
from aegis.io.leakgate import LeakGate
from aegis.io.pipeline import run

SECRET = "unit-test-secret"


def _b64(text: str, width: int = 0, newline: str = "\n") -> str:
    raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return newline.join(raw[i:i + width] for i in range(0, len(raw), width)) if width else raw


def _sanitize(tmp_path, monkeypatch, files: dict[str, str | bytes]):
    monkeypatch.setenv("RAKSHA_SECRET", SECRET)
    inp, out = tmp_path / "in", tmp_path / "out"
    for rel, content in files.items():
        p = inp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    assert run(inp, out) == 0
    return out, json.loads((out / "report.json").read_text(encoding="utf-8"))


def _outputs(out) -> dict[str, str]:
    return {p.relative_to(out / "sanitized").as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((out / "sanitized").rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- JSON Lines inside .csv
JSONL = ('{"patient": "Kavya Rastogi", "phone": "9811100021", "dx": "Anemia", "hb": "8.1 g/dL"}\n'
         '{"patient": "Tarun Kulkarni", "phone": "9811100022", "dx": "Asthma", "fev1": "71 %"}\n'
         '\n'
         '{"patient": "Meenal Dasgupta", "phone": "9811100023", "dx": "Hypertension", "bp": "150/94"}\n')


def test_json_lines_are_one_record_per_line():
    pf = formats.parse("lab/export.csv", JSONL)
    assert pf.jsonl and pf.fmt == "json"
    assert [r["loc"] for r in pf.records] == ["@file", "row:0", "row:1", "row:2"]
    assert {f["context"] for f in pf.records[1]["fields"] if f["kind"] == "value"} == {"patient", "phone", "dx", "hb"}


def test_json_lines_round_trip_keeps_one_object_per_line():
    pf = formats.parse("lab/export.csv", JSONL)
    out = formats.write(pf, {("lab/export.csv#row:1", "/1/patient"): "[PATIENT]"})
    lines = out.splitlines()
    assert len(lines) == 3 and all(json.loads(x) for x in lines)
    assert json.loads(lines[1])["patient"] == "[PATIENT]" and json.loads(lines[0])["patient"] == "Kavya Rastogi"


@pytest.mark.parametrize("rel", ["a.csv", "a.tsv"])
def test_table_that_starts_like_json_lines_but_is_not_is_quarantined(rel):
    bad = '{"patient": "Kavya Rastogi"}\n{"patient": "Tarun Kulkarni"\nsecond,third\n'
    with pytest.raises(formats.Unsupported):
        formats.parse(rel, bad)


def test_text_file_with_a_json_looking_first_line_stays_text():
    assert formats.parse("a.txt", '{"a": 1}\nfree text follows\n').fmt == "text"


def test_one_line_json_and_pretty_json_are_unchanged():
    assert not formats.parse("a.csv", '{"patient": "Kavya Rastogi"}').jsonl
    assert not formats.parse("a.csv", '{\n "patient": "Kavya Rastogi"\n}\n').jsonl


# ---------------------------------------------------------------- base64 layouts
BODY = "Consent by Kavya Rastogi, mobile 9811100021, MRN KGMU/26/55102"


@pytest.mark.parametrize("value", [
    _b64(BODY),                                        # one line
    "data:text/plain;base64," + _b64(BODY),            # data URI
    _b64(BODY, 32),                                    # wrapped, \n
    _b64(BODY, 20, "\r\n") + "\r\n",                   # wrapped, \r\n, final newline
    "data:text/plain;charset=utf-8;base64," + _b64(BODY, 24),
    "data:text/plain;base64," + _b64(BODY).rstrip("="),  # prefix: padding may be missing
])
def test_base64_layouts_are_decoded_and_written_back_the_same_way(value):
    hit = formats._b64_decode(value)
    assert hit is not None and hit[0] == BODY
    text, form = hit
    again = formats._b64_encode(text, form)
    assert again == value
    assert formats._b64_decode(formats._b64_encode("[PATIENT] mobile [PHONE]", form))[0] == "[PATIENT] mobile [PHONE]"


@pytest.mark.parametrize("value", [
    "Hypertension, Diabetes and Anaemia noted",       # words
    "ABCDEFGHIJKLMNOPQRSTUVWX" * 2,                     # letters only, not text when decoded
    "data:image/png;base64," + base64.b64encode(bytes(range(256))).decode(),   # binary
    _b64(BODY)[:30],                                   # cut mid-way (length not a multiple of 4)
    "line one is text\nline two is text too, long enough",
    "A" * 12 + "\n" + "B" * 7 + "\n" + "C" * 12,       # lines of different widths
])
def test_values_that_are_not_base64_text_are_left_alone(value):
    assert formats._b64_decode(value) is None


def test_json_leaf_with_wrapped_base64_is_sanitized_and_still_valid(tmp_path, monkeypatch):
    doc = {"kind": "referral", "blob": _b64("Referral for Meenal Dasgupta, Phone 9811100023, MRN KGMU/26/99104", 32),
           "uri": "data:text/plain;base64," + _b64("Aadhaar 4567 8901 2345 of Tarun Kulkarni"),
           "note": "Cholecystectomy planned"}
    out, _ = _sanitize(tmp_path, monkeypatch, {"att/consent.json": json.dumps(doc)})
    written = json.loads(_outputs(out)["att/consent.json"])
    blob = written["blob"]
    assert "\n" in blob and set(blob.replace("\n", "")) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    decoded = base64.b64decode(blob.replace("\n", "")).decode()
    assert "Meenal" not in decoded and "9811100023" not in decoded and "99104" not in decoded
    uri = written["uri"]
    assert uri.startswith("data:text/plain;base64,")
    assert "4567" not in base64.b64decode(uri.split(",", 1)[1]).decode() and "Kulkarni" not in base64.b64decode(uri.split(",", 1)[1]).decode()
    assert written["note"] == "Cholecystectomy planned"


# ---------------------------------------------------------------- base64 file names
@pytest.mark.parametrize("stem", ["Pranav Deshmukh_9691246176", "Zoya Qureshi 9811100024 discharge"])
def test_base64_file_name_is_decoded_even_without_padding(stem):
    name = base64.b64encode(stem.encode()).decode().rstrip("=") + ".txt"
    assert formats._b64_filename(name) == stem + ".txt"
    url_safe = base64.urlsafe_b64encode(stem.encode()).decode().rstrip("=") + ".json"
    assert formats._b64_filename(url_safe) == stem + ".json"


@pytest.mark.parametrize("name", ["dischargesummary2024.txt", "ward_3-medicine-round_notes.txt", "labreport.csv",
                                  "short.txt", "lab_Meenal_Dasgupta_note.txt"])
def test_ordinary_file_names_are_not_decoded(name):
    assert formats._b64_filename(name) is None


def test_base64_file_name_end_to_end(tmp_path, monkeypatch):
    name = base64.b64encode(b"Pranav Deshmukh_9691246176").decode().rstrip("=") + ".txt"
    out, report = _sanitize(tmp_path, monkeypatch, {f"hidden/{name}": "Stable on discharge. Follow up in 1 week.\n"})
    names = list(_outputs(out))
    assert names and all("Deshmukh" not in n and "9691246176" not in n and not n.startswith("hidden/UHJh") for n in names)
    assert _outputs(out)[names[0]].startswith("Stable on discharge")


# ---------------------------------------------------------------- leak gate
def test_gate_learns_names_joined_by_underscore_and_in_both_orders():
    g = LeakGate()
    g.add("PATIENT_NAME", "Agustín_Fonseca", None)       # a file name
    g.add("PATIENT_NAME", "Quispe, Mariela", None)       # surname first
    g.finalize()
    assert "[REDACTED]" in g.scrub("Follow up with Agustín Fonseca at 10 am.")
    assert "Agust" not in g.scrub("Follow up with Agustín Fonseca at 10 am.")
    assert "Mariela" not in g.scrub("Seen: Mariela Quispe today") and "Quispe" not in g.scrub("Seen: Quispe, Mariela today")
    assert g.scrub("Seen by Mariela on rounds.") == "Seen by Mariela on rounds."     # one word alone is not enough


def test_gate_reads_escaped_separators():
    g = LeakGate()
    g.add("PATIENT_NAME", "Hector Pereira", None)
    g.add("PHONE", "9811100025", "9811100025")
    g.finalize()
    s = g.scrub("view?patient=Hector%20Pereira&tel=%2B91%209811100025")
    assert "Pereira" not in s and "9811100025" not in s and s.startswith("view?patient=")
    assert g.contains_leak("a=Hector%5CPereira") and not g.contains_leak("a=Hector%41Pereira")


# ---------------------------------------------------------------- the whole pipeline
def test_jsonl_in_csv_end_to_end(tmp_path, monkeypatch):
    out, report = _sanitize(tmp_path, monkeypatch, {"lab/stream.csv": JSONL})
    text = _outputs(out)["lab/stream.csv"]
    for gone in ("Kavya", "Rastogi", "Tarun", "Kulkarni", "Meenal", "Dasgupta", "9811100021", "9811100022", "9811100023"):
        assert gone not in text
    for kept in ("Anemia", "8.1 g/dL", "Asthma", "71 %", "Hypertension", "150/94"):
        assert kept in text
    assert all(json.loads(x) for x in text.splitlines()) and len(text.splitlines()) == 3
    rows = [json.loads(x) for x in (out / "records.jsonl").read_text().splitlines()]
    assert [r["loc"] for r in rows] == ["row:0", "row:1", "row:2"]


def test_url_escapes_end_to_end(tmp_path, monkeypatch):
    note = ("Attachment URI: file:///D%3A%5CHIS%5CRukhsana_Bhattacharya%5Cdischarge_9811100026.pdf\n"
            "Link: https://portal.example/view?patient=Priyanka%20Sengupta&tel=%2B91%209811100027\n"
            "Rx Tab Levodopa 100mg 1-0-1, BP 134/82, SpO2 96%, 5%DEXTROSE drip.\n")
    out, _ = _sanitize(tmp_path, monkeypatch, {"notes/n.txt": note})
    text = _outputs(out)["notes/n.txt"]
    for gone in ("Rukhsana", "Bhattacharya", "Priyanka", "Sengupta", "9811100026", "9811100027"):
        assert gone not in text
    for kept in ("Levodopa 100mg 1-0-1", "BP 134/82", "SpO2 96%", "5%DEXTROSE", "discharge_", ".pdf", "https://portal.example/view?patient="):
        assert kept in text


def test_name_learned_in_one_file_is_removed_from_another_in_any_form(tmp_path, monkeypatch):
    out, _ = _sanitize(tmp_path, monkeypatch, {
        "a/Mariela_Quispe_9811100028.txt": "Routine OPD checkup complete. Paracetamol 650 mg SOS.\n",
        "b/handover.txt": "Follow up with Pema Tsering and Mariela Quispe at 10 am.\n",
    })
    for text in _outputs(out).values():
        assert "Quispe" not in text and "Mariela" not in text
    assert all("Quispe" not in n for n in _outputs(out))


# ---------------------------------------------------------------- binary files, deep JSON, metadata keys, doctors
from aegis.io.decode import decode  # noqa: E402


def test_nul_byte_anywhere_means_binary_but_utf16_is_still_text():
    text = "Progress note: stable vitals, BP 118/76. " * 150           # well past 4,096 bytes
    assert decode((text + "\n").encode()) is not None
    assert decode((text + "\n\x00\x00PK\x03\x04BINARY").encode("latin-1")) is None          # trailer after 4 KB
    assert decode(b"short note\x00more") is None
    assert decode("Brief note, no NUL".encode("utf-16")) is not None                         # BOM
    assert decode("Brief note, no NUL".encode("utf-16-le")) is not None                      # no BOM
    assert decode(("café " * 2000).encode("cp1252")) is not None


def test_binary_trailer_file_is_quarantined_end_to_end(tmp_path, monkeypatch):
    note = "Clinical note for Kavya Rastogi, phone 9811100029. " * 100 + "\x00\x00PK\x03\x04TRAILER"
    out, report = _sanitize(tmp_path, monkeypatch, {"notes/late.txt": note.encode("latin-1"),
                                                    "notes/fine.txt": "BP 118/76, Tab Aspirin 75 mg.\n"})
    assert list(_outputs(out)) == ["notes/fine.txt"]
    assert [e.get("reason") for e in report["files"] if e["status"] == "quarantined"] == ["undecodable_text"]


def _nested(depth: int, leaf) -> str:
    return '{"level":' * (depth - 1) + json.dumps(leaf) + "}" * (depth - 1)


@pytest.mark.parametrize("depth, ok", [(50, True), (950, True), (1000, True), (1001, False), (1500, False)])
def test_json_depth_cap(depth, ok):
    text = _nested(depth, {"patient": "Kavya Rastogi", "mobile": "9811100030"})
    if ok:
        assert formats.parse("a.json", text).fmt == "json"
    else:
        with pytest.raises(formats.Unsupported, match="json_too_deep"):
            formats.parse("a.json", text)


def test_deep_json_lines_are_quarantined_too():
    line = _nested(1200, "x")
    with pytest.raises(formats.Unsupported, match="json_too_deep"):
        formats.parse("a.csv", line + "\n" + line + "\n")


def test_deep_json_is_written_without_a_size_explosion_and_shallow_json_is_not_changed(tmp_path, monkeypatch):
    deep = _nested(900, {"patient": "Kavya Rastogi", "mobile": "9811100030", "dx": "Anemia"})
    shallow = json.dumps({"patient": "Tarun Kulkarni", "mobile": "9811100031", "dx": "Asthma"})
    out, _ = _sanitize(tmp_path, monkeypatch, {"x/deep.json": deep, "x/shallow.json": shallow})
    files = _outputs(out)
    assert len(files["x/deep.json"]) < 10 * len(deep) and "Rastogi" not in files["x/deep.json"] and "Anemia" in files["x/deep.json"]
    assert files["x/shallow.json"].startswith('{\n  "patient"')           # indent=2 as before


def test_export_metadata_key_does_not_collapse_a_list_of_patients():
    doc = {"patient_export_source": "HIS-Lucknow-Ward-3", "export_date": "2026-07-11",
           "visits": [{"patient_name": "Kavya Rastogi", "mobile": "9811100032"},
                      {"patient_name": "Tarun Kulkarni", "mobile": "9811100033"},
                      {"patient_name": "Meenal Dasgupta", "mobile": "9811100034"}]}
    pf = formats.parse("reg/wrapped.json", json.dumps(doc))
    assert [r["loc"] for r in pf.records] == ["@file", "/visits/0", "/visits/1", "/visits/2"] and pf.doc_record_id is None
    for key, value in (("patient_count", 3), ("patientTotal", 812), ("patient_source", "HIS-2"),
                       ("patient_export_version", "v2.1"), ("patient_batch", "B07")):
        assert formats._describes_export(key, value)
    one = {"patient_name": "Kavya Rastogi", "visits": [{"patient_name": "Kavya Rastogi", "mobile": "9811100032"}]}
    assert formats.parse("reg/one.json", json.dumps(one)).doc_record_id is not None      # a subject of its own: one document


@pytest.mark.parametrize("key, value", [
    ("batch_patient_name", "Imkong Walling"), ("source_patient_name", "Imkong Walling"), ("export_name", "Imkong Walling"),
    ("sourcePatientName", "Imkong"), ("patient_name_source", "Imkong_Walling"), ("patient_source", "Walling"),
    ("uhid_source", "KGMU/26/55102"), ("mobile_source", "9811100031"), ("mobile_batch", 9811100031),
    ("patient_source", {"name": "Imkong Walling"}),
])
def test_a_patient_field_with_an_export_word_is_still_the_subject(key, value):
    assert not formats._describes_export(key, value)
    doc = {key: value, "visits": [{"mrn": "KGMU/26/55102", "note": "Review"}]}
    assert formats.parse("reg/one.json", json.dumps(doc)).doc_record_id is not None


@pytest.mark.parametrize("key", ["batch_patient_name", "source_patient_name", "export_name"])
def test_subject_beside_visits_leaves_no_part_of_the_name_in_the_notes(tmp_path, monkeypatch, key):
    doc = {key: "Imkong Walling", "visits": [{"mrn": "KGMU/26/55102", "note": "Walling reports less fever. Hb 9.1 g/dL"},
                                             {"mrn": "KGMU/26/55102", "note": "Imkong doing well."}]}
    out, _ = _sanitize(tmp_path, monkeypatch, {"reg/one.json": json.dumps(doc)})
    text = _outputs(out)["reg/one.json"]
    assert "Walling" not in text and "Imkong" not in text and "Hb 9.1 g/dL" in text


@pytest.mark.parametrize("key", ["batch_patient_name", "source_patient_name", "export_name"])
def test_a_list_of_people_keyed_with_export_words_still_splits(key):
    doc = [{key: "Kavya Rastogi", "dx": "Anemia"}, {key: "Tarun Kulkarni", "dx": "Asthma"}]
    assert [r["loc"] for r in formats.parse("reg/list.json", json.dumps(doc)).records] == ["@file", "/0", "/1"]


def test_gate_keeps_the_doctor_but_removes_the_patient_with_the_same_name():
    g = LeakGate()
    g.add("PATIENT_NAME", "Suresh Pandey", None)
    g.finalize()
    s = g.scrub("Dr. Suresh Pandey examined Suresh Pandey (45/M). Dr R. Suresh Pandey signed. डॉ. Suresh Pandey. Prof Suresh Pandey.")
    assert s.count("Suresh Pandey") == 4 and s.count("[REDACTED]") == 1 and "examined [REDACTED] (45/M)" in s
    assert not g.contains_leak("Dr. Suresh Pandey reviewed the chart") and g.contains_leak("Mr Suresh Pandey reviewed the chart")


def test_doctor_with_a_patient_name_end_to_end(tmp_path, monkeypatch):
    out, _ = _sanitize(tmp_path, monkeypatch, {
        "reg/people.csv": "patient_name,age,dx\nSuresh Pandey,45,Parkinson's disease\n",
        "notes/n.txt": "Dr. Suresh Pandey examined Suresh Pandey (45/M) and diagnosed Parkinson's disease.\n"})
    note = _outputs(out)["notes/n.txt"]
    assert note.startswith("Dr. Suresh Pandey examined ") and note.count("Pandey") == 1 and "Parkinson's disease" in note


# ---------------------------------------------------------------- hidden payloads inside cells and running text
HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAHyJ4MQAAAABJRU5ErkJggg=="
_B64_CHARS = re.compile(r"[A-Za-z0-9+/=]{16,}")


def _decoded_runs(text: str) -> list[str]:
    return [dec for _a, _b, dec, _f in formats.find_runs(text)]


def _decode_all(text: str) -> str:
    """Every base64-looking piece of `text` that decodes to UTF-8, joined (to check nothing is left inside)."""
    out = []
    for piece in _B64_CHARS.findall(text):
        try:
            out.append(base64.b64decode(piece + "=" * (-len(piece) % 4)).decode("utf-8"))
        except ValueError:
            pass
    return "\n".join(out)


def test_find_runs_reads_text_and_leaves_noise():
    payload = _b64("patient=Rukmini Deshmukh;phone=9811100031")
    assert _decoded_runs(f"ref {payload} end") == ["patient=Rukmini Deshmukh;phone=9811100031"]
    assert _decoded_runs(f"x?q={payload}&y=1") == ["patient=Rukmini Deshmukh;phone=9811100031"]
    uri = "data:text/plain;base64," + _b64("Contact Gulab Chaudhry on 9811100032")
    assert _decoded_runs(f"see {uri} now") == ["Contact Gulab Chaudhry on 9811100032"]
    for noise in (HASH, PNG, "TXN8F3K2Q9ZL4M7W1B6C", "Hydroxychloroquine", "Tab Paracetamol 650 mg", "ABCDEFGHIJKLMNOP",
                  "1234567890123456", "https://portal.example/files/discharge/summary/2024", "9811100031" * 3):
        assert _decoded_runs(noise) == [], noise


def test_runs_round_trip_unchanged_and_changed():
    payload = _b64("patient=Rukmini Deshmukh;phone=9811100031")
    csv_text = f"id,blob,rx\nV1,{payload},Tab Cefixime 200 mg BD\n"
    pf = formats.parse("a/x.csv", csv_text)
    assert formats.write(pf, {}) == csv_text
    kid = [f for f in pf.records[1]["fields"] if "#b64:" in f["path"]]
    assert len(kid) == 1 and kid[0]["value"].startswith("patient=Rukmini")
    out = formats.write(pf, {(pf.records[1]["record_id"], kid[0]["path"]): "patient=[PATIENT];phone=[PHONE]"})
    cell = out.splitlines()[1].split(",")[1]
    assert base64.b64decode(cell).decode() == "patient=[PATIENT];phone=[PHONE]"
    note = f"line one\nattached {payload} thanks\n"
    pf = formats.parse("n/a.txt", note)
    assert formats.write(pf, {}) == note


def test_base64_cell_end_to_end(tmp_path, monkeypatch):
    csv_text = ("visit_id,blob,note,treatment\n"
                f"V9001,{_b64('name=Rukmini Deshmukh;mobile=9811100031')},sample id {HASH},Tab Cefixime 200 mg BD x 5 days\n"
                f"V9002,{_b64('Tab Cefixime 200 mg BD for 5 days')},image {PNG},Syp Ambroxol 5 ml TDS\n")
    out, _ = _sanitize(tmp_path, monkeypatch, {"exports/blobs.csv": csv_text})
    text = _outputs(out)["exports/blobs.csv"]
    rows = text.splitlines()
    inside = base64.b64decode(rows[1].split(",")[1]).decode()
    assert "Rukmini" not in text and "9811100031" not in text and "Rukmini" not in inside and "9811100031" not in inside
    assert inside.startswith("name=")
    # untouched: a clinical note inside base64, a hash, a binary image, the medical text
    assert _b64("Tab Cefixime 200 mg BD for 5 days") in rows[2] and HASH in rows[1] and PNG in rows[2]
    for kept in ("Tab Cefixime 200 mg BD x 5 days", "Syp Ambroxol 5 ml TDS"):
        assert kept in text


def test_data_uri_inside_a_sentence_and_wrapped_run(tmp_path, monkeypatch):
    uri = "data:text/plain;base64," + _b64("Patient: Gulab Chaudhry, mobile 9811100032")
    wrapped = _b64("Relative Meenakshi Pillai can be reached on 9811100033 after noon", width=20)
    note = (f"Scan attached ({uri}) please review. Rx Tab Metformin 500 mg BD, BP 128/82.\n"
            f"Forwarded block:\n{wrapped}\nEnd of block. SpO2 97%.\n")
    out, _ = _sanitize(tmp_path, monkeypatch, {"notes/fwd.txt": note})
    text = _outputs(out)["notes/fwd.txt"]
    seen = text + "\n" + _decode_all(text)
    for gone in ("Gulab", "Chaudhry", "9811100032", "Meenakshi", "Pillai", "9811100033"):
        assert gone not in seen
    assert "data:text/plain;base64," in text and "Patient:" in seen
    for kept in ("Rx Tab Metformin 500 mg BD, BP 128/82.", "Forwarded block:", "SpO2 97%."):
        assert kept in text


def test_escapes_in_text_are_read(tmp_path, monkeypatch):
    bs = chr(92)
    esc = "".join(f"{bs}u{ord(c):04x}" for c in "Hemant Joshi")
    csv_text = ("visit_id,remarks,treatment\n"
                f"V9101,Attendant: {esc} came with patient,Tab Telmisartan 40 mg OD\n"
                "V9102,Attendant: Ishita &#74;oshi &amp; son,Tab Atorvastatin 10 mg HS\n"
                "V9103,Rx Tab Amlodipine 5 mg &lt; 6 weeks BP 142/90 &amp; HR 78,Review in 2 weeks\n")
    out, _ = _sanitize(tmp_path, monkeypatch, {"exports/esc.csv": csv_text})
    text = _outputs(out)["exports/esc.csv"]
    assert "Hemant" not in text and "u0048" not in text and "Ishita" not in text and "&#74;" not in text
    for kept in ("Tab Telmisartan 40 mg OD", "Tab Atorvastatin 10 mg HS", "Tab Amlodipine 5 mg &lt; 6 weeks BP 142/90 &amp; HR 78"):
        assert kept in text


def test_gate_reads_runs_and_escapes():
    g = LeakGate()
    g.add("PATIENT_NAME", "Hector Pereira", None)
    g.add("PHONE", "9811100025", "9811100025")
    g.finalize()
    assert g.contains_leak("blob," + _b64("seen: Hector Pereira, tel 9811100099") + ",x")
    assert g.contains_leak("blob," + _b64("call 98111 00025 today") + ",x")
    assert g.contains_leak("a=Hector" + chr(92) + "u0020Pereira") and g.contains_leak("&#72;ector Pereira")
    assert not g.contains_leak("blob," + _b64("Tab Cefixime 200 mg BD for 5 days") + ",x")
    assert "Pereira" not in g.scrub("who: Hector&#32;Pereira ok")


def test_gate_catches_name_learned_elsewhere_inside_a_run(tmp_path, monkeypatch):
    out, _ = _sanitize(tmp_path, monkeypatch, {
        "a/Mariela_Quispe_9811100028.txt": "Routine OPD checkup complete. Paracetamol 650 mg SOS.\n",
        "b/log.csv": "id,blob\n1," + _b64("handover note: Pema Tsering and Mariela Quispe at 10 am") + "\n",
    })
    for text in _outputs(out).values():
        assert "Quispe" not in text and "Mariela" not in text
    inside = base64.b64decode(_outputs(out)["b/log.csv"].splitlines()[1].split(",")[1]).decode()
    assert "Quispe" not in inside and "handover note" in inside


def test_run_inside_a_json_string_and_fhir_attachment_unchanged(tmp_path, monkeypatch):
    note = "Forwarded: " + _b64("guardian Pushpa Rawat, mobile 9811100034, advised rest") + " (end)"
    doc = {"resourceType": "Bundle", "type": "collection", "entry": [
        {"resource": {"resourceType": "DocumentReference", "status": "current",
                      "content": [{"attachment": {"contentType": "text/plain", "data": _b64("Tab Cefixime 200 mg BD for 5 days, review in a week.")}}]}},
        {"resource": {"resourceType": "Communication", "status": "completed", "payload": [{"contentString": note}]}},
    ]}
    out, _ = _sanitize(tmp_path, monkeypatch, {"fhir/b.json": json.dumps(doc)})
    text = _outputs(out)["fhir/b.json"]
    got = json.loads(text)
    assert got["resourceType"] == "Bundle"
    att = got["entry"][0]["resource"]["content"][0]["attachment"]["data"]
    assert att == doc["entry"][0]["resource"]["content"][0]["attachment"]["data"]
    payload = got["entry"][1]["resource"]["payload"][0]["contentString"]
    assert payload.startswith("Forwarded: ") and payload.endswith(" (end)")
    inside = _decode_all(payload)
    assert "Pushpa" not in inside and "9811100034" not in inside and "advised rest" in inside
