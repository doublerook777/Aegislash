"""Unit and end-to-end tests for aegis.io (JSON Lines, base64 layouts, base64 file names, leak gate).

All names, numbers and files are invented. Run: .venv/bin/python -m pytest -q aegis/io
"""
from __future__ import annotations

import base64
import json

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
    for key in ("patient_count", "patientTotal", "patient_source", "patient_export_version", "patient_batch"):
        assert not formats._person_key(key)
    for key in ("patient", "patient_name", "uhid", "mobile", "guardian"):     # real subjects still are
        assert formats._person_key(key)
    one = {"patient_name": "Kavya Rastogi", "visits": [{"patient_name": "Kavya Rastogi", "mobile": "9811100032"}]}
    assert formats.parse("reg/one.json", json.dumps(one)).doc_record_id is not None      # a subject of its own: one document


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
