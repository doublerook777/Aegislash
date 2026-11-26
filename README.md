# Aegislash: Privacy Firewall for Track 3 "Secret Wards"

Offline, CPU-only, LLM-free de-identification and re-identification risk firewall for multi-hospital Indian healthcare records across **English, Devanagari Hindi, and Hinglish** (CSV, TSV, JSON, FHIR R4 Bundles, and free-text notes; UTF-8/BOM, UTF-16, and cp1252).

> Plan & module ownership: [SPEC.md](SPEC.md) · Module contracts: [contracts/](contracts/) · Team conventions: [CONVENTIONS.md](CONVENTIONS.md)

## Setup & Usage

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# Run the pipeline (RAKSHA_SECRET must be set per release)
RAKSHA_SECRET=<secret> .venv/bin/python main.py --input dev/input --output out

# Verify output format & contract compliance (must print CONTRACT OK)
.venv/bin/python validate_output.py --input dev/input --output out

# Measure leaks, clinical utility preservation, and linkage F0.5 on practice data
.venv/bin/python check_dev.py --output out

# Measure k-anonymity equivalence classes & simulated A2/A4 registry linkage risk
.venv/bin/python scripts/risk_report.py --output out --registry dev/attacker/registry.csv

# Validate all in-process Python module contracts
.venv/bin/python scripts/check_contracts.py
```

## Architecture

Aegislash runs an in-memory, two-pass pipeline designed around four strict contract boundaries ([aegis/types.py](aegis/types.py)):

```text
Input tree (CSV / TSV / JSON / FHIR / TXT)
  │
  ▼
1. io (main.py, aegis/io/)
   Walks files deterministically, decodes UTF-8/BOM/UTF-16/cp1252, quarantines
   malformed or unsupported files (.xml, .pdf, .jpg, 1500-deep JSON), splits into Records
  │
  ▼
2. detect (aegis/detect/)
   Context-aware column/key classification, regex + checksum IDs, Latin/Devanagari/Hinglish
   name cues, clinical trap protection (doctors, doses, vitals, C/O complaints, eponyms),
   and hidden-channel scanning (headers, JSON keys, filenames, base64, \u escapes)
  │
  ▼
3. link (aegis/link/)
   Cross-script name normalization, strong-ID and name + second-clue blocking/clustering
   without transitive over-merge, keyed HMAC-SHA256 pseudonyms (PSN-XXXXXX)
  │
  ▼
4. privacy (aegis/privacy/, config/policy.yaml)
   Per-patient secret date shifting, truthful age bands, PIN/village generalization,
   k-anonymity & rare-condition small-cell suppression
  │
  ▼
