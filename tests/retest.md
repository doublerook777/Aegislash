# Aegislash Retest Report (Post-PR #12 `detect/breaker-fixes` & PR #13)

**Date:** 2026-11-26  
**Branch / Commit Tested:** `main` at `a7faabf` (includes PR #12 `3689f41` `detect: fix red-team misses in PANs, phones, ref labels, parent keys and some lowercase names` and PR #13 `f08e0ca` `tests/` suites)  
**Environment:** Windows, Python 3.11.9, `RAKSHA_SECRET=practice`

---

## 1. Unit, Self-Test & Contract Checks

| Check | Command | Result |
|---|---|---|
| Link & Privacy unit tests | `pytest aegis/link/test_link.py aegis/privacy/test_privacy.py -v` | **18 / 18 passed** (11 `link`, 7 `privacy`) |
| Detect self-test | `python -m aegis.detect.selftest` | **81 / 81 passed** (`5` tables, `6` JSON docs, `2` filenames, `0` problems) |
| Module contract checks | `python scripts/check_contracts.py` | **13 / 13 passed** (`1` mock-only `detect` error case skipped) |

---

## 2. End-to-End Pipeline Results Across All Available Datasets

### 2.1 Repo Datasets (`dev/input`, `tests/adversarial`, `tests/breakers/*`)

| Dataset | Files (San/Quar) | Validation | Leaks (`check_dev.py`) | Canaries | Medical Kept | Linking (`P / R / F0.5`) | Wrong Merges | Raw Copies |
|---|---:|---|---|---:|---:|---|---:|---:|
| **`dev/input`** | 200 (195 / 5) | `CONTRACT OK` | `35 / 3230` (`1.1%`)* | `0 / 4` | `4496 / 4497` (`100.0%`) | `1.00 / 0.91 / 0.98`* | `0` | `0` |
| **`tests/adversarial/input`** | 38 (37 / 1) | `CONTRACT OK` | `22 / 157` (`14.0%`) | `3 / 8` | `47 / 49` (`95.9%`) | `1.00 / 0.62 / 0.89` | `0` | `0` |
| **`breaker_ds1_io_formats`** | 11 (10 / 1) | `CONTRACT OK` | `5 / 35` (`14.3%`) | `2 / 4` | `15 / 15` (`100.0%`) | `0.00 / 0.00 / 0.00` | `0` | `0` |
| **`breaker_ds2_detect_bypass`** | 6 (6 / 0) | `CONTRACT OK` | `8 / 40` (`20.0%`) | `2 / 2` | `18 / 19` (`94.7%`) | `0.00 / 0.00 / 0.00` | `0` | `0` |
| **`breaker_ds3_link_privacy`** | 4 (4 / 0) | `CONTRACT OK` | `4 / 80` (`5.0%`) | `1 / 1` | `12 / 12` (`100.0%`) | `1.00 / 0.33 / 0.71` | `0` | `0` |
| **`breakers/adversarial_input`** | 16 (16 / 0) | `CONTRACT OK` | *(no `truth.json`; 20,098 detected, 14 linked, 7.83 s)* | — | — | — | — | — |

\* *Note on `dev/input` on Windows:* All 35 `filename` leaks and the `0.91` (vs `0.9925` disk-SHA matched) recall are caused by Windows CRLF checkout altering `input_sha256` on renamed `.txt`/`.json` files relative to LF hashes in `dev/truth/truth.json`; actual content leaks are `0 / 3230` (`0.0%`).

### 2.2 Desktop Cohort Datasets (`Dataset_1`–`Dataset_4`, Before vs After PR #12)

| Dataset | Before (`test_results_and_observations.md`) | Now (`main @ a7faabf`) | Delta |
|---|---|---|---|
| **`Dataset_1_MultiHospital_Standard`** | `0.1%` leaked (`1/1263`), `0/4` canaries, `96.2%` med, `0.93` F0.5, `18.2%` A2/A4 | `0.1%` leaked (`1/1263`), `0/4` canaries, `96.2%` med, `0.93` F0.5, `18.2%` A2/A4 | Unchanged (already near-clean) |
| **`Dataset_2_UnseenFormats_Hindi`** | `0.0%` leaked (`0/1054`), `0/4` canaries, `98.3%` med, `0.86` F0.5, `15.4%` A2/A4 | `0.0%` leaked (`0/1054`), `0/4` canaries, `98.3%` med, `0.86` F0.5, `15.4%` A2/A4 | Unchanged |
| **`Dataset_3_Adversarial_Chaos_Risk`** | `0.6%` leaked (`8/1269`), `0/4` canaries, `97.0%` med, `0.94` F0.5, `21.9%` A2/A4 | **`0.4%` leaked (`5/1269`)**, `0/4` canaries, `97.0%` med, `0.94` F0.5, `21.9%` A2/A4 | **-3 leaks** |
| **`Dataset_4_Adversarial_Breaker`** | `25.1%` leaked (`265/1055`), `9/16` canaries, `90.8%` med, `0.40` F0.5 (`34` linked), `30.8%` A2/A4 | **`8.0%` leaked (`84/1055`)**, **`1/16` canaries**, `90.8%` med, **`0.66` F0.5 (`58` linked)**, **`15.0%` A2/A4** | **-181 leaks (-17.1 pp), -8 canaries, +0.26 F0.5, -15.8 pp A2/A4** |

---

## 3. Raw CLI Outputs (Key Suites)

### 3.1 `Dataset_4_Adversarial_Breaker` (Primary Red-Team Target)

```text
files 76 sanitized 71 quarantined 5 records 139 linked 58
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 84 of 1055 pieces still visible (  8.0% leaked; lower is better)
   PATIENT_NAME     leaked   43 / 227   18.9%
   PIN              leaked   21 / 86    24.4%
   RELATIVE_NAME    leaked   12 / 99    12.1%
   MRN              leaked    4 / 115    3.5%
   HOUSE            leaked    1 / 41     2.4%
   PHONE            leaked    1 / 157    0.6%
   VILLAGE          leaked    1 / 104    1.0%
   AADHAAR          leaked    1 / 58     1.7%
   DOB              leaked    0 / 60     0.0%
   INSURANCE_ID     leaked    0 / 12     0.0%
   EMAIL            leaked    0 / 1      0.0%
   ABHA_ADDRESS     leaked    0 / 24     0.0%
   PAN              leaked    0 / 71     0.0%
   by language: latin 7.8%, deva 0.0%, hinglish 79.2%
   by hiding place: content 7.4%, key 0.0%, filename 25.0%, base64 27.3%

2) CANARIES: 1 of 16 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 148 of 163 medical values survived ( 90.8%; higher is better)

4) PATIENT LINKING: precision 1.00, recall 0.28, F0.5 0.66  (pseudonyms that wrongly merge different people: 0)

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)
```

Risk report (`Dataset_4`):
```text
Linked patient profiles (PSN) : 20
Unlinked records              : 81
1) Equivalence classes (age_band, gender, district): unique (k=1): 5 / 20 (25.0%) | k<5: 20 | min_k: 1 | median_k: 3.0
2) Equivalence classes (age_band, district, adm_week, diagnosis): unique (k=1): 20 / 20 (100.0%) | k<5: 20 | min_k: 1 | median_k: 1.0
3) Simulated registry attack (A2/A4): attacked: 20 | mean candidates: 29.4 | unique (k=1): 1 | est conf>=0.5: 15.0%
```

### 3.2 `tests/adversarial/input`

```text
files 38 sanitized 37 quarantined 1 records 46 linked 7
CONTRACT OK
1) PERSONAL DATA: 22 of 157 pieces still visible ( 14.0% leaked; lower is better)
   PATIENT_NAME     leaked   14 / 49    28.6%
   DOB              leaked    4 / 14    28.6%
   PHONE            leaked    3 / 29    10.3%
   PIN              leaked    1 / 14     7.1%
   by language: latin 14.0%, deva 16.7%, hinglish 0.0%
   by hiding place: content 11.7%, base64 0.0%, filename 100.0%, key 0.0%, header 0.0%
2) CANARIES: 3 of 8 planted canaries found in your output folder
3) MEDICAL DATA KEPT: 47 of 49 medical values survived ( 95.9%; higher is better)
4) PATIENT LINKING: precision 1.00, recall 0.62, F0.5 0.89  (pseudonyms that wrongly merge different people: 0)
5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined
```

### 3.3 Targeted Breakers (`breaker_ds1` – `breaker_ds3`)

- **`breaker_ds1_io_formats`**: `5 / 35` (`14.3%`) leaked (`Pradeep Joshi` in `stream_export_jsonl.csv`, `Farzana Begum` + `4567 8901 2345` + `9822334455` in `wrapped_b64_consent.json`, `Sakshi` in `followup_unlabelled_tokens.txt`), `2 / 4` canaries, `15 / 15` medical kept, `0` raw copies.
- **`breaker_ds2_detect_bypass`**: `8 / 40` (`20.0%`) leaked (`PAN 0/4`, `MRN 0/4`, `PIN 0/3`, `PHONE 1/9` (`+91/9788/002233`), `AADHAAR 2/3` (`4567-8901 2345`, `1234 5678 9012`), `PATIENT_NAME 5/17` (`Hargobind Khorana`, `Vasundhara Raje`, `Keshav Dev`, `Rukhsana_Bhattacharya`, Cyrillic `Rаmesh Shаrmа`)), `2 / 2` canaries, `18 / 19` (`94.7%`) medical kept.
- **`breaker_ds3_link_privacy`**: `4 / 80` (`5.0%`) leaked (`Pahari`, `01/01/1892`, `शैलेन्द्र तिवाडी`, `Tindwari`), `1 / 1` canary, `12 / 12` (`100.0%`) medical kept, linking `1.00 / 0.33 / 0.71` (`0` wrong merges).

---

## 4. What Improved vs. What Still Needs Refinement

### What Improved Significantly (PR #12 Fixes Confirmed)
- **Lowercase PANs**: `71 / 71` leaked → **`0 / 71` (`0.0%`)** in `Dataset_4`, and `4 / 4` → **`0 / 4`** in `breaker_ds2`.
- **JSON keys & parent labels (`_map`, `organization.*`, `ref` vs `ref_by`)**: JSON key leaks dropped to **`0.0%`** across `Dataset_4`, `tests/adversarial`, and `breaker_ds2`.
- **Phones (`(912) 455-7781`, `912/450/7781`, landlines)**: `Dataset_4` phone leaks dropped `27.4% → 0.6%` (`1/157`), and `breaker_ds2` dropped `9/9 → 1/9`.
- **Opaque MRNs & PINs (`case_sheet_ref`, `dak_code`)**: `Dataset_4` MRN leaks dropped `43.5% → 3.5%`, and `breaker_ds2` MRNs dropped `4/4 → 0/4`.
- **Canaries & Linkage**: `Dataset_4` canaries dropped `9/16 → 1/16`, linking F0.5 rose `0.40 → 0.66` with **0 wrong merges across every single dataset**.

### Remaining Gaps Requiring Further Work
1. **Wrapped / `data:` Base64 Payloads (`io` / `detect`)**: `misc/consent_wrapped_b64.json` (`Dataset_4`) and `attachments/wrapped_b64_consent.json` (`breaker_ds1`) still leak (`27.3%` and `60.0%` base64 leak) because `data:text/plain;base64,...` URIs and line-wrapped base64 aren't decoded/scanned.
2. **Filename Leaks (`Dataset_4` `25.0%`, `tests/adversarial` `100.0%`)**:
   - Concatenated/lowercase filenames (`ds-prashantsuryavanshi-20268656.txt`) fail when the exact name is missing from the file body.
   - Accented (`Agustín_Fonseca_8673997291.txt`), Devanagari (`लक्ष्मी_अय्यर_पर्चा.txt`), and base64-encoded (`UHJhbmF2IERlc2htdWto...txt`) filenames leak in `tests/adversarial`.
3. **Zero-Width Characters, Cyrillic Homoglyphs & URL Encoding (`detect`)**:
   - `Rаmesh Shаrmа` (Cyrillic `а`), `Dеvikа Rаo`, and `Priyanka%20Sengupta` (`%20` / `%5C` URL-encoded) still bypass detection.
4. **Unlabelled TSV/CSV & Single Lowercase Names (`detect`)**:
   - `registration/unlabelled_deva_utf16be.tsv` leaked `21 / 86` PINs (`209622`, `205264`, etc.).
   - `lab/wa_lowercase_001..003.txt` (`harishankar`, `prashant`, `siddharth`) and `notes/followup_unlabelled_tokens.txt` (`Sakshi`) leaked single-token unlabelled names (`hinglish 79.2%`).
   - `unseen_schema/cryptic_pipe_utf16le.csv` (`P_NOM`, `X_YOB`, `Z_6D`, `PAT_TEL_1`) leaked `Surname, Given` names and year-of-birth (`DOB` `4/14`).
5. **`+91/XXXX/XXXXXX` Phone & Unconventional Aadhaar Separators (`breaker_ds2`)**:
   - `+91/9788/002233` (`escalation_unseen_phones.txt`) and `4567-8901 2345` / `1234 5678 9012` (`synthetic_aadhaar_variants.csv`) leaked.
6. **Privacy Risk (`dev/input` `scripts/risk_report.py`)**:
   - On `dev/input`, `(age_band, gender, district)` still has `36 / 50` (`72.0%`) `k=1` unique profiles and `34.0%` estimated A2/A4 risk (`conf >= 0.5`).
