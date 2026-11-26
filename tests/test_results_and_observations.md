# Aegislash Multi-Dataset Test Results & Observations

**Date:** 2026-11-26  
**System Tested:** Aegislash (`main.py`, `validate_output.py`, `check_dev.py`, `scripts/risk_report.py`)  
**Workspace:** `C:\Users\Hp\projects\Aegislash\Aegislash`

---

## 1. Test Datasets Created on Desktop

Three independent synthetic datasets were created on the Desktop (with zero patient/identifier overlap with `dev/input`), each structured with `input/`, `truth/truth.json`, `attacker/registry.csv`, `attacker/known_facts.jsonl`, and `dataset_manifest.json`, plus a fourth red-team adversarial breaker dataset:

| Dataset | Location | Files | Records | Patients | Population | Required Link Units | Focus / Stress Scenario |
|---|---|---:|---:|---:|---:|---:|---|
| **Dataset 1 (Standard Multi-Hospital)** | `Desktop\Dataset_1_MultiHospital_Standard` | 83 | 201 | 32 | 160 | 177 | Fresh cohort (Varanasi, Prayagraj, Gorakhpur, Jaunpur, Mirzapur) across UTF-8-SIG CSV, UTF-16 Hindi TSV, cp1252 CSV (`MM/DD/YYYY`), nested JSON, FHIR R4, WhatsApp forwards, hidden channels, and corrupt/unsupported files |
| **Dataset 2 (Unseen Formats & Hindi)** | `Desktop\Dataset_2_UnseenFormats_Hindi` | 82 | 181 | 30 | 150 | 157 | Fresh cohort (Mathura, Agra, Aligarh, Bareilly, Meerut) with unseen headers (`Rogee_Naam`, `Janam_Dinank`, `Sampark_Sutra`, `Patrak_Sankhya`), `;`-delimited cp1252 CSV, `DD-Mon-YYYY` dates, Devanagari numerals & phone digits, `\u`-escaped JSON, compact `Age/Sex` (`54/F`), and homonym pairs |
| **Dataset 3 (Adversarial Chaos & Risk)** | `Desktop\Dataset_3_Adversarial_Chaos_Risk` | 84 | 202 | 32 | 160 | 178 | Fresh cohort (Jhansi, Kanpur, Banda, Fatehpur, Chitrakoot) with elderly patients (`83–96` yrs), rare conditions & eponyms (*Kala-azar*, *Addison's*, *Parkinson's*, *Guillain-Barre*, *Wilson's*, *Hodgkin*, *Huntington's*), same-name doctor/patient trap, canaries, and hidden/malformed files |
| **Dataset 4 (Adversarial Breaker)** | `Desktop\Dataset_4_Adversarial_Breaker` | 76 | 167 | 40 | 200 | 141 | Red-team stress test using lowercase PANs, opaque headers (`case_sheet_ref`, `dak_code`), `|`-delimited CSV, numeric JSON PII, `_NOT_PERSON` wrapper keys, non-`by_` JSON keys, line-wrapped/`data:` base64, JSONL in `.txt`, slash/STD phones, lowercase free text, twins sharing a phone, and Devanagari filenames |

---

## 2. Executive Summary Comparison

