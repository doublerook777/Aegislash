# Aegislash: Context-Aware, Two-Pass Privacy Firewall for Multilingual Healthcare Records

**Track 3 · Secret Wards** · Team: Aegislash (Member-1 `io`, Member-2 `detect`, Member-3 `link`, Member-4 `privacy`) · Repo: `Aegislash`

## 1. In one paragraph

Aegislash is an offline, CPU-only, LLM-free privacy firewall that de-identifies heterogeneous multi-hospital records across English, Devanagari Hindi, and Hinglish without destroying clinical value. Unlike naive regex scrubbers that miss cross-script names, leak PII in side channels, or redact dosages and doctor names, Aegislash separates **detection**, **cross-document identity resolution**, and **dataset-wide privacy planning** into a deterministic two-pass pipeline: it protects medical entities (`Dr.`, vitals, `1-0-1`, ICD codes), links records via HMAC-SHA256 pseudonyms without over-merging homonyms, shifts all dates per patient with a keyed secret offset, and applies targeted k-anonymity/rare-condition coarsening only to high-risk cells.

## 2. Architecture

```text
Input Files (CSV, TSV, JSON, FHIR R4, TXT; UTF-8/BOM, UTF-16, cp1252)
  │
  ▼  [1. io: ingest & quarantine]
Records (+ @file channel for headers, JSON keys, filenames, metadata)
  │
  ▼  [2. detect: multilingual PII + medical trap protection]
Findings + Identity Evidence
  │
  ▼  [3. link: cross-script blocking & clustering]
Canonical Patient Keys -> HMAC-SHA256 Pseudonyms (PSN-XXXXXX)
  │
  ▼  [4. privacy: dataset-wide k-anonymity plan & replacement]
Per-patient date shifts, age bands, PIN/village generalization, rare-cell coarsening
  │
  ▼  [5. io: rewrite, FHIR repair, leak gate]
sanitized/  +  report.json  +  records.jsonl
```

## 3. How it works

- **Ingestion (`io`):** Walks the input tree in deterministic sorted order, decodes UTF-8/BOM/UTF-16/cp1252 into UTF-8, quarantines unsupported or malformed files (`.xml`, `.pdf`, `.jpg`, truncated or 1,500-deep JSON), repairs FHIR R4 Bundle references, renames PII filenames, and enforces a final leak gate before writing.
- **Detection (`detect`):** Uses context-aware column/key classification, regex + checksum validation (Aadhaar Verhoeff, ABHA, PAN, phone, MRN), and Latin/Devanagari/Hinglish cue rules (`S/o`, `W/o`, `ji`, `sahab`) while protecting medical traps (`Dr.`, `C/O <complaint>`, `1-0-1`, eponyms). Scans hidden channels including JSON keys, CSV headers, filenames, base64 payloads, and `\u` escapes.
- **Linkage & pseudonyms (`link`):** Normalizes names across scripts via transliteration, links on strong IDs or unique secondary clues (DOB, relative, village + age ±1), splits conflicting clusters to avoid homonym merges, and generates `PSN-XXXXXX` via `HMAC-SHA256(RAKSHA_SECRET, "psn|" + key)`.
- **Privacy layer (`privacy`):** Shifts dates per patient (or per unlinked record) by a non-zero keyed offset in `[-180, +180]` days (`HMAC-SHA256(RAKSHA_SECRET, "shift|" + key)`) preserving original date/datetime formats and exact stay intervals. Generalizes ages into 5-year bands (`85+` top-coding), PINs to `XXX***`, and villages to districts; enforces k-anonymity (`k >= 5`) and rare-condition (`<= 3` profiles) protection by widening ages (10/20-year) and suppressing PIN/village/district on rare cells while keeping clinical diagnoses intact.
- **Security:** Processes all PII strictly in memory with zero temp files or PII logging; uses domain-separated HMAC keys (`psn|` vs `shift|`) from `RAKSHA_SECRET`; fails closed (`[REDACTED]` / `[DATE]` / quarantine); executes deterministically with no network calls.

## 4. USP

- **Targeted rare-condition defense:** Coarsens quasi-identifiers (`AGE`, `PIN`, `VILLAGE`, `DISTRICT`) *only* on small k-anonymity cells and rare-diagnosis profiles, defeating A5 targeted attacks (e.g., "97-year-old with rare condition") without distorting dataset-wide ICD-10 statistics.
- **Format-faithful temporal privacy:** Preserves `DD/MM/YYYY`, `MM/DD/YYYY`, ISO datetimes with timezones, month-name dates, and Devanagari digits alongside exact intra-patient intervals and lengths of stay.
- **Keyed cross-release unlinkability:** Changing `RAKSHA_SECRET` rotates both `PSN-XXXXXX` identifiers and every patient's date shift offset.

## 5. Privacy–utility trade-off (measured on the practice data)

| Measure | Value |
|---|---|
| personal data leaked (overall / Hindi / Hinglish) | `1.1%` (`35/3230`; `latin 1.2%`, `deva 0.0%`, `hinglish 0.0%`; `content 0.0%`, `filename 72.9%`, `0/4` canaries) |
| medical values kept | `100.0%` (`4496/4497`) |
| linking precision / recall / F0.5 | `0.99 / 0.90 / 0.97` (`765/819` records linked, `1` wrong merge) |
| re-identification risk (`scripts/risk_report.py`) | `35/49` (`71.4%`) unique on `(age_band, gender, district)`; `49/49` on `(age_band, district, adm_week, diagnosis)`; A2/A4 est. `conf >= 0.5`: `32.7%` (`10` unique / `240` registry); A5 rare+narrow-QI hits: `0/18` |
| run time / peak memory | `6.05 s` (`dev/input`, 200 files, 819 records; Windows RSS fallback `0.0 MB`; byte-identical repeat runs & secret-keyed unlinkability verified) |
| on data you did not tune on | `3.2%` leaked (`102/3230`), `0/4` canaries, `100.0%` medical kept (`4312/4313`) on a perturbed-label copy of `dev/input`; `38/38` `aegis.detect.selftest` cases passing |

By tuning `config/policy.yaml` (`age_band_years: 5`, `date_shift_max_days: 180`, `min_group_size: 5`, `rare_condition_threshold: 3`), standard patients retain 5-year age resolution, district geography, 3-digit PIN prefixes, and exact stay intervals, while only rare/small-cell patients sacrifice fine location and narrow age bands to block registry and known-facts re-identification.

## 6. Known limitations

- **Filename PII & compact age/sex detection gaps:** Current `check_dev.py` & `risk_report.py` runs show `35` filename-channel leaks (`MRN`/`PATIENT_NAME`/`PHONE` in filenames) and some unbanded compact ages (`54/F`, `97/M`, `Age: 0/F`) not yet emitted by `detect`, raising A2/A4 registry uniqueness (`32.7%` `conf >= 0.5`).
- **Unlinked fragmentation:** Fragmentary notes that cannot be safely linked receive per-record date shifts rather than patient-level shifts, preserving intra-note intervals but not cross-document timelines.
- **No encryption-at-rest layer:** Designed as a stateless in-memory pipeline; long-term archival of raw source dumps requires external encrypted storage with KMS-managed `RAKSHA_SECRET`.
