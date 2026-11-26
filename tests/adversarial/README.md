# Adversarial & Stress-Test Suite for Aegislash

Red-team evaluation dataset (`raksha-dataset/1` and `raksha-truth/1` format) designed to expose edge cases and failure modes across `io`, `detect`, `link`, and `privacy`.

## Contents

- `generate_adversarial.py`: Deterministic generator (`--seed 9991337`)
- `input/`: `38` adversarial files (`51` records, `24` patients, `8` canaries) across 10 folders:
  - `unseen_schema/`: Cryptic/abbreviated CSV headers (`P_NOM`, `K_SUP`, `X_YOB`, `Z_6D`, `PAT_TEL_1`, `AADH_NO`), `Surname, Given` order, pipe delimiter, BOM-less `UTF-16LE`, unfamiliar camelCase JSON keys (`postal6`, `birthYear`, `contactDigits`), and custom extension URLs.
  - `evasion/`: Zero-width joiners/spaces (`\u200b`, `\u200d`), Cyrillic homoglyphs (`а`, `е`), URL-encoded query parameters, `\uXXXX`-escaped Devanagari, and base64 under non-standard keys.
  - `narrative_leaks/`: Unlabeled one-word names, non-gazetteer/accented names, Devanagari numeral phones, and unfamiliar MRN/CR/NICU formats.
  - `hidden_channels/`: Accented, Devanagari, and base64-encoded filenames; phone-keyed JSON objects.
  - `clinical_traps/`: Doctor names without `Dr.` alongside patient homonyms, `C/O <complaint>` vs `c/o <relative>`, eponyms, staff/hospital names, and large lab/billing integers.
  - `linkage_traps/`: Triple homonym (`Sunil Verma` ×3), transitive-merge chain attack (`Ramesh Kumar` + `Suresh Kumar` with distinct DOB/phone), cross-script `Mohammad`/`Mohd.`/`मोहम्मद` linkage, and ambiguous fragmentary notes.
  - `privacy_traps/`: Extreme ages (`0/F`, `97/M`, `102/F`, `94/M`, `89/F`) with rare conditions, leap day (`29/02/2024`), Devanagari dates, and partial dates.
  - `canaries/`: `8` synthetic canary identities across base64 arrays, JSON keys, CSV headers, filenames, `\u`-escaped strings, zero-width obfuscation, accented text, and semicolon CSVs.
  - `io_traps/`: Ragged `cp1252` semicolon CSV, FHIR `Binary` resource with base64 PII, `1500`-deep JSON, JSON behind `.tsv`, zero-byte `.json`, and invalid UTF-8 bytes.
  - `clean/`: PII-free clinical protocol file.
- `truth/truth.json`: Ground-truth entities, preserved clinical values, dates, quasi-identifiers, and linkage labels.
- `attacker/`: `registry.csv` (`120` population members) and `known_facts.jsonl` (rare-condition targets + `10` decoys).
- `dataset_manifest.json`: Counts and SHA-256 hashes.

## Run Against Aegislash

```powershell
cd C:\Users\LOQ\Desktop\yugantar\repo\Aegislash
$env:RAKSHA_SECRET = "practice"
.venv\Scripts\python.exe main.py --input tests\adversarial\input --output out_adv
.venv\Scripts\python.exe validate_output.py --input tests\adversarial\input --output out_adv
.venv\Scripts\python.exe check_dev.py --output out_adv --truth tests\adversarial\truth\truth.json --show 50
.venv\Scripts\python.exe scripts\risk_report.py --output out_adv --registry tests\adversarial\attacker\registry.csv
```

## Baseline Measured Results (`9b92af4`)

- `validate_output.py`: `CONTRACT OK`
- `check_dev.py`: `19 / 157` (`12.1%`) leaked (`PATIENT_NAME 26.5%`, `DOB 28.6%`, `PIN 7.1%`, `PHONE 3.4%`, `filename 40.0%`), `3 / 8` canaries leaked, `48 / 50` (`96.0%`) medical values kept (including `Dr. Meera Deshpande` redacted in `clean/protocol.txt`), linking precision `1.00`, recall `0.62`, F0.5 `0.89`.
