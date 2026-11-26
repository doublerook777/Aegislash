# Aegislash Improvement & Evaluation Report (Track 3: "Secret Wards")

**Date:** 2026-11-26  
**Workspace:** `D:\Projects\Aegislash`  
**Base Revision:** `origin/main` (`c318b1e`, including PRs #2–#18)  
**Reference Standard:** [Yugaantar DevForge Tracks.pdf](file:///C:/Users/HP/Downloads/Yugaantar/Yugaantar%20DevForge%20Tracks.pdf) (Track 3: *Secret Wards*, pp. 11–18), `GEMINI-Medicine/pyDeid`, and [scrubadub_comparison_report.md](scrubadub_comparison_report.md)

---

## 1. Executive Summary

Aegislash is an offline, CPU-only, LLM-free privacy firewall targeting Track 3 (*Secret Wards*) across **English, Devanagari Hindi, and Hinglish** clinical dumps (**CSV, TSV, JSON, FHIR R4 Bundles, and free-text notes**).

Following the latest `origin/main` integration (`c318b1e`, merging PRs #15, #16, #17, and #18 on top of PRs #2–#13):
* **`aegis/detect/` + `aegis/io/`** now include the Scrubadub-inspired multilingual detection upgrades, header-vs-cell validation (`PIN`, ward/patient headers, `h.no`, `"r/o"` rule-out protection), JSON Lines in `.csv`/`.tsv`, wrapped/data-URI/filename base64 decoding, `%20`/`%5C`/`%2B` URL-escape handling in `LeakGate`, `Surname, Given` name reversal, and `18xx` DOB handling.
* **`aegis.detect.selftest`** passes **129 / 129** cases (`8` column tables, `16` single cells, `7` JSON docs, `3` filenames; `0` problems) directly on `c318b1e`.
* **Additional local `io` hardening** (preserved in git stash `local-io-hardening` from `security-vulnerability-audit`) passed **15 / 15** `unittest` cases and **14 / 14** `--mock` contract cases, with three targeted `io` items still worth porting onto `c318b1e` (`records_quarantined` + `before_hits` rollback in `pipeline.py`, `_UUID_RX`/`_ISO_DATE_RX`/`_ZERO_WIDTH` guards in `leakgate.py`, and `_sync_fhir_refs` in `formats.py`).

---

## 2. Implemented Improvements Observed

### 2.1 `main` (`c318b1e`, PRs #2–#18)
1. **Multilingual Detection (`aegis/detect/`):**
   * Context-aware CSV/JSON/FHIR role classification (`labels.py`, `engine.py`), clinical trap protection (`Dr. <name>`, `C/O <complaint>`, `K/C/O`, `H/O`, `r/o`, doses, `1-0-1`, vitals, labs, eponyms), and doctor-column heuristic (PR #8).
   * Red-team & Scrubadub-inspired fixes (PRs #12, #15, #16, #17, #18): case-insensitive `PAN`, grouped/slash/dotted/STD phones (`98.45.01.12.23`, `989/900/1122`, `(795) 633-0006`, `0512-2345678`), obfuscated emails (`EMAIL_OBF`), URL query-param/path PII (`find_url_pii()`), zero-width & homoglyph folding (`strip_evasion_with_map()`), trilingual action-cue & unlisted-person detection (`_ACTION_CUES`, `find_unlisted_person()`), `Surname, Given` parsing, header-vs-cell verification (`a2a3f2e`), and base64/run-together/Devanagari filename detection.
2. **IO & LeakGate (`aegis/io/` — PR #18 `18ba313`):**
   * JSON Lines in `.csv`/`.tsv`/`.txt` (`jsonl` mode + `malformed_json_lines` quarantine), wrapped/data-URI base64 (`_B64Form`) and base64 filename decoding (`_b64_name`), plus `LeakGate` word splitting across `_` and URL `%20`/`%5C`/`%2B` escapes and `Surname, Given` reversal (`204`-line `aegis/io/test_io.py`).
3. **Cross-Script Record Linkage (`aegis/link/` — PRs #10, #11):**
   * Latin/Devanagari/Hinglish normalization (`normalize.py`), strong-ID + unique secondary-clue (`name + DOB/relative/village+age±1`) blocking and clustering (`resolver.py`) preventing transitive over-merge and homonym collisions, plus keyed `HMAC-SHA256` `PSN-XXXXXX` pseudonyms (`psn.py`).
4. **Privacy & $k$-Anonymity Layer (`aegis/privacy/` — PRs #4, #5, #9):**
   * Per-patient HMAC-derived secret date shifting (`[-180, +180]` days via `"shift|" + key`, `dates.py`), truthful 5-year age bands (`85+` top-coding), `XXX***` PIN prefixes, village→district generalization (`generalize.py`), and dataset-wide $k$-anonymity (`min_group_size: 5`) + rare-condition (`<= 3` profiles) widening/district suppression (`engine.py`, `scripts/risk_report.py`).

### 2.2 Local `io` Hardening (`security-vulnerability-audit` Stash `local-io-hardening`)
Verified via `git diff` prior to pulling `c318b1e` (passed `15/15` `aegis.io.test_io` `unittest` & `14/14` `--mock` contract cases):
* **`pipeline.py`:** Accurate `records_quarantined` accounting on `detect_error` and pass-2 export/leak-gate quarantine, plus `gate.hits` rollback (`before_hits`) when a file is quarantined mid-export.
* **`leakgate.py`:** `_ZERO_WIDTH` stripping in `_fold()`, plus `_UUID_RX` span exclusion and `_ISO_DATE_RX` guard in `_digit_hit()` so UUIDs and ISO dates are never falsely redacted as MRNs/phones.
* **`formats.py`:** `_snapshot_fhir_entries()`, `_fhir_safe_id()`, and `_sync_fhir_refs()` to keep FHIR `Bundle.entry.fullUrl`, `resource.id`, and internal `reference` pointers synchronized after ID replacement.

---

## 3. Observed Results

### 3.1 Direct Checks in This Session
* **Post-pull `origin/main` (`c318b1e`):** `python -m aegis.detect.selftest` → **129 / 129 cases passed** (`8` column tables, `16` single cells, `7` JSON documents, `3` filenames; `0` problems).
  * *Note:* `main.py` and `pytest aegis/io/test_io.py aegis/privacy/test_privacy.py` on `c318b1e` require `rapidfuzz` (listed in `requirements.txt`, not installed in the system Python 3.14 interpreter).
* **Pre-pull `security-vulnerability-audit` (`io` hardening):** `python -m unittest aegis.io.test_io -v` → **15 / 15 passed** (`0.127 s`); `python scripts/check_contracts.py --mock` → **14 / 14 passed**.

### 3.2 Reported End-to-End Benchmarks Across `main` (`README.md`, `report/scrubadub_comparison_report.md`, `tests/test_results_and_observations.md`)

| Benchmark / Dataset | Leaked PII | Canaries | Medical Preserved | Linking (P / R / F0.5) | Notes |
|---|---|---:|---:|---|---|
| **`dev/input` (baseline `main` PR #13)** | `1.1%` (`35/3230`; `0.0%` content, `72.9%` filename) | `0 / 4` | `100.0%` (`4496/4497`) | `0.99 / 0.90 / 0.97` (`1` wrong merge) | `6.05 s`; `35/49` `k=1`; A2/A4 `32.7%`; A5 rare `0/18` |
| **`dev/input` (after PR #17 Scrubadub improvements)** | **`0 / 3,230` (`0.0%`)** | **`0 / 4`** | `100.0%` (`4496/4497` e2e) | **`F0.5 = 1.00`** (LF-hash) | `3.71 s` detect; `776/819` linked |
| **`dataset/input` (PR #17)** | **`0 / 1,951` (`0.0%`)** | **`0 / 4`** | `98.3%` (`978/995` e2e) | **`F0.5 = 0.99`** | `1.88 s` detect; `402/427` linked |
| **`tests/adversarial/input` (PR #17)** | **`0 / 157` true (`0.0%`)** | **`0 / 8`** | `95.7%` (`44/46` e2e) | **`F0.5 = 0.94`** (LF-hash) | `0.28 s` detect; `50/50` detect-level med |
| **Desktop `Dataset_1` (Standard, `83` files)** | `0.1%` (`1/1263` benign `Dr. Subhash`) | `0 / 4` | `96.2%` (`410/426`) | `1.00 / 0.71 / 0.93` (`0` wrong) | `3.72 s`; `5` quarantined; A2/A4 `18.2%` |
| **Desktop `Dataset_2` (Unseen/Hindi, `82` files)** | `0.0%` (`0/1054`) | `0 / 4` | `98.3%` (`399/406`) | `1.00 / 0.54 / 0.86` (`0` wrong) | `3.83 s`; `5` quarantined; A2/A4 `15.4%` |
| **Desktop `Dataset_3` (Chaos/Risk, `84` files)** | `0.6%` (`8/1269` benign collisions) | `0 / 4` | `97.0%` (`416/429`) | `1.00 / 0.77 / 0.94` (`0` wrong) | `3.51 s`; `5` quarantined; A2/A4 `21.9%` |
| **Desktop `Dataset_4` (Pre-PR #12 Breaker, `76` files)** | `25.1%` (`265/1055`) | `9 / 16` | `90.8%` (`148/163`) | `1.00 / 0.12 / 0.40` (`0` wrong) | `5.66 s`; drove PR #12/#17/#18 fixes |

---

## 4. Comparison: Aegislash vs. `pyDeid` (`GEMINI-Medicine/pyDeid`) for Track 3

| Capability | `pyDeid` | **Aegislash (`c318b1e`)** | Track 3 Impact |
|---|---|---|---|
| **Languages & Scripts** | English only | English, Devanagari Hindi (`०-९`), Hinglish | Essential for Language Trap (`0.0%` Deva/Hinglish leaks) |
| **Identifiers** | HIPAA + Canadian (OHIP, postal codes, MRN, SSN/SIN) | Aadhaar (Verhoeff/masked), ABHA, PAN, PMJAY/insurance, Indian mobile/STD, UHID/MRN | Covers Indian healthcare IDs & checksums |
| **Formats & Side Channels** | CSV clinical notes & string APIs | CSV, TSV, JSON, JSONL-in-CSV, FHIR R4, `.txt`, mixed encodings, base64, URL escapes, keys, headers, filenames, quarantine | Blocks Hidden Leakage Trap & raw-copy penalties |
| **Record Linkage** | None (single-note scope; optional `reid_string`) | Cross-script blocking/clustering (`0.97–1.00` F0.5) + non-reversible keyed `HMAC-SHA256` `PSN-XXXXXX` | Meets Fragmented Identity Trap & blocks A6/A7 |
| **Date Shifting** | Random offset per note/entry | Per-patient HMAC offset (`[-180, +180]` days) across all linked files | Preserves multi-visit LOS & blocks A5 global-shift recovery |
| **Quasi-Identifiers & $k$-Anonymity** | None | Truthful 5/10/20-yr age bands, `XXX***` PIN, village→district, rare-cell coarsening | Mitigates A2/A4/A5 voter-list attacks |
| **Replacement Mode** | Realistic surrogates ("hide in plain sight") or tags | `[TYPE]` placeholders + `PSN-XXXXXX` + truthful generalized bands | Matches Track 3 `validate_output.py` / `ATTACKS.md` contract |

---

## 5. Remaining Gaps & Next Steps

1. **Port Remaining Stashed `io` Guards onto `c318b1e`:** Apply `records_quarantined` + `before_hits` rollback (`pipeline.py`), `_UUID_RX` / `_ISO_DATE_RX` / `_ZERO_WIDTH` guards (`leakgate.py`), and `_sync_fhir_refs` (`formats.py`) from `stash@{0}` without overwriting `18ba313`'s `jsonl` and `_B64Form` support.
2. **Close Remaining `io` / `privacy` Edge Cases (`tests/io_adversarial_results.md`, `tests/test_results_and_observations.md`):**
   * Check full file bytes (beyond `raw[:4096]`) for NUL/binary trailers in `aegis/io/decode.py`, and enforce explicit JSON depth bounds (since Python 3.14 C `_json` parses depth 1500 without `RecursionError`).
   * Suppress/generalize `Tehsil` / `Block` whenever `k < 5` triggers `[DISTRICT]` suppression, and review the `len(profiles) < 10` micro-batch guard in `aegis/privacy/engine.py`.
3. **Full End-to-End Re-Verification in `.venv`:** Install `requirements-dev.txt` in a `.venv` (`rapidfuzz`, `jellyfish`, `indic-transliteration`, `pytest`) and run `pytest -q aegis/`, `main.py`, `validate_output.py`, `check_dev.py`, `scripts/risk_report.py`, and `check_submission.py --run` on `c318b1e`.