| Metric | Dataset 1 (Standard) | Dataset 2 (Unseen/Hindi) | Dataset 3 (Chaos/Risk) | Dataset 4 (Breaker) |
|---|---|---|---|---|
| **Contract Compliance** | `CONTRACT OK` | `CONTRACT OK` | `CONTRACT OK` | `CONTRACT OK` |
| **Files Sanitized / Quarantined** | `78 / 5` (`83` total) | `77 / 5` (`82` total) | `79 / 5` (`84` total) | `71 / 5` (`76` total) |
| **Records Processed / Linked** | `191 / 156` | `171 / 113` | `192 / 160` | `139 / 34` |
| **Identifiers Detected (`report.json`)** | `1778` | `1510` | `1791` | `1177` |
| **Records Generalized / Suppressed** | `71 / 108` | `71 / 88` | `71 / 109` | `38 / 93` |
| **Runtime (`report.json`)** | `3.72 s` | `3.83 s` | `3.51 s` | `5.66 s` |
| **Personal Data Leaked (`check_dev.py`)** | `1 / 1263` (`0.1%`) | `0 / 1054` (`0.0%`) | `8 / 1269` (`0.6%`) | `265 / 1055` (`25.1%`) |
| **Canaries Leaked** | `0 / 4` | `0 / 4` | `0 / 4` | `9 / 16` |
| **Medical Values Preserved** | `410 / 426` (`96.2%`) | `399 / 406` (`98.3%`) | `416 / 429` (`97.0%`) | `148 / 163` (`90.8%`) |
| **Linking Precision / Recall / F0.5** | `1.00 / 0.71 / 0.93` | `1.00 / 0.54 / 0.86` | `1.00 / 0.77 / 0.94` | `1.00 / 0.12 / 0.40` |
| **Wrong Patient Merges** | `0` | `0` | `0` | `0` |
| **Raw Copies of Broken Files** | `0` | `0` | `0` | `0` |
| **k=1 on `(age_band, gender, district)`** | `25 / 33` (`75.8%`) | `24 / 26` (`92.3%`) | `21 / 32` (`65.6%`) | `2 / 13` (`15.4%`) |
| **A2/A4 Registry Attack (`conf >= 0.5`)** | `18.2%` (`4` unique) | `15.4%` (`1` unique) | `21.9%` (`4` unique) | `30.8%` (`1` unique) |

---

## 3. Raw Test Outputs (As-Is)

### 3.1 Dataset 1 — `Dataset_1_MultiHospital_Standard`

```text
files 83 sanitized 78 quarantined 5 records 191 linked 156
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 1 of 1263 pieces still visible (  0.1% leaked; lower is better)
   PATIENT_NAME     leaked    1 / 258    0.4%
   RELATIVE_NAME    leaked    0 / 119    0.0%
   ABHA_NUMBER      leaked    0 / 34     0.0%
   LANDMARK         leaked    0 / 14     0.0%
   DOB              leaked    0 / 97     0.0%
   PAN              leaked    0 / 10     0.0%
   PIN              leaked    0 / 102    0.0%
   EMAIL            leaked    0 / 8      0.0%
   PHONE            leaked    0 / 138    0.0%
   MRN              leaked    0 / 193    0.0%
   AADHAAR          leaked    0 / 64     0.0%
   INSURANCE_ID     leaked    0 / 10     0.0%
   VILLAGE          leaked    0 / 108    0.0%
   LOCALITY         leaked    0 / 22     0.0%
   HOUSE            leaked    0 / 86     0.0%
   by language: latin 0.1%, deva 0.0%, hinglish 0.0%
   by hiding place: content 0.1%, metadata 0.0%, filename 0.0%, header 0.0%, key 0.0%, base64 0.0%

2) CANARIES: 0 of 4 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 410 of 426 medical values survived ( 96.2%; higher is better)

4) PATIENT LINKING: precision 1.00, recall 0.71, F0.5 0.93  (pseudonyms that wrongly merge different people: 0)

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    PATIENT_NAME | latin | content | opd/pss_opd_2026.json | Subhash

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\Hp\.gemini\antigravity-cli\brain\b58ea862-bfc4-472d-9b62-13c03990c6a1\scratch\verify_out_1
============================================================
 Aegislash Risk & k-Anonymity Report (PII-free aggregates)
============================================================
Linked patient profiles (PSN) : 33
Unlinked records              : 35

1) Equivalence classes (age_band, gender, district):
   unique (k=1): 25 / 33 (75.8%) | k<5: 33 | min_k: 1 | median_k: 1.0

2) Equivalence classes (age_band, district, adm_week, diagnosis):
   unique (k=1): 33 / 33 (100.0%) | k<5: 33 | min_k: 1 | median_k: 1.0

3) Simulated registry attack (A2/A4):
   attacked: 33 | mean candidates: 13.6 | unique (k=1): 4 | est conf>=0.5: 18.2%
```

