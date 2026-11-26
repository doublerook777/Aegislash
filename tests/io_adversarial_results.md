# Aegislash Adversarial Test Results & Failure Analysis

**Date:** 2026-11-26  
**System Tested:** Aegislash (`main.py`, `validate_output.py`, `check_dev.py`)  
**Workspace:** `D:\Projects\Aegislash`  
**Note on Active Modules:** Local `HEAD` (`1a2d1e5`) runs real `aegis/io/` alongside `mock.py` stubs for `aegis/detect/`, `aegis/link/`, and `aegis/privacy/` (23 commits behind `origin/main`). Failure modes for the 3 new datasets are documented against **both** the observed local run and verified regex/logic in `origin/main`.

---

## 1. Exact Output (As-Is) — Initial Adversarial Dataset (`dev/adversarial_input`)

### 1.1 Exact Terminal Output (`main.py` + `validate_output.py` + `parse_adversarial.py`)

```text
files 16 sanitized 16 quarantined 0 records 10040 linked 0
CONTRACT OK
=== REPORT SUMMARY ===
{
  "schema": "raksha-report/1",
  "counts": {
    "files_total": 16,
    "files_sanitized": 16,
    "files_quarantined": 0,
    "records_processed": 10040,
    "identifiers_detected": 0,
    "records_linked": 0,
    "records_generalized": 0,
    "records_suppressed": 0,
    "records_quarantined": 0
  },
  "entities": {},
  "timing": {
    "seconds": 0.17
  },
  "resources": {
    "peak_rss_mb": 0.0
  }
}

=== PER-FILE STATUS ===
  00_manifest.json                          status=sanitized     sha256=2c9b8a2de1...
  01_base64_hidden_pii.json                 status=sanitized     sha256=4998fa0269...
  02_unicode_escape_name.json               status=sanitized     sha256=50147d2c8d...
  03_zero_width_chars.csv                   status=sanitized     sha256=0d000ff051...
  05_pii_in_header.csv                      status=sanitized     sha256=70e942170d...
  06_deep_nested.json                       status=sanitized     sha256=cd1c27742f...
  07_mixed_delimiters.csv                   status=sanitized     sha256=f65eec572c...
  08_phone_formats.csv                      status=sanitized     sha256=1168d2cfa7...
  09_aadhaar_formats.csv                    status=sanitized     sha256=3c98e90ff8...
  10_split_name.json                        status=sanitized     sha256=cdd58dd093...
  11_medical_confusion.txt                  status=sanitized     sha256=b8f50164ab...
  12_homoglyphs.csv                         status=sanitized     sha256=1730efeff2...
  13_large_5000_records.csv                 status=sanitized     sha256=a35e162b14...
  14_k_anon_violator.csv                    status=sanitized     sha256=11a7d4e784...
  15_pii_in_json_keys.json                  status=sanitized     sha256=a38e33b4f5...
  Zubair_Hussain_Dialysis_2024.csv          status=sanitized     sha256=e8a67ff3b8...

=== LEAK SCAN (looking for raw PII in sanitized output) ===
  !!! LEAKS DETECTED !!!
    00_manifest.json: contains 'Zubair'
    05_pii_in_header.csv: contains 'Shahid'
    06_deep_nested.json: contains 'Farhan'
    06_deep_nested.json: contains '9988776655'
    08_phone_formats.csv: contains '9876543211'
    08_phone_formats.csv: contains '9876543212'
    09_aadhaar_formats.csv: contains '123456789012'
    09_aadhaar_formats.csv: contains '1234 5678 9012'
    11_medical_confusion.txt: contains 'Ramesh Gupta'
    13_large_5000_records.csv: contains 'Zubair'
    14_k_anon_violator.csv: contains '9876543210'
    14_k_anon_violator.csv: contains '9876543211'
    14_k_anon_violator.csv: contains '9876543212'
    14_k_anon_violator.csv: contains '9876543213'
    14_k_anon_violator.csv: contains '9876543214'
    14_k_anon_violator.csv: contains 'Shahid'
    15_pii_in_json_keys.json: contains 'Shahid'
    15_pii_in_json_keys.json: contains 'Zubair'

=== DEEP JSON QUARANTINE CHECK ===
  06_deep_nested.json: status=sanitized  output=sanitized/06_deep_nested.json

=== FILENAME PII RENAME CHECK ===
  FAIL — PII still in output filename: Zubair_Hussain_Dialysis_2024.csv
  Output files: ['00_manifest.json', '01_base64_hidden_pii.json', '02_unicode_escape_name.json', '03_zero_width_chars.csv', '05_pii_in_header.csv', '06_deep_nested.json', '07_mixed_delimiters.csv', '08_phone_formats.csv', '09_aadhaar_formats.csv', '10_split_name.json', '11_medical_confusion.txt', '12_homoglyphs.csv', '13_large_5000_records.csv', '14_k_anon_violator.csv', '15_pii_in_json_keys.json', 'Zubair_Hussain_Dialysis_2024.csv']
```

