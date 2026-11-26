"""Unit tests for aegis.link (contracts/link.md)."""
from __future__ import annotations

import os
import re

import pytest

from aegis.link import pseudonym, resolve
from aegis.link.normalize import full_names_match, normalize_tokens
from aegis.types import Evidence, empty_evidence


def _ev(
    record_id: str,
    *,
    names: list[dict] | None = None,
    ids: list[dict] | None = None,
    dob: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    village: str | None = None,
    district: str | None = None,
    pin: str | None = None,
    hospital: str | None = None,
) -> Evidence:
    base = empty_evidence(record_id)
    base["names"] = names or []
    base["ids"] = ids or []
    base["dob"] = dob
    base["age"] = age
    base["gender"] = gender  # type: ignore[typeddict-item]
    base["village"] = village
    base["district"] = district
    base["pin"] = pin
    base["hospital"] = hospital
    return base


def _nm(text: str, *, role: str = "patient", relation: str | None = None, script: str = "latin") -> dict:
    return {"text": text, "norm": text.casefold(), "script": script, "role": role, "relation": relation}


@pytest.fixture(autouse=True)
def _secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAKSHA_SECRET", "test-secret")


def test_secret_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAKSHA_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="secret_missing"):
        resolve([])
    with pytest.raises(RuntimeError, match="secret_missing"):
        pseudonym("k:123")


def test_pseudonym_format_and_secret_sensitivity(monkeypatch: pytest.MonkeyPatch) -> None:
    p1 = pseudonym("k:abc")
    assert re.match(r"^PSN-[0-9A-HJKMNP-TV-Z]{6}$", p1)
    assert pseudonym("k:abc") == p1
    monkeypatch.setenv("RAKSHA_SECRET", "other-secret")
    assert pseudonym("k:abc") != p1


def test_cross_script_names_and_schwa_conjuncts() -> None:
    pairs = [
        ("मोहम्मद शाहिद", "Mohd. Shahid"),
        ("रुख़साना सिद्दीक़ी", "Rukhsana Siddiqi"),
        ("सुखविंदर कौर", "Sukhvinder Kaur"),
        ("सत्येन्द्र सिंह", "Satyendra Singh"),
        ("फ़ातिमा क़ुरैशी", "Fatma Kureshi"),
        ("अनीता शर्मा", "Aneeta Sarma"),
    ]
    for deva, lat in pairs:
        assert full_names_match(normalize_tokens(deva), normalize_tokens(lat)), (deva, lat)
    assert not full_names_match(normalize_tokens("Kamal Thakur"), normalize_tokens("Kamla Nishad"))


def test_strong_id_linking_across_hospitals_and_scripts() -> None:
    recs = [
        _ev("a#row:0", names=[_nm("Mohammad Shahid")], ids=[{"type": "PHONE", "norm": "+91 93685-91915"}], dob="1986-05-30", gender="M"),
        _ev("b#doc", names=[_nm("मोहम्मद शाहिद", script="deva")], ids=[{"type": "PHONE", "norm": "९३६८५९१९१५"}], gender="M"),
        _ev("c#doc", names=[_nm("Shahid sahab", script="hinglish")], ids=[{"type": "MRN", "norm": "ADM-001"}], gender="M"),
        _ev("d#row:1", names=[_nm("Mohd. Shahid")], ids=[{"type": "PHONE", "norm": "9368591915"}, {"type": "MRN", "norm": "ADM-001"}], gender="M"),
    ]
    out = resolve(recs)
    keys = {out[r["record_id"]] for r in recs}
    assert len(keys) == 1 and None not in keys
    # Opaque key contains no raw PII
    key = next(iter(keys))
    assert key is not None and "shahid" not in key.casefold() and "93685" not in key


def test_bare_digit_mrn_hospital_guard() -> None:
    recs = [
        _ev("a#row:0", names=[_nm("Ramesh Kumar")], ids=[{"type": "MRN", "norm": "010607"}], hospital="asr"),
        _ev("b#row:0", names=[_nm("Suresh Verma")], ids=[{"type": "MRN", "norm": "010607"}], hospital="dhh"),
    ]
    out = resolve(recs)
    assert out["a#row:0"] is None
    assert out["b#row:0"] is None


