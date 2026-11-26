#!/usr/bin/env python3
"""Self-assessment of k-anonymity & re-identification risk on sanitized outputs.

Measures:
  1. Release-internal k-anonymity on (age_band, gender, district) and
     (age_band, district, admission_week, diagnosis).
  2. Simulated A2/A4 registry linkage risk against a voter-roll style CSV
     (e.g. dev/attacker/registry.csv) without printing any PII.

Usage:
    python scripts/risk_report.py --output out/
    python scripts/risk_report.py --output out/ --registry dev/attacker/registry.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_AGE_BAND_RX = re.compile(r"(?<![\d/-])\b(\d{1,3})\s*-\s*(\d{1,3})\b(?![\d/-])")
_AGE_PLUS_RX = re.compile(r"(?<![\d/.-])\b(\d{2,3})\+")
_AGE_EXACT_RX = re.compile(
    r"(?:(?:age|umar|आयु|उम्र)\s*[:=-]?\s*|\b)(?<!x\s)(\d{1,3})\s*(?:/[MF]\b|(?:yrs?|years?|y/o|वर्ष|साल)\b(?!\s*back))",
    re.I,
)
_PIN_PREFIX_RX = re.compile(r"\b(\d{3})\*{3}\b")
_PIN_FULL_RX = re.compile(r"\b([1-8]\d{5})\b")
_ISO_DATE_RX = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_DMY_DATE_RX = re.compile(r"\b(\d{2})[/-](\d{2})[/-](20\d{2})\b")
_ICD_RX = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)\b")

_DISTRICT_KEYS = ("district", "jila", "distt")
_GENDER_KEYS = ("gender", "sex", "ling")
_AGE_KEYS = ("age", "umar", "age_sex")
_COND_KEYS = ("diagnosis", "condition", "icd", "dx")


def _norm(s: str) -> str:
    return " ".join(s.strip().casefold().split())


def _extract_age_range(text: str) -> tuple[int, int] | None:
    if re.search(r"\bx\s+\d+\s*(?:yrs?|years?)|\b\d+\s*(?:yrs?|years?)\s+back\b", text, re.I):
        # Skip clinical duration strings unless an explicit age band/label is also present
        cleaned = re.sub(r"\bx\s+\d+\s*(?:yrs?|years?)|\b\d+\s*(?:yrs?|years?)\s+back\b", "", text, flags=re.I)
    else:
        cleaned = text
    m = _AGE_BAND_RX.search(cleaned)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 <= lo <= hi <= 130 and (hi - lo) <= 40:
            return (lo, hi)
    m = _AGE_PLUS_RX.search(cleaned)
    if m:
        lo = int(m.group(1))
        if 50 <= lo <= 120:
            return (lo, 130)
    m = _AGE_EXACT_RX.search(cleaned)
    if m:
        a = int(m.group(1))
        if 0 <= a <= 130:
            return (a, a)
    return None


def _extract_date_and_week(text: str) -> tuple[str | None, str | None]:
    m = _ISO_DATE_RX.search(text)
    if m:
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            y, w, _ = d.isocalendar()
            return d.isoformat(), f"{y}-W{w:02d}"
        except ValueError:
            pass
    m = _DMY_DATE_RX.search(text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        for mo, da in ((b, a), (a, b)):
            try:
                d = dt.date(y, mo, da)
                iy, iw, _ = d.isocalendar()
                return d.isoformat(), f"{iy}-W{iw:02d}"
            except ValueError:
                continue
    return None, None


def _merge_profile(prof: dict[str, Any], key: str | None, val: str) -> None:
    if not val or val.startswith("[") and val.endswith("]"):
        return
    kl = (key or "").casefold()

    if any(k in kl for k in _AGE_KEYS) or not kl:
        ar = _extract_age_range(val)
        if ar is not None and prof["age_range"] is None:
            prof["age_range"] = ar
    elif kl == "age" and val.strip().isdigit():
        a = int(val.strip())
        prof["age_range"] = (a, a)

    if any(k in kl for k in _GENDER_KEYS):
        vn = _norm(val)
        if vn in ("m", "male", "पुरुष") or vn.endswith("/m"):
            prof["gender"] = "M"
        elif vn in ("f", "female", "महिला") or vn.endswith("/f"):
            prof["gender"] = "F"

    if any(k in kl for k in _DISTRICT_KEYS):
        vn = _norm(val)
        if vn and not vn.startswith("["):
            prof["district"] = vn

    if any(k in kl for k in _COND_KEYS):
        vn = _norm(val)
        if vn and not vn.startswith("["):
            prof["diagnoses"].add(vn)

    for m in _ICD_RX.findall(val):
        prof["diagnoses"].add(m.casefold())

    pm = _PIN_FULL_RX.search(val)
    if pm:
        prof["pin_prefix"] = pm.group(1)[:3]
    else:
        pm3 = _PIN_PREFIX_RX.search(val)
        if pm3 and prof["pin_prefix"] is None:
            prof["pin_prefix"] = pm3.group(1)

    iso_d, wk = _extract_date_and_week(val)
    if iso_d:
        prof["dates"].add(iso_d)
    if wk and prof["week"] is None:
        prof["week"] = wk


def _loads_json_safe(text: str) -> Any:
    """Parse JSON, allowing deep nesting up to pipeline limit without crashing."""
    try:
        return json.loads(text)
    except RecursionError:
        old_limit = sys.getrecursionlimit()
        if old_limit >= 20000:
            raise
        sys.setrecursionlimit(20000)
        try:
            return json.loads(text)
        finally:
            sys.setrecursionlimit(old_limit)


def _scan_json_obj(obj: Any, prof: dict[str, Any], parent_key: str | None = None, max_depth: int = 4096) -> None:
    stack: list[tuple[Any, str | None, int]] = [(obj, parent_key, 0)]
    while stack:
        cur, pkey, depth = stack.pop()
        if depth > max_depth or cur is None:
            continue
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k != "resourceType":
                    stack.append((v, str(k), depth + 1))
        elif isinstance(cur, list):
            for item in cur:
                stack.append((item, pkey, depth + 1))
        else:
            _merge_profile(prof, pkey, str(cur))


def _sniff_delimiter(text: str, ext: str) -> str:
    default = "\t" if ext == ".tsv" else ","
    sample = "\n".join(text.splitlines()[:5])
    if not sample.strip():
        return default
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;|")
        return dialect.delimiter
    except csv.Error:
        return default


def _rfc6901_escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _load_release_profiles(out_dir: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Read sanitized/ and records.jsonl to assemble quasi-identifier profiles."""
    records_path = out_dir / "records.jsonl"
    san_dir = out_dir / "sanitized"
    file_locs: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    unlinked = 0

    if records_path.is_file():
        for line in records_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            rel = str(rec["file"]).replace("sanitized/", "", 1)
            pat = rec.get("patient")
            if pat is None:
                unlinked += 1
            file_locs[rel].append((rec["loc"], pat))

    profiles: dict[str, dict[str, Any]] = {}

    def get_prof(pid: str) -> dict[str, Any]:
        return profiles.setdefault(
            pid,
            {"age_range": None, "gender": None, "district": None, "pin_prefix": None, "week": None, "diagnoses": set(), "dates": set()},
        )

    for rel, locs in sorted(file_locs.items()):
        p = san_dir / rel
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        text = p.read_text(encoding="utf-8", errors="replace")
        loc_map = {loc: (pat or f"unlinked:{rel}#{loc}") for loc, pat in locs}

        if ext in (".csv", ".tsv"):
            delim = _sniff_delimiter(text, ext)
            rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
            if not rows:
                continue
            header, body = rows[0], rows[1:]
            for idx, row in enumerate(body):
                pid = loc_map.get(f"row:{idx}", f"unlinked:{rel}#row:{idx}")
                prof = get_prof(pid)
                for h, cell in zip(header, row):
                    _merge_profile(prof, h, cell)
        elif ext == ".json":
            try:
                data = _loads_json_safe(text)
            except (ValueError, RecursionError):
                continue
            if "doc" in loc_map:
                _scan_json_obj(data, get_prof(loc_map["doc"]))
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    loc = f"/{idx}"
                    pid = loc_map.get(loc, f"unlinked:{rel}#{loc}")
                    _scan_json_obj(item, get_prof(pid))
            elif isinstance(data, dict):
                matched_records = False
                for k, v in data.items():
                    if isinstance(v, list):
                        pk = _rfc6901_escape(str(k))
                        for idx, item in enumerate(v):
                            loc = f"/{pk}/{idx}"
                            if loc in loc_map or isinstance(item, dict):
                                matched_records = True
                                pid = loc_map.get(loc, f"unlinked:{rel}#{loc}")
                                _scan_json_obj(item, get_prof(pid))
                if not matched_records:
                    _scan_json_obj(data, get_prof(f"unlinked:{rel}#doc"))
            else:
                _scan_json_obj(data, get_prof(f"unlinked:{rel}#doc"))
        else:
            pid = loc_map.get("doc", f"unlinked:{rel}#doc")
            prof = get_prof(pid)
            for line in text.splitlines():
                _merge_profile(prof, None, line)

    return profiles, unlinked