---

## 2. Detailed Report & Observations (`dev/adversarial_input`)

### 2.1 Dataset Overview

| Dataset | Location | Files | Records | Attack Scope |
|---|---|---:|---:|---|
| **`dev/adversarial_input`** | `D:\Projects\Aegislash\dev\adversarial_input` | 16 | 10,040 | Base64 JSON blobs, `\u`-escaped Devanagari, zero-width chars (`U+200B`/`U+200C`/`U+200D`), PII in filename (`Zubair_Hussain_Dialysis_2024.csv`), PII in CSV headers & JSON keys, 500-deep JSON, mixed `,`/`;` delimiters, 10 phone shapes, 6 Aadhaar shapes, split `first_name`/`last_name`, `Dr.`/`C/O`/`K/C/O` confusion, Cyrillic `а` (`U+0430`), 5,000-row stress CSV, `k=1` violator |

### 2.2 What Passed
- **Contract Compliance & Zero Crashes:** `validate_output.py` passed (`CONTRACT OK`) across all 16 files.
- **Pipeline Speed & Determinism on 5,000+ Records:** `10,040` records processed in `0.17 s` (`0.44 s` on cold run) without stack overflow during the iterative tree walk in `aegis/io/formats.py`.

### 2.3 Confirmed Failures & Root Causes
1. **Mock `detect`, `link`, `privacy` (`identifiers_detected = 0`, `records_linked = 0`):**
   - Because `aegis/detect/mock.py`, `aegis/link/mock.py`, and `aegis/privacy/mock.py` are active locally, all 18 needle-scan hits (patient names, phones, Aadhaar numbers, JSON keys, CSV headers, and `Zubair_Hussain_Dialysis_2024.csv` filename) passed straight through untouched.
   - `LeakGate` (`aegis/io/leakgate.py`) cannot backstop undetected PII unless `detect` finds it in at least one file (`LeakGate.add` is populated solely from `detect` findings).
2. **`06_deep_nested.json` (depth 500) Not Quarantined (`aegis/io/formats.py:84–91, 170–176`):**
   - `_looks_json()` and `_parse_json()` only raise `Unsupported("json_too_deep")` when `json.loads()` raises `RecursionError`. On Python 3.14, C `_json` parses both depth 500 and even depth 1500 without `RecursionError`, so deeply nested JSON passes unquarantined.
3. **`07_mixed_delimiters.csv` Mis-parsed (`aegis/io/formats.py:94–98`):**
   - `_sniff_delimiter()` inspects **only line 0** (`first = text.split("\n", 1)[0]`). Since line 0 used `,` while rows 1–2 used `;`, the pipeline emitted each row as a single unsplit `col:0` cell under `context="id"`, blinding column-role inference downstream.

---

## 3. Three Additional Breaker Datasets (`breaker_ds1` – `breaker_ds3`)

