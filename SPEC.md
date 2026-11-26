# Spec: Aegislash (Yugaantar DevForge, Track 3 "Secret Wards")

Freeze time: deadline minus 4 hours (about hour 20 of 24)
Submission deadline: about 24 hours after kickoff (exact clock time to be filled in)

## Problem
Hospitals in Yugaantar Pradesh are merging years of patient records (CSV, TSV, JSON, FHIR R4, text notes; English, Devanagari Hindi and Hinglish; UTF-8/BOM/UTF-16/cp1252) into one research database. We build "an offline, CPU-only, LLM-free privacy firewall that removes every piece of personal information, keeps every medically useful value exactly intact, recognizes the same patient across languages, files and hospitals without merging different people, and leaks nothing: not in outputs, logs, temp files or error messages." An automated attacker holding a voter-roll registry and known facts (visit date, hospital, rare condition, length of stay) must fail to re-identify patients in our output.

## Target user
A hospital data-governance team turning raw multi-hospital dumps into a research-safe release; graded by the organizers' evaluator and attacker on 3 hidden datasets (one with unseen names, labels and formats).

## Core demo flow
`RAKSHA_SECRET=practice python main.py --input dev/input --output out` reads every file, detects PII in fields and free text in all three scripts, links each patient's records to one `PSN-XXXXXX`, shifts dates per patient and generalizes quasi-identifiers, and writes `out/sanitized/`, `out/report.json`, `out/records.jsonl`. Then `validate_output.py` prints CONTRACT OK, `check_dev.py` shows leaks, canaries, medical values kept and linking F0.5, and `scripts/risk_report.py` shows our measured re-identification risk. Live demo: the nursing note "Shahid sahab ka BP 117/82 ... Mohd. Shahid - K/C/O addison's disease ... S/o Zubair" before and after.

## Scoring we optimise (kit docs/SCORING.md)
Privacy vs attacker 25 · Detection F2 20 · Clinical utility 20 · Identity resolution F0.5 15 · Integrity 10 · Speed/reliability 10. Penalties: −1 per leaked identifier (cap −25), −3 per canary (cap −15), −5 per raw copy of a broken file, −10 false success, −5 input modified. Organizer reference solution: ~80–85 normal, ~50 unseen-format. Kit starter as shipped: ~8.