def test_name_plus_second_clues_and_homonyms() -> None:
    recs = [
        # Patient 1: Brijesh Yadav, older, Jalalpur, S/o Raju Gupta
        _ev("p1#0", names=[_nm("Brijesh Yadav"), _nm("Raju Gupta", role="relative", relation="S/o")],
            ids=[{"type": "MRN", "norm": "JJH-001"}], dob="1954-10-18", age=70, gender="M", village="Jalalpur"),
        _ev("p1#1", names=[_nm("Brijesh"), _nm("Raju", role="relative", relation="S/o")], gender="M"),
        _ev("p1#2", names=[_nm("बृजेश यादव", script="deva")], age=71, village="जलालपुर"),
        # Patient 2: Homonym Brijesh Yadav, younger, Rasooldih, S/o Manoj Tiwari
        _ev("p2#0", names=[_nm("Brijesh Yadav"), _nm("Manoj Tiwari", role="relative", relation="S/o")],
            ids=[{"type": "MRN", "norm": "JJH-002"}], dob="1999-03-13", age=27, gender="M", village="Rasooldih"),
        _ev("p2#1", names=[_nm("Brijesh"), _nm("Manoj Tiwari", role="relative")], gender="M"),
        # Ambiguous record: only name, no second clue -> must stay None
        _ev("amb#0", names=[_nm("Brijesh Yadav")], gender="M"),
        # Village + age diff == 2 -> must NOT merge with p1 (age 70/71) or p2 (age 27)
        _ev("far#0", names=[_nm("Brijesh Yadav")], age=68, village="Jalalpur"),
    ]
    out = resolve(recs)
    assert out["p1#0"] is not None and out["p1#0"] == out["p1#1"] == out["p1#2"]
    assert out["p2#0"] is not None and out["p2#0"] == out["p2#1"]
    assert out["p1#0"] != out["p2#0"]
    assert out["amb#0"] is None
    assert out["far#0"] is None


def test_ambiguous_second_clue_rejected_and_no_transitive_overmerge() -> None:
    recs = [
        # Two distinct Sunita Patels who both have a relative named Ramesh
        _ev("s1#0", names=[_nm("Sunita Patel"), _nm("Ramesh Patel", role="relative", relation="W/o")],
            ids=[{"type": "AADHAAR", "norm": "111122223333"}], dob="1972-07-11", gender="F"),
        _ev("s1#1", names=[_nm("Sunita Patel")], ids=[{"type": "AADHAAR", "norm": "111122223333"}], dob="1972-07-11", gender="F"),
        _ev("s2#0", names=[_nm("Sunita Patel"), _nm("Ramesh", role="relative", relation="W/o")],
            ids=[{"type": "AADHAAR", "norm": "444455556666"}], dob="1985-01-05", gender="F"),
        _ev("s2#1", names=[_nm("Sunita Patel")], ids=[{"type": "AADHAAR", "norm": "444455556666"}], dob="1985-01-05", gender="F"),
        # Fragmented record matching both -> ambiguous -> must stay None
        _ev("frag#0", names=[_nm("Sunita"), _nm("Ramesh", role="relative", relation="W/o")], gender="F"),
    ]
    out = resolve(recs)
    assert out["s1#0"] == out["s1#1"] is not None
    assert out["s2#0"] == out["s2#1"] is not None
    assert out["s1#0"] != out["s2#0"]
    assert out["frag#0"] is None


def test_split_first_last_names_and_order_independence() -> None:
    recs = [
        _ev("csv#row:1", names=[_nm("Dinesh"), _nm("Lodhi")], dob="1990-02-01", gender="M"),
        _ev("txt#doc", names=[_nm("दिनेश लोधी", script="deva")], dob="1990-02-01", gender="M"),
        _ev("empty#doc"),
    ]
    out1 = resolve(recs)
    out2 = resolve(list(reversed(recs)))
    assert out1 == out2
    assert out1["csv#row:1"] is not None and out1["csv#row:1"] == out1["txt#doc"]
    assert out1["empty#doc"] is None