Three targeted datasets with `input/`, `truth/truth.json`, and `dataset_manifest.json` were created under `D:\Projects\Aegislash\dev\` to break **`io`**, **`detect`**, and **`link` + `privacy`** across both the local pipeline and `origin/main`'s real modules.

| Dataset | Location | Files | Units | Entities | Canaries | Primary Failure Focus |
|---|---|---:|---:|---:|---:|---|
| **Breaker 1 (`breaker_ds1_io_formats`)** | `D:\Projects\Aegislash\dev\breaker_ds1_io_formats` | 11 | 17 | 39 | 4 | Post-4KB binary NUL trailer, JSONL-in-`.csv`, `_PERSON_KEY` record-split collapse, data-URI/wrapped Base64, 950/1500-deep JSON, 1/5-token LeakGate bypass, mixed delim, FHIR query ref |
| **Breaker 2 (`breaker_ds2_detect_bypass`)** | `D:\Projects\Aegislash\dev\breaker_ds2_detect_bypass` | 6 | 13 | 42 | 2 | Lowercase/mixed PANs, slash/paren phones & STD landlines behind unseen labels, mixed-sep & `1`-leading Aadhaar, unseen Hindi headers, arbitrary JSON map keys, `%5C` URL encoding, Cyrillic `\u0430`, `<50%` Dr. column trap |
| **Breaker 3 (`breaker_ds3_link_privacy`)** | `D:\Projects\Aegislash\dev\breaker_ds3_link_privacy` | 4 | 14 | 81 | 1 | Micro-batch `k`-anonymity bypass (`len(profiles) < 10`), unredacted `Tehsil`/`Block` sub-district leak, cross-script phonetic (`Tiwari`/`तिवाडी`), initial/nickname fragmentation, homonym pair collision |

### 3.1 Executive Summary Comparison (Observed Run Results)

| Metric | Breaker 1 (`io_formats`) | Breaker 2 (`detect_bypass`) | Breaker 3 (`link_privacy`) |
|---|---|---|---|
| **Contract Compliance (`validate_output.py`)** | `CONTRACT OK` | `CONTRACT OK` | `CONTRACT OK` |
| **Files Sanitized / Quarantined** | `10 / 1` (`11` total) | `6 / 0` (`6` total) | `4 / 0` (`4` total) |
| **Records Processed / Linked** | `13 / 0` | `13 / 0` | `14 / 0` |
| **Identifiers Detected (`report.json`)** | `0` (mock) | `0` (mock) | `0` (mock) |
| **Personal Data Leaked (`check_dev.py`)** | `33 / 35` (`94.3%`) | `40 / 40` (`100.0%`) | `80 / 80` (`100.0%`) |
| **Canaries Leaked (`check_dev.py`)** | `3 / 4` | `2 / 2` | `1 / 1` |
| **Medical Data Kept (`check_dev.py`)** | `15 / 15` (`100.0%`) | `19 / 19` (`100.0%`) | `12 / 12` (`100.0%`) |
| **Linking Precision / Recall / F0.5** | `0.00 / 0.00 / 0.00` | `0.00 / 0.00 / 0.00` | `0.00 / 0.00 / 0.00` |
| **Raw Copies of Broken Files (`check_dev.py`)** | **`1`** (penalty `-5`) | `0` | `0` |

---

### 3.2 Raw Test Outputs (As-Is)

#### Breaker 1 — `breaker_ds1_io_formats`

```text
files 11 sanitized 10 quarantined 1 records 13 linked 0
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 33 of 35 pieces still visible ( 94.3% leaked; lower is better)
   PATIENT_NAME     leaked   17 / 18    94.4%
   PHONE            leaked   13 / 14    92.9%
   AADHAAR          leaked    3 / 3    100.0%
   by language: latin 94.3%
   by hiding place: content 100.0%, base64 60.0%

2) CANARIES: 3 of 4 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 15 of 15 medical values survived (100.0%; higher is better)

4) PATIENT LINKING: precision 0.00, recall 0.00, F0.5 0.00  (pseudonyms that wrongly merge different people: 0)
   you linked nothing yet: write your pseudonym into records.jsonl "patient"

