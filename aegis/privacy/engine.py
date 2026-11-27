"""Real privacy layer implementing contracts/privacy.md.

Two-stage workflow:
  1. ``plan(results, keys)`` computes per-patient / per-record secret date offsets,
     aggregates patient profiles across linked records, identifies rare conditions
     and small k-anonymity cells, and assigns a deterministic generalization tier.
  2. ``replace(plan, record_id, finding)`` produces the exact Replacement for every
     Finding using the precomputed plan.
  3. ``stats(plan)`` reports ``records_generalized`` and ``records_suppressed``.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Any

from aegis.link import pseudonym
from aegis.privacy.dates import shift_date_text, shift_days
from aegis.privacy.generalize import (
    generalize_age,
    generalize_pin,
    generalize_village,
    parse_age_int,
)
from aegis.privacy.policy import load_policy
from aegis.types import DIRECT_TYPES, TYPES, Finding, RecordResult, Replacement

_DIRECT_SET = frozenset(DIRECT_TYPES)
_ALL_TYPES_SET = frozenset(TYPES)
_KEEP_BY_DEFAULT = frozenset(("CONDITION", "DISTRICT", "GENDER"))

_DIRECT_PLACEHOLDER = {
    "PATIENT_NAME": "[PATIENT]",
    "RELATIVE_NAME": "[RELATIVE]",
}


def _profile_id(record_id: str, patient_key: str | None) -> str:
    return f"p|{patient_key}" if patient_key else f"r|{record_id}"


def _age_bucket(age: int | None, width: int, elderly: int) -> str:
    if age is None or age < 0:
        return "unk"
    if age >= elderly:
        return f"{elderly}+"
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"


def _infer_ref_year(ordered_results: list[RecordResult]) -> int:
    """Infer dataset reference year from the latest DATE finding, falling back to 2026."""
    years = []
    for res in ordered_results:
        for f in res.get("findings") or []:
            if f.get("type") == "DATE":
                norm = f.get("norm") or ""
                if len(norm) >= 4 and norm[:4].isdigit():
                    years.append(int(norm[:4]))
    return max(years) if years else 2026


def _derive_age_from_dob(dob_iso: str | None, ref_year: int) -> int | None:
    if not dob_iso or len(dob_iso) < 4 or not dob_iso[:4].isdigit():
        return None
    return max(0, ref_year - int(dob_iso[:4]))


def _compute_profile_tiers(
    ordered_results: list[RecordResult],
    keys: dict[str, str | None],
    policy: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Build profile metadata and assign risk tiers ('normal', 'widen', 'suppress_qi')."""
    w_norm = int(policy.get("age_band_years", 5))
    w_wide = int(policy.get("wide_age_band_years", 10))
    elderly = int(policy.get("elderly_age_threshold", 85))
    min_k = int(policy.get("min_group_size", 5))
    rare_thresh = int(policy.get("rare_condition_threshold", 3))

    profiles: dict[str, dict[str, Any]] = {}
    rec_to_prof: dict[str, str] = {}
    ref_year = _infer_ref_year(ordered_results)

    for res in ordered_results:
        rid = res["record_id"]
        if rid.endswith("#@file"):
            continue
        pid = _profile_id(rid, keys.get(rid))
        rec_to_prof[rid] = pid
        prof = profiles.setdefault(
            pid,
            {"age": None, "gender": None, "district": None, "conditions": set()},
        )
        ev = res.get("evidence") or {}
        if prof["age"] is None:
            if ev.get("age") is not None:
                prof["age"] = int(ev["age"])
            elif ev.get("dob"):
                prof["age"] = _derive_age_from_dob(ev.get("dob"), ref_year)
        if prof["gender"] is None and ev.get("gender"):
            prof["gender"] = ev["gender"]
        if prof["district"] is None and ev.get("district"):
            prof["district"] = str(ev["district"]).strip().casefold()

        for f in res.get("findings") or []:
            ft = f.get("type")
            if ft == "CONDITION":
                cname = (f.get("norm") or f.get("text") or "").strip().casefold()
                if cname:
                    prof["conditions"].add(cname)
            elif ft == "AGE" and prof["age"] is None:
                parsed_age = parse_age_int(f.get("text", ""), f.get("norm"))
                if parsed_age is not None:
                    prof["age"] = parsed_age
            elif ft == "DISTRICT" and prof["district"] is None:
                dname = (f.get("norm") or f.get("text") or "").strip().casefold()
                if dname:
                    prof["district"] = dname

    # A small release (fewer than max(10, 2 * min_k) profiles) cannot hold two cells of min_k people, so the
    # tiers below run as usual (they used to be switched off here, which left every patient in a small release
    # unique on age band + gender + district). On top of that, a district shared by fewer than min_k profiles is
    # suppressed in a small release, together with the village (which would otherwise be generalised to it).
    # Larger releases keep district as before: suppressing it there costs generalisation utility on standard data.
    small_release = len(profiles) < max(10, min_k * 2)
    district_counts: Counter[str] = Counter(p["district"] for p in profiles.values() if p["district"])
    for prof in profiles.values():
        prof["hide_district"] = bool(
            small_release and prof["district"] and district_counts[prof["district"]] < min_k
        )

    cond_counts: Counter[str] = Counter()
    cell_counts: Counter[tuple[str, str, str]] = Counter()
    wide_cell_counts: Counter[tuple[str, str, str]] = Counter()

    for pid in sorted(profiles):
        prof = profiles[pid]
        for c in sorted(prof["conditions"]):
            cond_counts[c] += 1
        g = prof["gender"] or "unk"
        d = prof["district"] or "unk"
        cell_counts[(_age_bucket(prof["age"], w_norm, elderly), g, d)] += 1
        wide_cell_counts[(_age_bucket(prof["age"], w_wide, elderly), g, d)] += 1

    tiers: dict[str, str] = {}
    for pid in sorted(profiles):
        prof = profiles[pid]
        age = prof["age"]
        g = prof["gender"] or "unk"
        d = prof["district"] or "unk"
        k_norm = cell_counts[(_age_bucket(age, w_norm, elderly), g, d)]
        k_wide = wide_cell_counts[(_age_bucket(age, w_wide, elderly), g, d)]
        has_rare_cond = any(cond_counts[c] <= rare_thresh for c in prof["conditions"])
        is_elderly = age is not None and age >= elderly

        if has_rare_cond and (k_norm < min_k or k_wide < min_k or is_elderly):
            tiers[pid] = "suppress_qi"
        elif k_norm < min_k or is_elderly:
            tiers[pid] = "widen"
        else:
            tiers[pid] = "normal"

    return profiles, tiers