def _k_stats(keys: list[tuple[Any, ...]]) -> dict[str, Any]:
    if not keys:
        return {"profiles": 0, "unique_k1": 0, "pct_unique": 0.0, "lt5": 0, "min_k": 0, "median_k": 0.0}
    counts = Counter(keys)
    sizes = [counts[k] for k in keys]
    n = len(keys)
    u1 = sum(1 for s in sizes if s == 1)
    lt5 = sum(1 for s in sizes if s < 5)
    return {
        "profiles": n,
        "unique_k1": u1,
        "pct_unique": round(100.0 * u1 / n, 1),
        "lt5": lt5,
        "min_k": min(sizes),
        "median_k": round(float(statistics.median(sizes)), 1),
    }


def _simulate_registry_attack(profiles: dict[str, dict[str, Any]], registry_path: Path) -> dict[str, Any]:
    """Simulate Sweeney-style A2/A4 candidate filtering against attacker registry.csv."""
    rows = []
    with registry_path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            age_v = int(r["age"]) if str(r.get("age", "")).strip().lstrip("-").isdigit() else None
            rows.append({
                "district": _norm(r.get("district", "")),
                "gender": _norm(r.get("gender", "")).upper()[:1] or None,
                "age": age_v,
                "pin_prefix": str(r.get("pin", "")).strip()[:3],
            })

    cand_counts: list[int] = []
    for pid in sorted(profiles):
        prof = profiles[pid]
        cands = rows
        for pred in (
            lambda r, d=prof["district"]: (not d) or r["district"] == d,
            lambda r, g=prof["gender"]: (not g) or r["gender"] == g,
            lambda r, pp=prof["pin_prefix"]: (not pp) or r["pin_prefix"] == pp,
            lambda r, ar=prof["age_range"]: (not ar) or (
                r["age"] is not None and (ar[0] - 1) <= r["age"] <= (ar[1] + 1)
            ),
        ):
            nxt = [r for r in cands if pred(r)]
            if nxt:  # ATTACKS.md: filter that would empty set is skipped
                cands = nxt
        cand_counts.append(len(cands))

    if not cand_counts:
        return {"attacked_profiles": 0, "mean_candidates": 0.0, "pct_conf_ge_05": 0.0, "unique_matches": 0}
    conf_ge_05 = sum(1 for c in cand_counts if c <= 2)
    return {
        "attacked_profiles": len(cand_counts),
        "mean_candidates": round(sum(cand_counts) / len(cand_counts), 1),
        "pct_conf_ge_05": round(100.0 * conf_ge_05 / len(cand_counts), 1),
        "unique_matches": sum(1 for c in cand_counts if c == 1),
    }


