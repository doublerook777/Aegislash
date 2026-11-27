"""The io module: two-pass pipeline (SPEC.md, "Modules and owners").

Pass 1: read + decode + parse every file into Records, call detect per file.
Then:   link.resolve on all evidence, privacy.plan on all results.
Pass 2: apply replacements, leak gate, write sanitized/, records.jsonl, report.json.

Nothing is written before pass 2. Raw values never reach stdout, stderr or disk: only counts
and reason codes are printed, and exceptions are reported by type name only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path, PurePosixPath

from aegis import detect, link, privacy
from aegis.io.decode import decode
from aegis.io.formats import SUPPORTED_EXT, ParsedFile, Unsupported, parse, write
from aegis.io.leakgate import LeakGate
from aegis.types import DIRECT_TYPES, QUASI_TYPES, Finding, RecordResult

_STATUS_RANK = {"sanitized": 0, "generalized": 1, "suppressed": 2}
_UNSAFE_NAME = re.compile(r"[^\w.\-ऀ-ॿ]+")


def _err(code: str) -> None:
    print(f"error: {code}", file=sys.stderr)


def peak_rss_mb() -> float:
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        return round(r / 1024 if sys.platform != "darwin" else r / 1048576, 1)
    except Exception:  # noqa: BLE001
        return 0.0


def _apply(value: str, findings: list[Finding], replace_fn) -> tuple[str, int, list[str]]:
    """Apply findings right-to-left. Returns (new value, identifiers applied, statuses)."""
    applied, statuses, last_start = 0, [], len(value) + 1
    for f in sorted(findings, key=lambda f: (f["start"], f["end"]), reverse=True):
        s, e = f["start"], f["end"]
        if not (0 <= s < e <= len(value)) or e > last_start or value[s:e] != f["text"]:
            continue  # out of range, overlapping or stale: skip (the leak gate is the safety net)
        rep = replace_fn(f)
        statuses.append(rep["status"])
        if rep["text"] is None:
            continue
        value = value[:s] + rep["text"] + value[e:]
        last_start = s
        applied += f["type"] in DIRECT_TYPES or f["type"] in QUASI_TYPES
    return value, applied, statuses


def _safe_filename(original: str, new: str) -> str:
    stem, suffix = PurePosixPath(original).stem, PurePosixPath(original).suffix
    new_stem = new[: len(new) - len(suffix)] if suffix and new.endswith(suffix) else PurePosixPath(new).stem
    cleaned = _UNSAFE_NAME.sub("_", new_stem.replace("[", "").replace("]", "")).strip("_") or "file"
    return cleaned + suffix if cleaned != stem else original


def run(inp: Path, out: Path) -> int:
    t0 = time.monotonic()
    sys.setrecursionlimit(20000)
    san = out / "sanitized"
    san.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ pass 1: read + detect
    entries: list[dict] = []            # report "files", in input order
    parsed: list[tuple[int, ParsedFile]] = []
    results: dict[str, RecordResult] = {}
    records_quarantined = 0
    for path in sorted((p for p in inp.rglob("*") if p.is_file()), key=lambda p: p.relative_to(inp).as_posix()):
        rel = path.relative_to(inp).as_posix()
        raw = path.read_bytes()
        entry = {"input_sha256": hashlib.sha256(raw).hexdigest(), "output": None, "status": "quarantined"}
        entries.append(entry)
        try:
            if PurePosixPath(rel).suffix.lower() not in SUPPORTED_EXT:
                raise Unsupported("unsupported_format")
            if not raw.strip():
                raise Unsupported("empty_file")
            text = decode(raw)
            if text is None:
                raise Unsupported("undecodable_text")
            pf = parse(rel, text)
        except Unsupported as exc:
            entry["reason"] = str(exc)
            continue
        except (RecursionError, MemoryError, ValueError, UnicodeError) as exc:
            entry["reason"] = f"parse_error_{type(exc).__name__}"
            continue
        try:
            res = detect.detect_file(pf.records)
            if len(res) != len(pf.records) or any(r["record_id"] != rec["record_id"] for r, rec in zip(res, pf.records)):
                raise RuntimeError("detect_shape")
        except Exception:  # noqa: BLE001 - any detect failure quarantines the file, never crashes the run
            entry["reason"] = "detect_error"
            records_quarantined += sum(1 for rec in pf.records if rec["loc"] != "@file")
            continue
        for r in res:
            results[r["record_id"]] = r
        parsed.append((len(entries) - 1, pf))

    # ------------------------------------------------------------------ link + plan
    evidence = [results[rid]["evidence"] for rid in sorted(results) if not rid.endswith("#@file")]
    try:
        keys = link.resolve(evidence)
    except RuntimeError as exc:
        if str(exc) == "secret_missing":
            _err("secret_missing")
            return 2
        keys = {e["record_id"]: None for e in evidence}
    except Exception:  # noqa: BLE001
        keys = {e["record_id"]: None for e in evidence}
    try:
        plan = privacy.plan([results[rid] for rid in sorted(results)], keys)
    except Exception as exc:  # noqa: BLE001
        _err(f"privacy_plan_failed_{type(exc).__name__}")
        return 3

    gate = LeakGate()
    for rid in sorted(results):
        for f in results[rid]["findings"]:
            if f["type"] in DIRECT_TYPES:
                gate.add(f["type"], f["text"], f.get("norm"))
    gate.finalize()

    # ------------------------------------------------------------------ pass 2: rewrite + write
    records_out: list[dict] = []
    identifiers = 0
    entity_counts: Counter = Counter()
    used_outputs: set[str] = set()
    for idx, pf in parsed:
        entry = entries[idx]
        before_hits = gate.hits
        try:
            new: dict[tuple[str, str], str] = {}
            rec_status: dict[str, str] = {}
            file_entities: Counter = Counter()
            n_ids = 0
            for rec in pf.records:
                rid = rec["record_id"]
                # file-level findings of a single-document file belong to that document's patient
                plan_rid = pf.doc_record_id if (rec["loc"] == "@file" and pf.doc_record_id) else rid
                by_path: dict[str, list[Finding]] = {}
                for f in results[rid]["findings"]:
                    by_path.setdefault(f["path"], []).append(f)
                worst = "sanitized"
                for fld in rec["fields"]:
                    value = fld["value"]
                    fs = by_path.get(fld["path"], [])
                    if fs:
                        value, applied, statuses = _apply(value, fs, lambda f, r=plan_rid: privacy.replace(plan, r, f))
                        n_ids += applied
                        for f in fs:
                            file_entities[f["type"]] += 1
                        for s in statuses:
                            if _STATUS_RANK.get(s, 0) > _STATUS_RANK[worst]:
                                worst = s
                    value = gate.scrub(value)
                    if value != fld["value"]:
                        new[(rid, fld["path"])] = value
                rec_status[rid] = worst
            content = write(pf, new)

            # output path: rename when the file name held PII
            name = PurePosixPath(pf.rel).name
            new_name = new.get((pf.file_record_id, "filename"))
            if new_name is not None:
                name = _safe_filename(name, new_name)
            parent = PurePosixPath(pf.rel).parent
            out_rel = (parent / name).as_posix() if str(parent) != "." else name
            base, n = out_rel, 2
            while out_rel in used_outputs:
                p = PurePosixPath(base)
                out_rel = (p.parent / f"{p.stem}_{n}{p.suffix}").as_posix()
                n += 1
            if gate.contains_leak(content) or gate.contains_leak(out_rel):
                raise RuntimeError("leak_gate")
            used_outputs.add(out_rel)
            dest = san / out_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="")
            entry.update(output=f"sanitized/{out_rel}", status="sanitized")
            identifiers += n_ids
            entity_counts.update(file_entities)
            for rec in pf.records:
                if rec["loc"] == "@file":
                    continue
                key = keys.get(rec["record_id"])
                line = {"file": f"sanitized/{out_rel}", "loc": rec["loc"],
                        "patient": link.pseudonym(key) if key else None}
                if rec_status.get(rec["record_id"], "sanitized") != "sanitized":
                    line["status"] = rec_status[rec["record_id"]]
                records_out.append(line)
        except Exception as exc:  # noqa: BLE001 - fail safe: quarantine, never half-write
            gate.hits = before_hits
            records_quarantined += sum(1 for rec in pf.records if rec["loc"] != "@file")
            entry.update(output=None, status="quarantined",
                         reason="leak_gate" if str(exc) == "leak_gate" else f"export_error_{type(exc).__name__}")

    with open(out / "records.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in records_out:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    pstats = privacy.stats(plan)
    n_san = sum(e["status"] == "sanitized" for e in entries)
    report = {
        "schema": "raksha-report/1",
        "files": entries,
        "counts": {
            "files_total": len(entries), "files_sanitized": n_san, "files_quarantined": len(entries) - n_san,
            "records_processed": len(records_out), "identifiers_detected": identifiers + gate.hits,
            "records_linked": sum(r["patient"] is not None for r in records_out),
            "records_generalized": int(pstats.get("records_generalized", 0)),
            "records_suppressed": int(pstats.get("records_suppressed", 0)),
            "records_quarantined": records_quarantined,
        },
        "entities": dict(sorted(entity_counts.items())),
        "timing": {"seconds": round(time.monotonic() - t0, 2)},
        "resources": {"peak_rss_mb": peak_rss_mb()},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"files {len(entries)} sanitized {n_san} quarantined {len(entries) - n_san} "
          f"records {len(records_out)} linked {report['counts']['records_linked']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aegislash privacy firewall")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args(argv)
    try:
        return run(Path(a.input), Path(a.output))
    except Exception as exc:  # noqa: BLE001 - never print content, only the exception type
        _err(f"fatal_{type(exc).__name__}")
        return 1