5) RAW COPIES: 1 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    PATIENT_NAME | latin | content | notes/late_binary_after_4kb.txt | Harishankar Tiwari
    PHONE | latin | content | notes/late_binary_after_4kb.txt | 9811223344
    PATIENT_NAME | latin | content | lab/stream_export_jsonl.csv | Kavita Rawat
    PHONE | latin | content | lab/stream_export_jsonl.csv | 9711223344
    AADHAAR | latin | content | lab/stream_export_jsonl.csv | 4567 1234 8901
    PATIENT_NAME | latin | content | lab/stream_export_jsonl.csv | Pradeep Joshi
    PHONE | latin | content | lab/stream_export_jsonl.csv | 9711223345
    AADHAAR | latin | content | lab/stream_export_jsonl.csv | 4567 1234 8902
    PATIENT_NAME | latin | content | registration/wrapped_multi_patient.json | Anwar Ansari
    PHONE | latin | content | registration/wrapped_multi_patient.json | 9833001101
    PATIENT_NAME | latin | content | registration/wrapped_multi_patient.json | Rehana Parveen
    PHONE | latin | content | registration/wrapped_multi_patient.json | 9833001102
    PATIENT_NAME | latin | content | registration/wrapped_multi_patient.json | Yogesh Shukla
    PHONE | latin | content | registration/wrapped_multi_patient.json | 9833001103
    PATIENT_NAME | latin | base64 | attachments/wrapped_b64_consent.json | Farzana Begum

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\HP\.gemini\antigravity-cli\brain\acfcd8f6-7233-4d3b-9f4a-ee512e2289ac\scratch\out_breaker_ds1_io_formats
REPORT_COUNTS: {"files_total": 11, "files_sanitized": 10, "files_quarantined": 1, "records_processed": 13, "identifiers_detected": 0, "records_linked": 0, "records_generalized": 0, "records_suppressed": 0, "records_quarantined": 0}
QUARANTINED: [{'input_sha256': '5e0d79c40dc99e3935291d6992e7d53af40772407656199e4b2b68bfe258031e', 'output': None, 'status': 'quarantined', 'reason': 'malformed_json'}]
```

Notable emitted `records.jsonl` entries from `out_breaker_ds1_io_formats`:
```text
{"file": "sanitized/corrupt/depth_1500_bomb.json", "loc": "doc", "patient": null}
{"file": "sanitized/lab/stream_export_jsonl.csv", "loc": "row:0", "patient": null}
{"file": "sanitized/lab/stream_export_jsonl.csv", "loc": "row:1", "patient": null}
{"file": "sanitized/notes/late_binary_after_4kb.txt", "loc": "doc", "patient": null}
{"file": "sanitized/registration/wrapped_multi_patient.json", "loc": "doc", "patient": null}
```

#### Breaker 2 — `breaker_ds2_detect_bypass`

```text
files 6 sanitized 6 quarantined 0 records 13 linked 0
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 40 of 40 pieces still visible (100.0% leaked; lower is better)
   PATIENT_NAME     leaked   17 / 17   100.0%
   PHONE            leaked    9 / 9    100.0%
   MRN              leaked    4 / 4    100.0%
   PAN              leaked    4 / 4    100.0%
   PIN              leaked    3 / 3    100.0%
   AADHAAR          leaked    3 / 3    100.0%
   by language: latin 100.0%, deva 100.0%
   by hiding place: content 100.0%, key 100.0%

2) CANARIES: 2 of 2 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 19 of 19 medical values survived (100.0%; higher is better)

