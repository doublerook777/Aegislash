# Aegislash vs. Scrubadub: Detection Comparison, Multilingual Translation (Hindi & Hinglish), and Improvements

**Branch:** `detect/scrubadub-comparison`  
**Date:** 2026-11-26  
**Baseline Tool:** `scrubadub 2.0.1` (`en_IN` locale; default & full English detector suites + Hindi/Hinglish translation experiments)  
**Target System:** Aegislash ([`aegis/detect/`](../aegis/detect/)), evaluated across `dev` (200 files, 3,230 PII entities, 4,855 clinical probes), `dataset` (146 files, 1,951 PII entities, 995 clinical probes), and `tests/adversarial` (38 files, 157 PII entities, 50 clinical probes).

---

## 1. Executive Summary

We benchmarked Aegislash's deterministic rule-and-context detection engine (`aegis.detect.detect_file`) against Python's `scrubadub` (`2.0.1`) across three multi-format healthcare datasets (`CSV`, `TSV`, `JSON`, `FHIR R4`, free-text notes) spanning **English (`latin`)**, **Devanagari Hindi (`deva`)**, and **Hinglish (`hinglish`)**.

- **Why Scrubadub alone is insufficient for Indian clinical records:**
  - **Default Scrubadub** (`CredentialDetector`, `CreditCardDetector`, `EmailDetector`, `PhoneDetector`, `TwitterDetector`, `UrlDetector`) achieves only **30.6%–37.7%** PII recall (`3/4`–`6/8` canaries leaked) because it has no person-name, DOB, Aadhaar, ABHA, PAN, MRN, or Indian address/PIN detectors enabled by default.
  - **Full English Scrubadub** (+ `TextBlobNameDetector`, `DateOfBirthDetector`, `SkypeDetector`) increases recall to **60.6%–68.8%**, but `TextBlobNameDetector` (`NNP`/`NNPS` POS tagging with only `"skype"` in `disallowed_nouns`) destroys **51.6%–64.0% of clinical preserve probes** (redacting drugs like `Paracetamol`, `Metformin`, `Azithromycin`, disease eponyms like `Parkinson's disease` and `Guillain-Barré syndrome`, clinician titles `Dr. Meera Deshpande`, and UP districts) and reduces clean-document token retention to **64.7%–71.1%**.
  - **English-only barrier:** On Devanagari Hindi (`deva`), Scrubadub achieves only **4.2%–7.7%** recall (catching only ASCII numbers/emails embedded in Hindi text), and `DateOfBirthDetector(locale="hi_IN")` raises `ValueError: DateOfBirthDetector does not support language hi`.
- **Where Scrubadub exposed real gaps in baseline Aegislash (`main`):**
  Head-to-head error analysis revealed **16 entity misses** where Full English Scrubadub caught PII that baseline Aegislash missed (`2` in `dataset`, `14` in `tests/adversarial`), guiding concrete detection improvements translated across English, Hindi, and Hinglish.
- **Observed Impact on `detect/scrubadub-comparison`:**
  - **`dev`:** **0 / 3,230** leaked (**100.0%** detection recall), **0 / 4** canaries, **4,855 / 4,855 (100.0%)** detect-level medical kept (`4,496 / 4,497` end-to-end), linking **F0.5 = 1.00** (with LF-hash alignment for Windows CRLF checkout).
  - **`dataset`:** improved from **7 / 1,951** leaks (**1 / 4** canary) to **0 / 1,951** leaked (**100.0%** recall), **0 / 4** canaries, **978 / 995 (98.3%)** end-to-end medical kept (`100.0%` detect-level), linking **F0.5 = 0.99**.
  - **`tests/adversarial`:** improved from **21 / 157** leaks (**3 / 8** canaries, **86.6%** recall) to **0 / 157** true PII leaks (**0 / 8** canaries, **50 / 50 (100.0%)** detect-level medical kept, **44 / 46 (95.7%)** end-to-end medical kept, linking **F0.5 = 0.94** with LF-hash alignment).

---

## 2. Quantitative Comparison: Aegislash vs. Scrubadub

All configurations were evaluated on the exact parsed fields (`ParsedFile.records`: content, filenames, CSV headers, JSON keys, metadata, and decoded base64 leaves) against `truth.json`.

### 2.1 Overall Recall, Canaries, Clinical Preservation, Clean Retention, and Runtime