def _apply_replace(
    rec_info: dict[str, Any],
    policy: dict[str, Any],
    finding: Finding,
) -> Replacement:
    t = finding["type"]
    if t not in _ALL_TYPES_SET:
        return {"text": "[REDACTED]", "status": "sanitized"}

    patient_key = rec_info["key"]
    tier = rec_info["tier"]

    if t in _DIRECT_SET:
        if t in ("PATIENT_NAME", "MRN") and rec_info["psn"]:
            return {"text": rec_info["psn"], "status": "sanitized"}
        placeholder = _DIRECT_PLACEHOLDER.get(t, f"[{t}]")
        return {"text": placeholder, "status": "sanitized"}

    if t in ("DATE", "DOB"):
        shifted = shift_date_text(finding["text"], finding.get("norm"), rec_info["shift_days"])
        if shifted is None:
            return {"text": "[DATE]" if t == "DATE" else "[DOB]", "status": "suppressed"}
        return {"text": shifted, "status": "generalized"}

    if t == "AGE":
        if tier == "suppress_qi":
            band_w = int(policy.get("wide_age_band_years", 10)) * 2
            elderly = min(80, int(policy.get("elderly_age_threshold", 85)))
        elif tier == "widen":
            band_w = int(policy.get("wide_age_band_years", 10))
            elderly = int(policy.get("elderly_age_threshold", 85))
        else:
            band_w = int(policy.get("age_band_years", 5))
            elderly = int(policy.get("elderly_age_threshold", 85))
        text_out, status = generalize_age(finding["text"], finding.get("norm"), band_w, elderly)
        return {"text": text_out, "status": status}  # type: ignore[return-value]

    if t == "PIN":
        text_out, status = generalize_pin(finding["text"], suppress=(tier != "normal"))
        return {"text": text_out, "status": status}  # type: ignore[return-value]

    hide_district = rec_info.get("hide_district", False)
    if t == "VILLAGE":
        text_out, status = generalize_village(rec_info["district"], suppress=(tier != "normal" or hide_district))
        return {"text": text_out, "status": status}  # type: ignore[return-value]

    if t in _KEEP_BY_DEFAULT:
        if t == "DISTRICT" and (tier == "suppress_qi" or hide_district):
            return {"text": "[DISTRICT]", "status": "suppressed"}
        return {"text": None, "status": "sanitized"}

    return {"text": "[REDACTED]", "status": "sanitized"}