def _simulate_known_facts_attack(
    profiles: dict[str, dict[str, Any]],
    known_facts_path: Path,
) -> dict[str, Any]:
    """Estimate A5 targeted risk: known rare conditions / unshifted dates matching profiles."""
    all_dates: dict[str, set[str]] = defaultdict(set)
    for pid, p in profiles.items():
        if p.get("dates"):
            all_dates[pid] = p["dates"]

    targets = 0
    rare_cond_hits = 0
    exact_date_hits = 0
    for line in known_facts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fact = json.loads(line)
        targets += 1
        ch = _norm(str(fact.get("condition_hint") or ""))
        vdates = set(fact.get("visit_dates") or [])

        matched_cond_pids = [
            pid for pid, p in profiles.items()
            if ch and any(ch in d or d in ch for d in p["diagnoses"])
        ]
        matched_rare = False
        if 1 <= len(matched_cond_pids) <= 3:
            for pid in matched_cond_pids:
                p = profiles[pid]
                if p["district"] is not None or (p["age_range"] and (p["age_range"][1] - p["age_range"][0]) <= 10):
                    matched_rare = True
                    break

        matched_date = any(vdates and (vdates & all_dates.get(pid, set())) for pid in profiles)
        if matched_rare:
            rare_cond_hits += 1
        if matched_date:
            exact_date_hits += 1

    return {
        "known_fact_targets": targets,
        "rare_cond_with_narrow_qi_hits": rare_cond_hits,
        "exact_date_overlap_hits": exact_date_hits,
    }