### 3.2 Dataset 2 — `Dataset_2_UnseenFormats_Hindi`

```text
files 82 sanitized 77 quarantined 5 records 171 linked 113
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 0 of 1054 pieces still visible (  0.0% leaked; lower is better)
   LOCALITY         leaked    0 / 11     0.0%
   AADHAAR          leaked    0 / 45     0.0%
   LANDMARK         leaked    0 / 9      0.0%
   HOUSE            leaked    0 / 68     0.0%
   EMAIL            leaked    0 / 10     0.0%
   RELATIVE_NAME    leaked    0 / 99     0.0%
   PHONE            leaked    0 / 118    0.0%
   INSURANCE_ID     leaked    0 / 10     0.0%
   PIN              leaked    0 / 82     0.0%
   VILLAGE          leaked    0 / 88     0.0%
   PAN              leaked    0 / 10     0.0%
   DOB              leaked    0 / 77     0.0%
   MRN              leaked    0 / 173    0.0%
   ABHA_NUMBER      leaked    0 / 21     0.0%
   PATIENT_NAME     leaked    0 / 233    0.0%
   by language: latin 0.0%, deva 0.0%, hinglish 0.0%
   by hiding place: content 0.0%, metadata 0.0%, filename 0.0%, header 0.0%, key 0.0%, base64 0.0%

2) CANARIES: 0 of 4 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 399 of 406 medical values survived ( 98.3%; higher is better)

4) PATIENT LINKING: precision 1.00, recall 0.54, F0.5 0.86  (pseudonyms that wrongly merge different people: 0)

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\Hp\.gemini\antigravity-cli\brain\b58ea862-bfc4-472d-9b62-13c03990c6a1\scratch\verify_out_2
============================================================
 Aegislash Risk & k-Anonymity Report (PII-free aggregates)
============================================================
Linked patient profiles (PSN) : 26
Unlinked records              : 58

1) Equivalence classes (age_band, gender, district):
   unique (k=1): 24 / 26 (92.3%) | k<5: 26 | min_k: 1 | median_k: 1.0

2) Equivalence classes (age_band, district, adm_week, diagnosis):
   unique (k=1): 26 / 26 (100.0%) | k<5: 26 | min_k: 1 | median_k: 1.0

3) Simulated registry attack (A2/A4):
   attacked: 26 | mean candidates: 17.7 | unique (k=1): 1 | est conf>=0.5: 15.4%
```

### 3.3 Dataset 3 — `Dataset_3_Adversarial_Chaos_Risk`