4) PATIENT LINKING: precision 0.00, recall 0.00, F0.5 0.00  (pseudonyms that wrongly merge different people: 0)
   you linked nothing yet: write your pseudonym into records.jsonl "patient"

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    PATIENT_NAME | latin | content | billing/lowercase_pan_claims.csv | Gaurav Malhotra
    PAN | latin | content | billing/lowercase_pan_claims.csv | gxlpv2692s
    PATIENT_NAME | latin | content | billing/lowercase_pan_claims.csv | Sonal Kulkarni
    PAN | latin | content | billing/lowercase_pan_claims.csv | ywfpk4957p
    PATIENT_NAME | latin | content | billing/lowercase_pan_claims.csv | Nitin Agarwal
    PAN | latin | content | billing/lowercase_pan_claims.csv | AbCdE1234f
    PATIENT_NAME | latin | content | billing/lowercase_pan_claims.csv | Pooja Bansal
    PAN | latin | content | billing/lowercase_pan_claims.csv | BNSLP8821K
    PATIENT_NAME | latin | content | notes/escalation_unseen_phones.txt | Zulqarnain Barua
    PHONE | latin | content | notes/escalation_unseen_phones.txt | 989/900/1122
    PHONE | latin | content | notes/escalation_unseen_phones.txt | 0522-2418392
    PHONE | latin | content | notes/escalation_unseen_phones.txt | (795) 633-0006
    PHONE | latin | content | notes/escalation_unseen_phones.txt | +91/9788/002233
    PHONE | latin | content | notes/escalation_unseen_phones.txt | 011-26597135
    PATIENT_NAME | latin | content | registration/synthetic_aadhaar_variants.csv | Hargobind Khorana

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\HP\.gemini\antigravity-cli\brain\acfcd8f6-7233-4d3b-9f4a-ee512e2289ac\scratch\out_breaker_ds2_detect_bypass
REPORT_COUNTS: {"files_total": 6, "files_sanitized": 6, "files_quarantined": 0, "records_processed": 13, "identifiers_detected": 0, "records_linked": 0, "records_generalized": 0, "records_suppressed": 0, "records_quarantined": 0}
QUARANTINED: []
```

#### Breaker 3 — `breaker_ds3_link_privacy`

```text
files 4 sanitized 4 quarantined 0 records 14 linked 0
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 80 of 80 pieces still visible (100.0% leaked; lower is better)
   PATIENT_NAME     leaked   15 / 15   100.0%
   VILLAGE          leaked   12 / 12   100.0%
   PHONE            leaked   11 / 11   100.0%
   RELATIVE_NAME    leaked   10 / 10   100.0%
   PIN              leaked    8 / 8    100.0%
   DOB              leaked    8 / 8    100.0%
   AADHAAR          leaked    8 / 8    100.0%
   MRN              leaked    8 / 8    100.0%
   by language: latin 100.0%, deva 100.0%
   by hiding place: content 100.0%

2) CANARIES: 1 of 1 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 12 of 12 medical values survived (100.0%; higher is better)