def analyze_release(
    out_dir: Path,
    registry_path: Path | None = None,
    known_facts_path: Path | None = None,
) -> dict[str, Any]:
    """Compute k-anonymity and optional registry / known-facts attack metrics."""
    profiles, unlinked = _load_release_profiles(out_dir)
    psn_profiles = {k: v for k, v in profiles.items() if k.startswith("PSN-")}
    eval_profiles = psn_profiles if psn_profiles else profiles

    cell_3 = []
    cell_4 = []
    for pid in sorted(eval_profiles):
        p = eval_profiles[pid]
        ab = f"{p['age_range'][0]}-{p['age_range'][1]}" if p["age_range"] else "unk"
        g = p["gender"] or "unk"
        d = p["district"] or "unk"
        w = p["week"] or "unk"
        dx = sorted(p["diagnoses"])[0] if p["diagnoses"] else "unk"
        cell_3.append((ab, g, d))
        cell_4.append((ab, d, w, dx))

    report: dict[str, Any] = {
        "linked_psn_profiles": len(psn_profiles),
        "unlinked_records": unlinked,
        "k_anon_age_gender_district": _k_stats(cell_3),
        "k_anon_age_district_week_dx": _k_stats(cell_4),
    }
    if registry_path and registry_path.is_file():
        report["simulated_registry_attack"] = _simulate_registry_attack(eval_profiles, registry_path)
    if known_facts_path and known_facts_path.is_file():
        report["simulated_known_facts_attack"] = _simulate_known_facts_attack(eval_profiles, known_facts_path)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", required=True, help="Output folder produced by main.py")
    ap.add_argument("--registry", default=None, help="Optional attacker registry.csv for simulated A2/A4 check")
    ap.add_argument("--known-facts", default=None, help="Optional known_facts.jsonl for simulated A5 check")
    ap.add_argument("--json", action="store_true", help="Print JSON summary instead of text")
    args = ap.parse_args()

    out_dir = Path(args.output)
    reg_path = Path(args.registry) if args.registry else None
    kf_path = Path(args.known_facts) if args.known_facts else None
    rep = analyze_release(out_dir, reg_path, kf_path)

    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0

    k3 = rep["k_anon_age_gender_district"]
    k4 = rep["k_anon_age_district_week_dx"]
    print("=" * 60)
    print(" Aegislash Risk & k-Anonymity Report (PII-free aggregates)")
    print("=" * 60)
    print(f"Linked patient profiles (PSN) : {rep['linked_psn_profiles']}")
    print(f"Unlinked records              : {rep['unlinked_records']}")
    print(f"\n1) Equivalence classes (age_band, gender, district):")
    print(f"   unique (k=1): {k3['unique_k1']} / {k3['profiles']} ({k3['pct_unique']}%) | k<5: {k3['lt5']} | min_k: {k3['min_k']} | median_k: {k3['median_k']}")
    print(f"\n2) Equivalence classes (age_band, district, adm_week, diagnosis):")
    print(f"   unique (k=1): {k4['unique_k1']} / {k4['profiles']} ({k4['pct_unique']}%) | k<5: {k4['lt5']} | min_k: {k4['min_k']} | median_k: {k4['median_k']}")
    if "simulated_registry_attack" in rep:
        ra = rep["simulated_registry_attack"]
        print(f"\n3) Simulated registry attack (A2/A4):")
        print(f"   attacked: {ra['attacked_profiles']} | mean candidates: {ra['mean_candidates']} | unique (k=1): {ra['unique_matches']} | est conf>=0.5: {ra['pct_conf_ge_05']}%")
    if "simulated_known_facts_attack" in rep:
        kf = rep["simulated_known_facts_attack"]
        print(f"\n4) Simulated targeted attack (A5):")
        print(f"   targets: {kf['known_fact_targets']} | rare+narrow-QI hits: {kf['rare_cond_with_narrow_qi_hits']} | exact date hits: {kf['exact_date_overlap_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