```text
files 84 sanitized 79 quarantined 5 records 192 linked 160
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 8 of 1269 pieces still visible (  0.6% leaked; lower is better)
   VILLAGE          leaked    3 / 109    2.8%
   DOB              leaked    3 / 97     3.1%
   PATIENT_NAME     leaked    2 / 259    0.8%
   INSURANCE_ID     leaked    0 / 10     0.0%
   EMAIL            leaked    0 / 6      0.0%
   PAN              leaked    0 / 10     0.0%
   ABHA_NUMBER      leaked    0 / 32     0.0%
   PIN              leaked    0 / 103    0.0%
   RELATIVE_NAME    leaked    0 / 119    0.0%
   AADHAAR          leaked    0 / 64     0.0%
   PHONE            leaked    0 / 138    0.0%
   MRN              leaked    0 / 194    0.0%
   LOCALITY         leaked    0 / 22     0.0%
   LANDMARK         leaked    0 / 20     0.0%
   HOUSE            leaked    0 / 86     0.0%
   by language: latin 0.6%, deva 1.1%, hinglish 0.0%
   by hiding place: content 0.7%, metadata 0.0%, filename 0.0%, header 0.0%, key 0.0%, base64 0.0%

2) CANARIES: 0 of 4 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 416 of 429 medical values survived ( 97.0%; higher is better)

4) PATIENT LINKING: precision 1.00, recall 0.77, F0.5 0.94  (pseudonyms that wrongly merge different people: 0)

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    VILLAGE | latin | content | registration/bkd_registration.csv | Ranipur
    VILLAGE | latin | content | registration/bkd_registration (1).csv | Ranipur
    DOB | latin | content | registration/knp_patients.tsv | 03-08-1936
    VILLAGE | deva | content | registration/knp_patients.tsv | रानीपुर
    DOB | latin | content | registration/bnd_legacy_export.csv | 08/03/1936
    DOB | latin | content | registration/bnd_legacy_export.csv | 08/03/1936
    PATIENT_NAME | latin | content | opd/bkd_opd_2026.json | Subhash
    PATIENT_NAME | latin | content | opd/knp_opd_2026.json | Subhash

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\Hp\.gemini\antigravity-cli\brain\b58ea862-bfc4-472d-9b62-13c03990c6a1\scratch\verify_out_3
============================================================
 Aegislash Risk & k-Anonymity Report (PII-free aggregates)
============================================================
Linked patient profiles (PSN) : 32
Unlinked records              : 32

1) Equivalence classes (age_band, gender, district):
   unique (k=1): 21 / 32 (65.6%) | k<5: 27 | min_k: 1 | median_k: 1.0

2) Equivalence classes (age_band, district, adm_week, diagnosis):
   unique (k=1): 32 / 32 (100.0%) | k<5: 32 | min_k: 1 | median_k: 1.0

3) Simulated registry attack (A2/A4):
   attacked: 32 | mean candidates: 7.8 | unique (k=1): 4 | est conf>=0.5: 21.9%
```

---

## 4. Detailed Observations (Datasets 1–3)