4) PATIENT LINKING: precision 0.00, recall 0.00, F0.5 0.00  (pseudonyms that wrongly merge different people: 0)
   you linked nothing yet: write your pseudonym into records.jsonl "patient"

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    MRN | latin | content | hosp_a/jhansi_reg.csv | JHS/26/1001
    PATIENT_NAME | latin | content | hosp_a/jhansi_reg.csv | Shailendra Tiwari
    RELATIVE_NAME | latin | content | hosp_a/jhansi_reg.csv | Mahesh Tiwari
    DOB | latin | content | hosp_a/jhansi_reg.csv | 12/05/1978
    VILLAGE | latin | content | hosp_a/jhansi_reg.csv | Raniyapur
    PIN | latin | content | hosp_a/jhansi_reg.csv | 284204
    PHONE | latin | content | hosp_a/jhansi_reg.csv | 9810001001
    AADHAAR | latin | content | hosp_a/jhansi_reg.csv | 4567 8901 2345
    MRN | latin | content | hosp_a/jhansi_reg.csv | JHS/26/1002
    PATIENT_NAME | latin | content | hosp_a/jhansi_reg.csv | Govind Prasad
    RELATIVE_NAME | latin | content | hosp_a/jhansi_reg.csv | Bhola Prasad
    DOB | latin | content | hosp_a/jhansi_reg.csv | 04/02/1937
    VILLAGE | latin | content | hosp_a/jhansi_reg.csv | Pahari
    PIN | latin | content | hosp_a/jhansi_reg.csv | 284204
    PHONE | latin | content | hosp_a/jhansi_reg.csv | 9810001002

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\HP\.gemini\antigravity-cli\brain\acfcd8f6-7233-4d3b-9f4a-ee512e2289ac\scratch\out_breaker_ds3_link_privacy
REPORT_COUNTS: {"files_total": 4, "files_sanitized": 4, "files_quarantined": 0, "records_processed": 14, "identifiers_detected": 0, "records_linked": 0, "records_generalized": 0, "records_suppressed": 0, "records_quarantined": 0}
QUARANTINED: []
```

---

### 3.3 Reasons for Failure (Code-Verified Root Causes Across Local `io` and `origin/main`)

#### Dataset 1 (`breaker_ds1_io_formats`) — Confirmed `io` Structural Failures
1. **Binary Trailer After Byte 4096 Exported Raw (`notes/late_binary_after_4kb.txt` → `RAW COPIES: 1`):**
   - `aegis/io/decode.py` lines 18 and 28 inspect only `head = raw[:4096]` for `b"\x00"`. Once valid text exceeds 4,096 bytes, appended `\x00PK\x03\x04...` binary payload passes `decode()` cleanly and is written byte-for-byte into `sanitized/` (`expect="either"` triggers `copied_raw = 1`).
2. **Deeply Nested 1,500-Level JSON Not Quarantined (`corrupt/depth_1500_bomb.json`):**
   - `aegis/io/formats.py` lines 88 and 173 depend on `json.loads()` raising `RecursionError`. Python 3.14's C `_json` module uses an iterative parser and does **not** raise `RecursionError` at depth `950` or `1500`, so `corrupt/depth_1500_bomb.json` (including `CANARY_DS1_DEPTH1500`) was marked `"status": "sanitized"` instead of quarantined.
3. **JSON-Lines Inside `.csv` Corrupted & Row Indices Shifted (`lab/stream_export_jsonl.csv`):**
   - `aegis/io/formats.py` line 75 calls `_looks_json()` on the whole file, which raises `ValueError` (`Extra data`) on NDJSON. It then falls back to `_parse_csv(rel, text, ",")`, consuming line 0 (`Kavita Rawat`) as the **CSV header** (`@file`) and splitting remaining JSON objects by commas (`records.jsonl` shows only `row:0` and `row:1` for a 3-patient file).
4. **Wrapper Metadata Field Collapses Multi-Patient JSON into 1 Doc (`registration/wrapped_multi_patient.json`):**
   - `aegis/io/formats.py` line 156 checks `any(_person_key(k) and not (isinstance(v, list) ...))`. Because `"patient_export_source"` matches `_PERSON_KEY` (`patient`) and holds a string, `_record_pointers()` returns `[]` — collapsing all `/visits/0`..`/visits/2` patient records into one single `"doc"` entry in `records.jsonl`.
5. **Data-URI & Wrapped Base64 Untouched (`attachments/wrapped_b64_consent.json`):**
   - `aegis/io/formats.py` lines 48–54 require `_B64_RX.fullmatch(v)` and `len(v) % 4 == 0`. Both `data:text/plain;base64,...` and 32-char newline-wrapped base64 fail `fullmatch`, leaving `Farzana Begum`, Aadhaar `4567 8901 2345`, phone `9822334455`, and `CANARY_DS1_B64URI` raw inside base64 (`base64 60.0%` leaked).
6. **1-Token & 5-Token Names Ignored by LeakGate (`opd/single_and_long_names.csv` + `notes/followup_unlabelled_tokens.txt`):**
   - `aegis/io/leakgate.py` line 52 restricts `self.names` to `2 <= len(toks) <= 4`. Single-word (`"Sakshi"`) and 5-word (`"Thakur Bhanu Pratap Singh Chauhan"`) names bypass LeakGate cross-file propagation.
7. **Single-Line Delimiter Sniffer & FHIR Query Suffixes (`legacy/mixed_delim_cp1252.csv`, `fhir/bundle_query_ref.json`):**
   - `formats.py:94–98` inspects only line 0 (`','` count `2` beats `';'` count `1`), leaving every semicolon-separated body row collapsed into `col:0` (`"101;Ritu Saxena;..."`).
   - `formats.py:296–301` only rewrites exact string matches in `ref_map`, leaving query-suffixed FHIR references like `"Patient/pat-901?_format=json"` unsynchronized after `Patient.id` replacement.

#### Dataset 2 (`breaker_ds2_detect_bypass`) — Verified `detect` Failure Modes (`origin/main:aegis/detect/`)
1. **Lowercase / Mixed-Case PAN Bypass (`billing/lowercase_pan_claims.csv`):**
   - `origin/main:aegis/detect/ids.py:20` defines `PAN = re.compile(_L + r"[A-Z]{5}\d{4}[A-Z]" + _R)` without `re.I`. Lowercase/mixed PANs (`gxlpv2692s`, `ywfpk4957p`, `AbCdE1234f`) fail unlabelled detection completely.
2. **Slash/Parenthesized Mobiles, STD Landlines & Unseen Labels (`notes/escalation_unseen_phones.txt`):**
   - `origin/main:aegis/detect/ids.py:25–30` (`_PHONE_BODY`) does not match slash-separated phones (`989/900/1122`), parenthesized formats (`(795) 633-0006`), or `0522-2418392` / `011-26597135` landlines; and line 59 (`_LABELLED`) omits `caller=`, `dial:`, `emergency_num=`, `attendant_cell:`, and `helpline#`.