Export: sanitized/ + report.json + records.jsonl (verified by final leak gate)
```

## How Each Part Works

- **Ingestion & Export (`io`):** Preserves input relative paths, CSV delimiters/headers, JSON key schemas/types, and valid FHIR R4 Bundle references; renames PII-containing filenames and declares mappings by `input_sha256` in `report.json`.
- **Detection (`detect`):** Combines header/key context with pattern + checksum rules (Aadhaar Verhoeff, ABHA, PAN, phone, MRN) and multilingual context cues (`S/o`, `D/o`, `W/o`, `ji`, `sahab`) while explicitly exempting medical values (`Dr. <name>`, `1-0-1`, `mg/dL`, `C/O <complaint>`).
- **Linkage & Pseudonyms (`link`):** Normalizes names across Latin, Devanagari, and Hinglish to link only on strong IDs or unique secondary clues, keeping homonyms apart. `aegis.link.pseudonym()` generates Crockford base32 `PSN-XXXXXX` tokens via `HMAC-SHA256(RAKSHA_SECRET, "psn|" + patient_key)`.
- **Privacy Layer (`privacy`):**
  - **Per-patient secret date shifting ([aegis/privacy/dates.py](aegis/privacy/dates.py)):** Computes a non-zero offset in `[-180, +180]` days via `HMAC-SHA256(RAKSHA_SECRET, "shift|" + key)` so all events of one patient (or unlinked record) shift together, preserving lengths of stay and visit intervals while preventing global-shift recovery and cross-release linkability. Preserves original formats (`DD/MM/YYYY`, `MM/DD/YYYY`, ISO datetimes with timezones, month-name dates, and Devanagari digits), failing closed to `[DATE]` if unparseable.
  - **Quasi-identifier generalization ([aegis/privacy/generalize.py](aegis/privacy/generalize.py)):** Converts ages into truthful 5-year bands (`48/M` -> `45-49/M`, `47 वर्ष` -> `45-49 वर्ष`) with `85+` top-coding for elderly patients; generalizes 6-digit PINs to `XXX***` and villages to district names.
  - **k-Anonymity & rare-condition defense ([aegis/privacy/engine.py](aegis/privacy/engine.py)):** Counts equivalence class sizes on `(age_band, gender, district)` and condition frequencies across the full dataset ([config/policy.yaml](config/policy.yaml)). Small cells (`k < 5`) trigger 10-year age widening and PIN/village suppression; rare conditions (`<= 3` profiles) in small cells trigger 20-year age widening (or `80+`) and district suppression while keeping diagnoses and ICD codes intact for clinical utility.

## Declared Models

**None.** Aegislash uses deterministic rules, gazetteers, checksums, and transliteration only (no LLMs, no generative AI, no pretrained transformers, and zero network calls during execution).

## Security Design

- **In-memory processing:** Raw PII is never written to temporary directories (`TMPDIR`, `HOME`), logs, or error messages.
- **Key separation & hygiene:** `RAKSHA_SECRET` is read from the environment only, domain-separated between pseudonyms (`psn|`) and date shifts (`shift|`), and never logged or written to output artifacts.
- **Fail-closed behavior:** Unknown finding types map to `[REDACTED]`; unparseable dates map to `[DATE]`; broken/unsupported files are quarantined rather than copied raw.
- **Determinism:** Records and profiles are processed in sorted order with no set-iteration ordering dependence, ensuring byte-identical outputs for identical inputs and secrets.

## Measured Results (`dev/input`, `main` integration)

| Metric | Measured Value | Source |
|---|---|---|
| Personal data leaked (overall / Hindi / Hinglish) | `1.1%` (`35/3230`; `latin 1.2%`, `deva 0.0%`, `hinglish 0.0%`; `content 0.0%`, `filename 72.9%`) | `check_dev.py` |
| Planted canaries leaked | `0 / 4` | `check_dev.py` |
| Medical values preserved | `100.0%` (`4496 / 4497`) | `check_dev.py` |
| Patient linking (precision / recall / F0.5) | `0.99 / 0.90 / 0.97` (`765 / 819` records linked, `1` wrong merge) | `check_dev.py` |
| Equivalence classes & A2/A4 / A5 risk | `35/49` unique on `(age_band, gender, district)`; A2/A4 est. `conf >= 0.5`: `32.7%`; A5 rare+narrow-QI hits: `0 / 18` | `scripts/risk_report.py` |
| Unseen-label self-test (perturbed headers/keys/labels) | `3.2%` leaked (`102/3230`), `0/4` canaries, `100.0%` medical kept (`4312/4313`); `38/38` `aegis.detect.selftest` | `check_dev.py` / `selftest.py` |
| Runtime & determinism | `6.05 s` (`200` files, `819` records); byte-identical repeat runs & secret-keyed unlinkability verified | `report.json` / 3-run check |
| Contracts & privacy unit tests | `13/13` contract cases passing; `6/6` `aegis/privacy/test_privacy.py` passing | `check_contracts.py` / `unittest` |

## Known Limitations

- All four modules (`io`, `detect`, `link`, `privacy`) are integrated on `main` (`1.1%` overall leak in `check_dev.py` driven by `35` filename leaks and `0.0%` content leaks; `100.0%` medical values kept; `0.97` linking F0.5). Some compact age strings (`54/F`, `97/M`, `Age: 0/F`) and filename tokens remain unflagged by `detect`, which elevates simulated A2/A4 registry uniqueness (`32.7%` est. `conf >= 0.5`).
- K-anonymity risk mitigation relies on `detect` emitting `CONDITION`, `DISTRICT`, `GENDER`, and `AGE` findings/evidence consistently across formats, including unseen layouts.
- Unlinked records that lack strong IDs or matching secondary clues receive per-record date shifts rather than cross-file patient shifts, preserving intra-record LOS but not cross-document intervals.