### 4.1 Strong Generalization Across Unseen Data
- **Zero contract failures & zero raw leaks of broken files:** Datasets 1–3 passed `validate_output.py` (`CONTRACT OK`). Every malformed/unsupported file (empty CSV, corrupt UTF-8, truncated JSON, 1500-deep JSON, XML, PDF, JPEG, mislabeled CSV) was cleanly quarantined (`5` quarantined per dataset; `0` copied raw).
- **Zero canary leaks (`0/4`) & zero hidden-channel leaks (`0.0%`):** Metadata (`_export_meta.source_path`), filenames (`Discharge_Summary_<Name>_<MRN>.txt`, `<phone>_report_*.json`), CSV headers (`ward_vitals_sheet.csv`), JSON keys (`patient_index.json`), and base64-encoded attachments (`scanned_consent_form.json`) were all caught cleanly across Datasets 1–3.
- **High clinical utility preservation (`96.2%–98.3%`):** Diagnoses, ICD-10 codes, medications, vitals, lab test names, and disease eponyms (*Addison's disease*, *Parkinson's disease*, *Huntington's disease*, etc.) survived across Datasets 1–3.
- **Zero false patient merges (`precision = 1.00`, `0` wrong merges):** Even with deliberate homonym pairs (patients sharing identical first and last names in different villages/families), Aegislash never falsely merged two distinct people.

### 4.2 Root Cause Analysis of Reported "Leaks" in Datasets 1 & 3 (`check_dev.py`)
Inspecting the actual sanitized output files revealed that **all 9 reported leak hits across Datasets 1 and 3 were benign collisions in `check_dev.py`'s substring checker rather than unredacted patient records**:
1. **`PATIENT_NAME: Subhash` (Dataset 1 `opd/pss_opd_2026.json` & Dataset 3 `opd/bkd_opd_2026.json`, `opd/knp_opd_2026.json`):**
   - The patient's own `patient_ref` and `notes` were properly replaced with `PSN-...`.
   - However, another visit in the same OPD JSON listed `"doctor": "Dr. Subhash Chandra (MS Orthopedics)"` (correctly exempted as a clinician name), and `check_dev.py` checks substring presence across the whole file.
2. **`VILLAGE: Ranipur / रानीपुर` (Dataset 3 `bkd_registration.csv`, `bkd_registration (1).csv`, `knp_patients.tsv`):**
   - Every row's `Village/Mohalla` / `Gaon` column was properly suppressed to `[VILLAGE]`.
   - The `Tehsil` column contained `"Mauranipur"` / `"मऊरानीपुर"`, and `"ranipur"` / `"रानीपुर"` matched as a literal substring of `"Mauranipur"` / `"मऊरानीपुर"`.
3. **`DOB: 08/03/1936` & `03-08-1936` (Dataset 3 `bnd_legacy_export.csv` & `knp_patients.tsv`):**
   - In `bnd_legacy_export.csv` (`MM/DD/YYYY`), `PSN-35F690`'s true DOB (`09/16/1936`) was date-shifted by `-44` days to `08/03/1936` (and `03-08-1936` in `knp_patients.tsv`), which happened to collide with the *unshifted* raw DOB (`08/03/1936`) of two other patients in the same file (whose own DOBs were shifted to `12/15/1936` and `05/20/1936`).

### 4.3 Real Model Gaps & Areas for Improvement
1. **Linkage Recall Drop on Unseen Headers & Devanagari Digits (Dataset 2):**
   - Linking recall dropped from `0.71` (Dataset 1) and `0.77` (Dataset 3) down to **`0.54`** in Dataset 2 (`113 / 171` records linked; `58` unlinked profiles in `risk_report.py`).
   - Cause: Dataset 2 uses unseen Hindi-transliterated CSV column names (`Patrak_Sankhya`, `Rogee_Naam`, `Janam_Dinank`, `Sampark_Sutra`), semicolon (`;`) delimiters in `cp1252` legacy CSV, `DD-Mon-YYYY` dates, and Devanagari-digit phone numbers (`९८७६५४३२१०`), reducing cross-hospital blocking matches.
   - **Actionable next step:** Expand `aegis/link/` blocking & `aegis/detect/` column/field normalization to handle Devanagari digits in phone/MRN extraction and unseen transliterated column headers.
2. **Higher Re-identification Risk on Small-Cell / Elderly / Rare-Disease Cohorts (Dataset 3):**
   - While k-anonymity triggered suppression (`records_suppressed = 109`, `80+` top-coding, `[DISTRICT]` suppression on small cells in `bkd_registration.csv`), simulated A2/A4 registry attack risk rose to **`21.9%` (`est conf>=0.5`)** with `mean candidates: 7.8` (vs. `13.6` in Dataset 1 and `17.7` in Dataset 2), because `Tehsil` (`Mauranipur`, `Karwi`, `Moth`, `Bindki`, `Naraini`) remained unredacted even when `[DISTRICT]` was suppressed.
   - **Actionable next step:** When `k < 5` triggers `[DISTRICT]` suppression in `aegis/privacy/engine.py`, also suppress or generalize the finer `Tehsil` column so `Tehsil` does not leak the suppressed district/location.

---

## 5. Dataset 4 — `Dataset_4_Adversarial_Breaker` (Red-Team Failure Test)

Designed specifically using realistic Indian healthcare patterns to stress-test Aegislash's detection, linkage, hidden-channel scanning, and privacy layers (`76` files, `167` records, `40` patients, `200` population, `141` required link units).

### 5.1 Raw Test Output (As-Is)

```text
files 76 sanitized 71 quarantined 5 records 139 linked 34
CONTRACT OK
================================================================
 SECRET WARDS practice self-check (rough guide, not the official score)
================================================================

1) PERSONAL DATA: 265 of 1055 pieces still visible ( 25.1% leaked; lower is better)
   PAN              leaked   71 / 71   100.0%
   MRN              leaked   50 / 115   43.5%
   PATIENT_NAME     leaked   45 / 227   19.8%
   PHONE            leaked   43 / 157   27.4%
   PIN              leaked   41 / 86    47.7%
   RELATIVE_NAME    leaked   12 / 99    12.1%
   HOUSE            leaked    1 / 41     2.4%
   VILLAGE          leaked    1 / 104    1.0%
   AADHAAR          leaked    1 / 58     1.7%
   INSURANCE_ID     leaked    0 / 12     0.0%
   DOB              leaked    0 / 60     0.0%
   EMAIL            leaked    0 / 1      0.0%
   ABHA_ADDRESS     leaked    0 / 24     0.0%
   by language: latin 29.4%, deva 0.0%, hinglish 79.2%
   by hiding place: content 24.3%, key 0.0%, filename 64.3%, base64 27.3%

2) CANARIES: 9 of 16 planted canaries found in your output folder (each one costs -3 officially)

3) MEDICAL DATA KEPT: 148 of 163 medical values survived ( 90.8%; higher is better)

4) PATIENT LINKING: precision 1.00, recall 0.12, F0.5 0.40  (pseudonyms that wrongly merge different people: 0)

5) RAW COPIES: 0 broken/unsupported files were copied out unchanged instead of quarantined (each costs -5 officially)

Example leaks (type, language, place, file, text):
    MRN | latin | content | registration/opaque_pipe_export.csv | 20265549
    PIN | latin | content | registration/opaque_pipe_export.csv | 205264
    PAN | latin | content | registration/opaque_pipe_export.csv | gxlpv2692s
    MRN | latin | content | registration/opaque_pipe_export.csv | 20266575
    PIN | latin | content | registration/opaque_pipe_export.csv | 205264
    PAN | latin | content | registration/opaque_pipe_export.csv | lqvpb8374s
    MRN | latin | content | registration/opaque_pipe_export.csv | 20268656
    PIN | latin | content | registration/opaque_pipe_export.csv | 209502
    PAN | latin | content | registration/opaque_pipe_export.csv | zfups1120d
    MRN | latin | content | registration/opaque_pipe_export.csv | 20261647
    PIN | latin | content | registration/opaque_pipe_export.csv | 205262
    PAN | latin | content | registration/opaque_pipe_export.csv | kzmpb1426p
    MRN | latin | content | registration/opaque_pipe_export.csv | 20261142
    PIN | latin | content | registration/opaque_pipe_export.csv | 209721
    PAN | latin | content | registration/opaque_pipe_export.csv | encps6716w
    MRN | latin | content | registration/opaque_pipe_export.csv | 20268042
    PIN | latin | content | registration/opaque_pipe_export.csv | 209502
    PAN | latin | content | registration/opaque_pipe_export.csv | nwgpu3805s
    MRN | latin | content | registration/opaque_pipe_export.csv | 20265164
    PIN | latin | content | registration/opaque_pipe_export.csv | 209721
    PAN | latin | content | registration/opaque_pipe_export.csv | bsjpk4547v
    MRN | latin | content | registration/opaque_pipe_export.csv | 20267007
    PIN | latin | content | registration/opaque_pipe_export.csv | 209721
    PAN | latin | content | registration/opaque_pipe_export.csv | levpu6458h
    MRN | latin | content | registration/opaque_pipe_export.csv | 20267628
    PIN | latin | content | registration/opaque_pipe_export.csv | 206245
    PAN | latin | content | registration/opaque_pipe_export.csv | qvmpk8279w
    MRN | latin | content | registration/opaque_pipe_export.csv | 20266676
    PIN | latin | content | registration/opaque_pipe_export.csv | 209732
    PAN | latin | content | registration/opaque_pipe_export.csv | gxcps4517p
    MRN | latin | content | registration/opaque_pipe_export.csv | 20269870
    PIN | latin | content | registration/opaque_pipe_export.csv | 209622
    PAN | latin | content | registration/opaque_pipe_export.csv | trfpb3734u
    MRN | latin | content | registration/opaque_pipe_export.csv | 20264536
    PIN | latin | content | registration/opaque_pipe_export.csv | 205264
    PAN | latin | content | registration/opaque_pipe_export.csv | jbcps1892q
    MRN | latin | content | registration/opaque_pipe_export.csv | 20265018
    PIN | latin | content | registration/opaque_pipe_export.csv | 205264
    PAN | latin | content | registration/opaque_pipe_export.csv | tqwpk4442b
    MRN | latin | content | registration/opaque_pipe_export.csv | 20264675

Next: fix the biggest leak rows first, keep the medical values, then link patients.
Also run: python3 validate_output.py --input dev/input --output C:\Users\Hp\.gemini\antigravity-cli\brain\b58ea862-bfc4-472d-9b62-13c03990c6a1\scratch\verify_out_4
============================================================
 Aegislash Risk & k-Anonymity Report (PII-free aggregates)
============================================================
Linked patient profiles (PSN) : 13
Unlinked records              : 105

1) Equivalence classes (age_band, gender, district):
   unique (k=1): 2 / 13 (15.4%) | k<5: 13 | min_k: 1 | median_k: 3.0

2) Equivalence classes (age_band, district, adm_week, diagnosis):
   unique (k=1): 13 / 13 (100.0%) | k<5: 13 | min_k: 1 | median_k: 1.0

3) Simulated registry attack (A2/A4):
   attacked: 13 | mean candidates: 8.8 | unique (k=1): 1 | est conf>=0.5: 30.8%
```

### 5.2 Confirmed Failure Modes Exposed
1. **100% Lowercase PAN Leak (`71 / 71`):** `PAN` regex in `aegis/detect/ids.py` only matches uppercase `[A-Z]{5}\d{4}[A-Z]`, so lowercase PANs (`gxlpv2692s`, `ywfpk4957p`) leaked across `registration/opaque_pipe_export.csv`, `lab/stream_export_jsonl.txt`, `billing/adversarial_claims.csv`, and clinical notes.
2. **9 / 16 Planted Canaries Leaked:**
   - In `notes/escalation_canaries.txt`, unseen labels (`caller=`, `dial=`) + lowercase names (`zulqarnain barua`, `hargobind khorana`) + slash-delimited phone numbers (`989/900/1122`, `978/800/2233`) bypassed detection completely.
   - In `misc/canary_key_trap.json`, the JSON key `"Firdaus Chagla"` under `"escalation_map"` leaked verbatim because `aegis/detect/engine.py` only scans JSON keys whose parent key starts with `"by_"`.
3. **27.3% Base64 & URL-Encoded Channel Leaks (`misc/consent_wrapped_b64.json`):**
   - `data:text/plain;base64,...` data URIs and 32/40-char line-wrapped base64 payloads bypassed `_b64_text()`'s `fullmatch` check, leaving patient name, phone, and Aadhaar decodable in output.
   - URL-encoded Windows path (`D%3A%5CHIS%5CRukhsana_Bhattacharya%5C[REDACTED].pdf`) left the patient's name intact.
4. **43.5% MRN, 47.7% PIN, 27.4% Phone, 19.8% Patient Name Leaks:**
   - Numeric-only MRNs (`20265549`) under unseen header `case_sheet_ref`, PINs under `dak_code`, slash/parenthesized mobiles (`(795) 633-0006`, `795/633/0006`) and STD landlines (`0568-2xxxxx`), `"organization"` parent key masking (`_NOT_PERSON` in `labels.py`), and `64.3%` filename leaks on lowercase/concatenated/Devanagari filenames.
5. **Linkage Collapse (`recall = 0.12`, `F0.5 = 0.40`, `105` unlinked records) & Elevated A2/A4 Risk (`30.8%`):**
   - Cross-script phonetic variations (`Shailendra` / `Sailendra` / `शैलेन्द्र`), Devanagari digits, unrecognized IDs, and opaque headers caused `88%` of required links to be missed while raising simulated A2/A4 registry attack risk to `30.8%`.