3. **Mixed-Separator & Leading-1 Aadhaar + Numeric MRNs (`registration/synthetic_aadhaar_variants.csv`):**
   - `origin/main:aegis/detect/ids.py:19` uses backreference `\1` and leading `[2-9]`, rejecting `"4567-8901 2345"` (mixed `-` and space) and `"1234 5678 9012"`; pure digits `"20265549"` under unseen column headers `parchi_no` / `pehchaan_sankhya` / `dak_code` miss `MRN_SHAPES`.
4. **Arbitrary JSON Object Keys (`misc/unscanned_json_keys.json`):**
   - Names stored as dictionary keys under `"escalation_map"` and `"ward_assignments"` (not starting with `"by_"`) evade key-name scanning in `aegis/detect/engine.py`.
5. **URL Encoding, Cyrillic Homoglyphs & `<50%` Doctor Column Heuristic (`notes/url_homoglyph_medical_trap.txt`, `opd/deva_digits_and_doctor_col.csv`):**
   - `%3A`/`%5C` URL escapes break word boundaries around `Rukhsana_Bhattacharya`; Cyrillic `U+0430` (`а`) breaks Latin name token matching; and `Dr. Arvind Mehta` as `<50%` (1 of 3) in a `consultant` column triggers PR #8's threshold ambiguity alongside same-name doctor/patient collision (`Dr. Suresh Pandey` vs `Suresh Pandey`).

#### Dataset 3 (`breaker_ds3_link_privacy`) — Verified `link` & `privacy` Failure Modes (`origin/main`)
1. **Micro-Batch k-Anonymity Disable (`len(profiles) < 10` in `origin/main:aegis/privacy/engine.py:163`):**
   - Because Dataset 3 intentionally contains 8 distinct patients (`hosp_a/jhansi_reg.csv`), `enforce_k = len(profiles) >= max(10, min_k * 2)` evaluates to `False`. Every record receives `tier = "normal"`, disabling both age-band widening and `[DISTRICT]`/`[PIN]`/`[VILLAGE]` suppression even on `89/M` (`Visceral leishmaniasis`) and `92/F` (`Huntington's chorea`).
2. **Sub-District `Tehsil` & `Block` Quasi-Identifier Escape (`hosp_a/jhansi_reg.csv`, `hosp_b/hindi_opd.tsv`, `hosp_d/ward_followup.json`):**
   - Even when `len(profiles) >= 10` promotes a unique elderly profile to `suppress_qi` (`[DISTRICT]`, `[VILLAGE]`, `[PIN]` suppressed), `Tehsil` (`Mauranipur`, `Karwi`) and `Block` (`Bangra`, `Pahari`) are kept verbatim, reconstructing exact district/locality for an attacker (`k=1`).
3. **Cross-Script Phonetic, Initial-Only & Nickname Linkage Fragmentation (`origin/main:aegis/link/resolver.py`):**
   - Patient `PT001` spans `Shailendra Tiwari` (with Aadhaar) → `शैलेन्द्र तिवाडी` (`Tiwadi` phonetic drift, zero strong IDs) → `S. Tiwari` (initial-only + slash phone `981/000/1001` + age `47` vs `48`) → `Shailu Tiwari` (nickname, zero strong IDs), fragmenting one patient across multiple `PSN` clusters while `Shanti Devi` homonyms (`PT003` vs `PT004`, identical `age=42, F, district=Jhansi`) test false-merge resistance.
4. **Out-of-Range Age Edge Case (`age = 134` in `hosp_a/jhansi_reg.csv`):**
   - `origin/main:aegis/privacy/generalize.py:24` checks `age > 130` and returns `"[AGE]"`, `"suppressed"` while `link/resolver.py:194` rejects `age > 125` (`age = None`), dropping age evidence completely during linkage.