## Scope
### Must-have
- Built on the kit's `starter/main.py` skeleton (already CONTRACT OK: deterministic walk, decoding, quarantine, report, records, HMAC pseudonym, date-shift and age-band helpers).
- Output contract per kit `docs/SPEC.md`: same paths/delimiter/header/JSON structure and types, UTF-8, FHIR stays a valid R4 Bundle with resolving references, PII file names renamed and declared, true counts, pseudonym written inside each exported record.
- Detection: context-aware column classification (header + values, works on unseen column names); regex/checksum IDs (phone all formats, Aadhaar + masked, ABHA number/address, UHID/MRN/IPD digit cores, insurance, PAN, PIN, email, DOB); names in Latin/Devanagari/Hinglish via label and context cues (Name:, honorifics, ji/sahab/didi/behenji, S/o D/o W/o, C/O-relative, Attendant), gazetteers + transliteration, propagation of names already found; hidden places (JSON keys, CSV headers, file names, export metadata, FHIR narrative, base64 attachments, `\u`-escaped Devanagari).
- Medical protection first: doses, `1-0-1`, BD/TDS x N days, vitals, labs with units, diagnoses/ICD, eponyms, `Dr. <name>`, `C/O <complaint>`, K/C/O, H/O, wards, ASHA; clean documents untouched.
- Linkage: strong ID → link; same name + a second clue (DOB, relative, village + age ±1) unique in dataset → link; otherwise `null`; cross-script names via transliteration; no transitive over-merge; homonyms kept apart.
- Privacy layer: per-patient secret date shift (all of a patient's intervals preserved), truthful 5-year age bands, PIN → 3-digit prefix, house/locality/landmark removed, village → tehsil/district, rare condition + small cell → coarser band or suppression; own k-anonymity count reported.
- Security: in-memory only, nothing in TMPDIR/HOME, stdout/stderr print counts only, exceptions logged by type, final leak gate scans every output (incl. report and file names) for every raw value detected and quarantines on a hit, `RAKSHA_SECRET` never written, byte-identical reruns (no set/dict-order dependence).
- Within 2 CPUs, 4 GB, target < 60 s and < 512 MB on practice data.
- README (setup, architecture, declared models: none) + 2-page brief PDF from `brief/PROJECT_BRIEF_TEMPLATE.md` with measured numbers.
### Nice-to-have (24h: pick at most one after must-haves pass)
- Unseen-format self-test: a script that renames columns/labels and swaps names in a copy of dev/input, to measure generalization.
- Simple re-implementation of the A2/A4 registry attack on our own output.
### Out of scope
- LLMs, generative models, transformers > 50M params, trained CRF (no time in 24h).
- Any network call during `run`; storing raw data on disk (so no encryption layer is needed; the brief explains the at-rest design).
- Memorized practice names/files; real patient data; a demo UI (before/after shown in terminal/editor).

## Tech decisions
- Language / framework: Python 3.10+ (organizer version unknown; dev 3.14), stdlib-first.
- Libraries: rapidfuzz, jellyfish, indic-transliteration (pinned in requirements.txt). Anything else needs team agreement.
- Database: none (in-memory).
- Data / tools: kit `dev/` practice set + `truth.json`, `validate_output.py`, `check_dev.py`, `check_submission.py`, copied into the repo.
- Hosting: none; organizers run `raksha.toml`.

## Modules and owners
Pipeline is two-pass: **read + detect everything → link all records → plan privacy for the whole dataset → rewrite + leak gate + write**. Nothing is written until pass 2.

| Module | Owner | Owns | Takes in | Hands out |
|---|---|---|---|---|
| `io` (ingest, export, orchestration) | Member-1 | `main.py`, `raksha.toml`, walking/decoding/parsing CSV-TSV-JSON-FHIR-text, quarantine, splitting files into records with `loc`, applying edits back into the same structure, FHIR validity, PSN injection, file renaming, final leak gate, `report.json`, `records.jsonl`, determinism, run-time/memory | input folder; findings from `detect`; patient keys from `link`; replacements from `privacy` | the `sanitized/` tree, report, records; `Record` objects to the other modules |
| `detect` (detection engine) | Member-2 | column/key classification, regex+checksum IDs, Latin/Devanagari/Hinglish name detection, gazetteers + transliteration, medical protection (meaning traps), hidden places (keys, headers, file names, base64, `\u` escapes), extraction of identity evidence | `Record` (fields with key/header context) and file names | `Finding`s (span, type, raw text) + `Evidence` per record |
| `link` (linkage + pseudonyms) | Member-3 | name normalization across scripts, blocking, matching rules, clustering without over-merge, homonym separation, canonical patient key, `PSN-` via HMAC | `Evidence` for every record in the dataset | `patient_key` (or `None`) per record |
| `privacy` (quasi-identifiers + measurement + brief) | Member-4 | per-patient date shift, age bands, DOB, PIN/village/locality generalization, rare-condition small-cell handling, `config/policy.yaml`, `scripts/risk_report.py` (k-anonymity / uniqueness), README + 2-page brief | QI findings (dates, ages, DOB, village, PIN, condition) + patient keys for the whole dataset | a privacy plan + the replacement text for each QI finding |

## Contracts
All boundaries are in-process Python calls (no HTTP). Shared shapes: contracts/types.md
- detect -> contracts/detect.md (Member-2 provides, Member-1 calls)
- link -> contracts/link.md (Member-3 provides, Member-1 calls, Evidence from Member-2)
- privacy -> contracts/privacy.md (Member-4 provides, Member-1 calls, Findings from Member-2)

Change rules:
- Adding a new optional field: no approval, add a note here.
- Changing or removing a field: both owners must sign off.
- After the freeze time: no changes unless the demo is broken without it; both owners plus a tiebreaker must agree.

## Conventions
See CONVENTIONS.md. Branches `<module>/<topic>`, commits `<module>: <change>`, edit only your own `aegis/<module>/`.
Layout: `main.py` (entry, io) · `aegis/{io,detect,link,privacy}/` · `aegis/types.py` (shared shapes, part of the contract) · `contracts/` (md + json + examples) · `scripts/check_contracts.py` · `config/policy.yaml` · `dev/` + `validate_output.py` + `check_dev.py` + `check_submission.py` (kit) · `docs/kit/` · `brief/`.

## Status
Planning stage: 5 approved

Assumptions:
- Project root `Aegislash/` becomes the public GitHub submission repo (origin already set by the team).
- Kit cloned from github.com/Reinforce-SST/Secret-Wards-ToolKit (MIT); starter code reuse is allowed as organizer-provided scaffolding.
- Rules + gazetteers + transliteration only (no CRF), custom linkage (no splink): chosen for the 24h window.
- Contract checker is a Python-call version of the hammer-skill HTTP checker (`--mock` adds exact example answers and mock-only error cases).
- Pseudonym HMAC input is prefixed `psn|` (domain separation from the date-shift key).
- Kickoff prompts for each member: KICKOFF.md.

| Module | Owner | Contract | State (mocked / in progress / real) | Last update |
|---|---|---|---|---|
| io | Member-1 | calls detect, link, privacy | real (`aegis/io/`); runs end-to-end on the 3 mocks, CONTRACT OK, READY TO SUBMIT | 2026-11-26 |
| detect | Member-2 | contracts/detect.md | real (`aegis/detect/`); next: generalisation to unseen formats | 2026-11-26 |
| link | Member-3 | contracts/link.md | mocked (`pseudonym` real) | 2026-11-26 |
| privacy | Member-4 | contracts/privacy.md | mocked | 2026-11-26 |

io notes (2026-11-26):
- Done: two-pass pipeline, decoding (BOM/UTF-16 incl. BOM-less/cp1252/corrupt UTF-8), CSV/TSV (delimiter sniff), JSON-behind-.csv, deep JSON, record splitting matching truth locators, base64 attachments, JSON type restore, key/header/file renames, leak gate, report/records. Verified with a truth-based fake detector (test only, not in repo): 0/3230 leaks, 4855/4855 medical kept, 0 structure mismatches, deterministic; 2,000 files in 1.7 s / 241 MB.
- Next: swap in real detect/link/privacy as they land; re-run `check_dev.py`.
- Contract notes (no shape change): (1) io decodes whole-string base64 JSON leaves (FHIR attachments) and gives detect the decoded text; it re-encodes on write. (2) `keys` passed to `privacy.plan` has no entries for `@file` records (link never sees them): use `keys.get`. (3) For single-document files, `@file` findings (file name) are passed to `privacy.replace` with the document's `record_id`, so the file name gets the patient's PSN. (4) A JSON top-level array counts as records only when its elements carry person fields (patient/uhid/name/...) and the top level has no subject of its own (matches truth locators).

detect notes (2026-11-26):
- Done: real engine; practice 0/3230 leaks, 0 canaries, 4855/4855 medical kept (link, privacy still mocked). Practice score is optimistic; own cases: `python -m aegis.detect.selftest`. Next steps: aegis/detect/README.md.
- Contract notes (no shape change): MRN `norm` is the digits only; evidence `gender` may be implied by S/o, D/o, W/o or an honorific. `check_contracts.py --mock` fails detect's mock-only "bad file" case by design.

## Open questions
Format: what I'm unsure about | why it matters | options | recommended default | owner to answer
- Exact deadline clock time | fixes the freeze time | give time | deadline − 4h | team