def plan(results: list[RecordResult], keys: dict[str, str | None]) -> dict[str, Any]:
    """Build the dataset-wide privacy plan (date shifts, k-anonymity tiers, counts)."""
    policy = load_policy()
    secret_bytes = os.environ.get("RAKSHA_SECRET", "").encode("utf-8")
    max_shift = int(policy.get("date_shift_max_days", 180))

    ordered = sorted(results, key=lambda r: r["record_id"])
    profiles, tiers = _compute_profile_tiers(ordered, keys, policy)

    # Precompute per-patient / per-record date shifts and pseudonyms deterministically
    shift_cache: dict[str, int] = {}
    psn_cache: dict[str, str] = {}
    records_map: dict[str, dict[str, Any]] = {}
    gen_records = 0
    sup_records = 0

    for res in ordered:
        rid = res["record_id"]
        is_file_rec = rid.endswith("#@file")
        pkey = None if is_file_rec else keys.get(rid)
        pid = _profile_id(rid, pkey)
        shift_key = pkey if pkey else f"rec|{rid}"
        if shift_key not in shift_cache:
            shift_cache[shift_key] = shift_days(shift_key, secret_bytes, max_shift)
        if pkey and pkey not in psn_cache:
            psn_cache[pkey] = pseudonym(pkey)

        ev = res.get("evidence") or {}
        prof = profiles.get(pid)
        district = ev.get("district") or (prof["district"] if prof else None)
        rec_info = {
            "key": pkey,
            "psn": psn_cache[pkey] if pkey else None,
            "profile_id": pid,
            "tier": tiers.get(pid, "normal"),
            "shift_days": shift_cache[shift_key],
            "district": district,
            "hide_district": bool(prof and prof.get("hide_district")),
        }
        records_map[rid] = rec_info

        if is_file_rec:
            continue

        has_gen = False
        has_sup = False
        for f in res.get("findings") or []:
            rep = _apply_replace(rec_info, policy, f)
            if rep["status"] == "generalized":
                has_gen = True
            elif rep["status"] == "suppressed":
                has_sup = True
        if has_sup:
            sup_records += 1
        elif has_gen:
            gen_records += 1

    return {
        "policy": policy,
        "records": records_map,
        "stats": {
            "records_generalized": gen_records,
            "records_suppressed": sup_records,
        },
    }


def replace(plan: dict[str, Any], record_id: str, finding: Finding) -> Replacement:
    """Return the replacement for one Finding in ``record_id``."""
    rec_info = plan["records"][record_id]  # raises KeyError for unknown record_id
    return _apply_replace(rec_info, plan["policy"], finding)


def stats(plan: dict[str, Any]) -> dict[str, int]:
    """Return dataset-level generalization and suppression counts for report.json."""
    return dict(plan["stats"])