| Dataset | Model | Leaked / Total | Recall | Canaries Leaked | Medical Kept (Detect) | Clean Token Retention | Time (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| **`dev`** (3,230 PII) | `aegis_detect` (before) | 0 / 3,230 | 100.0% | 0 / 4 | 4,855 / 4,855 (100.0%) | 225 / 225 (100.0%) | 5.72 |
| | **`aegis_detect` (after)** | **0 / 3,230** | **100.0%** | **0 / 4** | **4,855 / 4,855 (100.0%)** | **225 / 225 (100.0%)** | **3.71** |
| | `scrubadub_default` (`en_IN`) | 2,013 / 3,230 | 37.7% | 3 / 4 | 4,855 / 4,855 (100.0%) | 225 / 225 (100.0%) | 0.39 |
| | `scrubadub_full_en` (`en_IN`) | 1,274 / 3,230 | 60.6% | 0 / 4 | 2,349 / 4,855 (48.4%) | 160 / 225 (71.1%) | 7.25 |
| | `scrubadub_hi_hinglish` (adapted) | 1,296 / 3,230 | 59.9% | 0 / 4 | 2,369 / 4,855 (48.8%) | 160 / 225 (71.1%) | 7.74 |
| **`dataset`** (1,951 PII) | `aegis_detect` (before) | 7 / 1,951 | 99.6% | 1 / 4 | 995 / 995 (100.0%) | 68 / 68 (100.0%) | 2.59 |
| | **`aegis_detect` (after)** | **0 / 1,951** | **100.0%** | **0 / 4** | **995 / 995 (100.0%)** | **68 / 68 (100.0%)** | **1.88** |
| | `scrubadub_default` (`en_IN`) | 1,224 / 1,951 | 37.3% | 3 / 4 | 995 / 995 (100.0%) | 68 / 68 (100.0%) | 0.22 |
| | `scrubadub_full_en` (`en_IN`) | 681 / 1,951 | 65.1% | 0 / 4 | 475 / 995 (47.7%) | 48 / 68 (70.6%) | 3.50 |
| | `scrubadub_hi_hinglish` (adapted) | 688 / 1,951 | 64.7% | 0 / 4 | 482 / 995 (48.4%) | 48 / 68 (70.6%) | 3.80 |
| **`tests/adversarial`** (157 PII) | `aegis_detect` (before) | 21 / 157 | 86.6% | 3 / 8 | 50 / 50 (100.0%) | 17 / 17 (100.0%) | 0.39 |
| | **`aegis_detect` (after)** | **1\* / 157** | **99.4%\*** | **0 / 8** | **50 / 50 (100.0%)** | **17 / 17 (100.0%)** | **0.28** |
| | `scrubadub_default` (`en_IN`) | 109 / 157 | 30.6% | 6 / 8 | 50 / 50 (100.0%) | 17 / 17 (100.0%) | 0.08 |
| | `scrubadub_full_en` (`en_IN`) | 49 / 157 | 68.8% | 1 / 8 | 18 / 50 (36.0%) | 11 / 17 (64.7%) | 0.37 |
| | `scrubadub_hi_hinglish` (adapted) | 48 / 157 | 69.4% | 1 / 8 | 18 / 50 (36.0%) | 11 / 17 (64.7%) | 0.38 |

> \*The single raw substring hit (`Meera Deshpande`) in `tests/adversarial` (`clinical_traps/trap_dense_note.txt`) is the preserved clinician string `Dr. Meera Deshpande`. Subtracting `preserve` occurrences (matching `check_dev.py` / `SCORING.md`) yields **0 / 157 leaked (100.0% recall)**.

### 2.2 Breakdown by Script (`latin` vs. `deva` vs. `hinglish`)

| Dataset | Model | `latin` Recall | `deva` Recall | `hinglish` Recall |
|---|---|---:|---:|---:|
| **`dev`** | `aegis_detect` (after) | **100.0%** (0/2,976) | **100.0%** (0/143) | **100.0%** (0/111) |
| | `scrubadub_default` | 38.5% (1,829/2,976) | 7.7% (132/143) | 53.2% (52/111) |
| | `scrubadub_full_en` | 61.6% (1,142/2,976) | 7.7% (132/143) | 100.0% (0/111) |
| **`dataset`** | `aegis_detect` (after) | **100.0%** (0/1,805) | **100.0%** (0/96) | **100.0%** (0/50) |
| | `scrubadub_default` | 38.3% (1,114/1,805) | 4.2% (92/96) | 64.0% (18/50) |
| | `scrubadub_full_en` | 67.4% (589/1,805) | 4.2% (92/96) | 100.0% (0/50) |
| **`tests/adversarial`** | `aegis_detect` (before) | 86.7% (20/150) | 83.3% (1/6) | 100.0% (0/1) |
| | **`aegis_detect` (after)** | **99.3%\*** (1\*/150) | **100.0%** (0/6) | **100.0%** (0/1) |
| | `scrubadub_full_en` | 70.0% (45/150) | 33.3% (4/6) | 100.0% (0/1) |

### 2.3 Observed Strengths & Weaknesses by Detector Type

- **Where Scrubadub outperformed baseline Aegislash:**
  - **`PHONE` (`0 / 308` on `dev`, `0 / 194` on `dataset`, `0 / 29` on `tests/adversarial`):** `phonenumbers.PhoneNumberMatcher` handled dotted `98.45.01.12.23`, slash-grouped, and URL-encoded `%2B91%207759130735` formats.
  - **`EMAIL` (`0 / 1`, `0 / 2`):** `EmailDetector` catches obfuscated `@` / `.` variants (`ramesh at gmail dot com`).
  - **Unlabeled / non-gazetteer `PATIENT_NAME`:** `TextBlobNameDetector` caught single-word names (`Satyendra`, `Devika`, `Priyanka`, `Rohan`), `Surname, Given` rows (`Radhika`, `Pranav`, `Pema`, `Choden`, `Agustín`), and non-gazetteer names (`Pema Choden`, `Agustín Fonseca`).
- **Where Scrubadub failed:**
  - **Indian IDs:** Missed ~95% of `AADHAAR`, `100%` of `AADHAAR_MASKED`, `76%–92%` of `ABHA_NUMBER`, `100%` of `PAN`, `60%–81%` of `MRN`, and `85%–100%` of `PIN`.
  - **DOB (`71%–82%` leaked):** `DateOfBirthDetector` requires `birth`/`born`/`dob` within `context_before=2`/`context_after=1` lines, skips ages `< 18` or `> 100` by default, and adds substantial latency via `dateparser.search_dates`.
  - **Filenames & CSV headers:** Missed `83%–90%` of filename PII and `50%–100%` of header PII.
  - **Clinical preservation:** Destroyed clinician names (`Dr. Meera Deshpande`), drugs (`Paracetamol`, `Metformin`, `Azithromycin`), disease eponyms (`Hashimoto's`, `Parkinson's`, `Cushing's`, `Addison's`, `Guillain-Barré`), staff names (`Mary Thomas`, `Anita Nair`), and district names.

---

## 3. Translating Scrubadub to Hindi & Hinglish (Experiment & Findings)

1. **Direct Locale & Context Adaptation (`scrubadub_hi_hinglish`):**
   - `DateOfBirthDetector(locale="hi_IN")` fails immediately with `ValueError: DateOfBirthDetector does not support language hi`.
   - Folding Devanagari digits (`०–९` -> `0–9`) via `fold()` allowed `PhoneDetector` to catch Devanagari mobile numbers (`मो. ९८४५०११२२३` -> `{{PHONE}}`).
   - Supplying translated Hindi/Hinglish `context_words` (`"जन्म"`, `"जन्मतिथि"`, `"जन्मदिन"`, `"पैदा"`, `"janam"`, `"janm"`, `"tarikh"`, `"dinank"`, `"paida"`) and relaxing `DateOfBirthFilth` age bounds (`0..120`) allowed `DateOfBirthDetector` to catch `"Janam tarikh 04-08-1979"` and `"जन्मतिथि 12/05/1984"`.

2. **Devanagari-to-Latin Transliteration into `TextBlobNameDetector`:**
   - **Lowercase transliteration (`to_latin`):** Scored **0%–7.0%** on `deva` because TextBlob's `PatternTagger` relies on English **TitleCase capitalization** for `NNP`.
   - **TitleCase-restoring transliteration (with Hindi stopword filtering):**
     - `hindi_1`: `"रोगी का नाम - लक्ष्मी अय्यर, जन्मतिथि 12/05/1984, निवासी ग्राम बेलापुर, मो. ९८४५०११२२३। पैरासिटामोल 500mg जारी।"` -> `rogi ka {{NAME}} - {{NAME}} {{NAME}}, {{NAME}} {{DATE_OF_BIRTH}}, {{NAME}} Gram {{NAME}}, {{NAME}}. {{PHONE}} {{NAME}} 500mg {{NAME}}`
     - `hinglish_1`: `"Shahid sahab ka BP 117/82. Janam tarikh 04-08-1979. Dr. Ramesh ne dekha. Attendant S/o Zubair ph 9876543210."` -> `{{NAME}} sahab ka {{NAME}} 117/82. {{NAME}} tarikh {{DATE_OF_BIRTH}}. Dr. {{NAME}} ne dekha. Attendant S/o {{NAME}} ph {{PHONE}}.`
   - **Takeaway:** Translating Scrubadub via transliteration recovers Hindi names and DOBs, but without clinical disallow-lists and protected spans it destroys drugs, vitals labels (`BP`), clinicians (`Dr.`), and common Hindi nouns. Therefore, we translated Scrubadub's underlying detection ideas into Aegislash's domain-safe architecture.

---

## 4. Features Implemented in Aegislash (`aegis/detect/`) Across English, Hindi & Hinglish

| # | Scrubadub Inspiration / Observed Gap | Improvement Implemented | EN / HI / Hinglish Support | File |
|---|---|---|---|---|
| 1 | **Obfuscated Email (`EmailDetector`)** | Added `EMAIL_OBF` for `user at domain dot tld` with TLD guard. | English & Hinglish prose (`dinesh at gmail dot com`). | [`aegis/detect/ids.py`](../aegis/detect/ids.py) |
| 2 | **Flexible Phone Grouping (`PhoneDetector`) & URL Hex Guard** | Added `98.45.01.12.23`, `989/900/1122`, `(795) 633-0006`, `dial`/`caller` cues, and `%` left boundary on `AADHAAR` so URL `%20`+phone is not misread as Aadhaar. | Combined with `fold()` for Devanagari digits and Hindi phone labels (`मोबाइल`, `फ़ोन`, `संपर्क`). | [`aegis/detect/ids.py`](../aegis/detect/ids.py) |
| 3 | **URL Query-Param & Path PII (`UrlDetector`)** | Added `find_url_pii()` for `key=value` parameters and `%3A`/`%5C`-encoded paths using `classify()` + `unquote_plus()`. | English (`patient=`), Hinglish (`naam=`), and UTF-8 percent-encoded Devanagari (`रोगी=`). | [`aegis/detect/names.py`](../aegis/detect/names.py) |
| 4 | **Zero-Width, Homoglyph & Diacritic Normalization** | Extended 1-to-1 `_FOLD` with Cyrillic/Greek look-alikes and Latin diacritics; added `strip_evasion_with_map()` to bridge zero-width chars while preserving Devanagari conjunct ZWJ/ZWNJ. | Exact offset mapping across Latin, Hinglish, and Devanagari. | [`aegis/detect/normalize.py`](../aegis/detect/normalize.py), [`aegis/detect/engine.py`](../aegis/detect/engine.py) |
| 5 | **Disallow-Listed Proper-Noun & Action-Cue Names (`TextBlobNameDetector`)** | Added `_ACTION_CUES` + `_FOLLOWUP_AND` for unlabeled 1–4 word names (`Satyendra discharged`, `given to Devika`, `Priyanka signed`, `Follow up with X and Y`, `called on`), plus `find_unlisted_person()`, guarded by `STOP \| MEDICAL \| ORG \| _PRONOUNS`. | Translated to **Hinglish** (`ko chhutti`, `ne sign kiya`, `aur <Name>`) and **Devanagari** (`को छुट्टी`, `ने हस्ताक्षर किए`, `और <Name>` with `(?![ऀ-ॿ])`). | [`aegis/detect/names.py`](../aegis/detect/names.py), [`aegis/detect/gazetteer.py`](../aegis/detect/gazetteer.py), [`aegis/detect/engine.py`](../aegis/detect/engine.py) |
| 6 | **DOB Context Cues (`DateOfBirthDetector`) & 4-Digit YOB** | Added `yob`/`birthYear` label support, 4-digit birth-year handling without poisoning exact-DOB linkage, and Hinglish/Hindi DOB cues (`janam dinank`, `janam tithi`, `जन्म...`). | English (`birthYear`, `X_YOB`), Hinglish (`janam tithi`), and Devanagari (`जन्मतिथि`, `जन्म_वर्ष`). | [`aegis/detect/labels.py`](../aegis/detect/labels.py), [`aegis/detect/fields.py`](../aegis/detect/fields.py), [`aegis/detect/dates.py`](../aegis/detect/dates.py), [`aegis/detect/engine.py`](../aegis/detect/engine.py) |
| 7 | **`Surname, Given`, Case-Insensitive PAN, & Hidden Channels** | Added `Surname, Given` parsing without comma truncation, case-insensitive `PAN`, `postal6`/`contactDigits` tokenization, export-path 5–8 digit MRNs, `_b64_filename_cands()`, underscore-split Devanagari filenames, and lowercase filename propagation. | Latin, Hinglish, and Devanagari filenames, export paths, and JSON keys. | [`aegis/detect/fields.py`](../aegis/detect/fields.py), [`aegis/detect/ids.py`](../aegis/detect/ids.py), [`aegis/detect/labels.py`](../aegis/detect/labels.py), [`aegis/detect/names.py`](../aegis/detect/names.py), [`aegis/detect/engine.py`](../aegis/detect/engine.py) |

---

## 5. Verification Summary

All tests passed after the final edit on branch `detect/scrubadub-comparison`:

- **`python -m aegis.detect.selftest`:** **89 / 89** line cases passed, **5 / 5** column tables passed, **6 / 6** JSON docs passed, and **2 / 2** filenames passed (`0` problems).
- **`python scripts/check_contracts.py`:** **13 / 13** contract checks passed.
- **`pytest aegis/`:** **18 / 18** unit tests passed (`test_link.py` + `test_privacy.py`).
- **End-to-end (`main.py` + `validate_output.py`):**
  - **`dev/input`:** `CONTRACT OK` (`200` files, `195` sanitized, `5` quarantined, `819` records, `776` linked), **0 / 3,230** leaks (with LF-hash alignment), **0 / 4** canaries, **4,496 / 4,497 (100.0%)** medical kept, linking **F0.5 = 1.00**.
  - **`dataset/input`:** `CONTRACT OK` (`146` files, `141` sanitized, `5` quarantined, `427` records, `402` linked), **0 / 1,951** leaks (`0.0%`), **0 / 4** canaries, **978 / 995 (98.3%)** medical kept, linking **F0.5 = 0.99**.
  - **`tests/adversarial/input`:** `CONTRACT OK` (`38` files, `37` sanitized, `1` quarantined, `46` records), **0 / 157** true leaks (with LF-hash alignment), **0 / 8** canaries, **44 / 46 (95.7%)** end-to-end medical kept (`50 / 50` detect-level), linking **F0.5 = 0.94**.

---

## 6. Post-Pull Verification (`origin/main` Merged at `111efa9`)

After pulling and merging `origin/main` (`a7faabf`, including PR #12 `detect/breaker-fixes` and PR #13 `test/adversarial-breaker-results`) into `detect/scrubadub-comparison` (`111efa9`):

- **`tests/breakers/breaker_ds1_io_formats` (`35` PII, `15` med):** `aegis_detect` **85.7%** recall (`5/35` leaked, `2/4` canaries, `15/15` med kept) vs. `scrubadub_full_en` **85.7%** recall (`5/35` leaked, `2/4` canaries, `9/15` med kept). Remaining Aegislash misses where Scrubadub caught PII: `Pradeep Joshi`, `Sakshi`.
- **`tests/breakers/breaker_ds2_detect_bypass` (`40` PII, `19` med):** `aegis_detect` **80.0%** recall (`8/40` leaked, `2/2` canaries, `19/19` med kept) vs. `scrubadub_full_en` **57.5%** recall (`17/40` leaked, `2/2` canaries, `8/19` med kept). Remaining misses where Scrubadub caught PII: `+91/9788/002233`, `Hargobind Khorana`, `Vasundhara Raje`, `Keshav Dev`, `Suresh Pandey`.
- **`tests/breakers/breaker_ds3_link_privacy` (`80` PII, `12` med):** `aegis_detect` **95.0%** recall (`4/80` leaked, `1/1` canary, `12/12` med kept, end-to-end linking F0.5 `0.71`) vs. `scrubadub_full_en` **51.2%** recall (`39/80` leaked, `1/1` canary, `6/12` med kept). Remaining misses where Scrubadub caught PII: `Pahari`, `Tindwari`.
