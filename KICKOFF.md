# Kickoff prompts

Each teammate starts a fresh Claude Code session in their clone of this repo and pastes their prompt.
Setup first: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.

## Member-1: io
You own the io module (ingest, export, orchestration: `main.py`, `aegis/io/`). Use the hammer-build skill. Read SPEC.md, contracts/types.md and the detect, link and privacy contracts. Build against the mocks. Do not touch other modules. If a question touches a contract, log it in Open questions instead of deciding alone.
First milestone: move the kit starter in `main.py` into `aegis/io/`, split every file into `Record`s (incl. the `@file` record), call `detect.detect_file` → `link.resolve` → `privacy.plan`/`replace`, and still print CONTRACT OK with the mocks. Then: FHIR stays valid R4, PII file names renamed, final leak gate, honest report counts.

## Member-2: detect
You own the detect module (`aegis/detect/`). Use the hammer-build skill. Read SPEC.md, contracts/types.md and the detect contract. Build against the mock. Do not touch other modules. If a question touches a contract, log it in Open questions instead of deciding alone.
First milestone: regex + checksum IDs and column classification by header and values, measured with `check_dev.py` (PERSONAL DATA by type, language and hiding place). Then names in Devanagari and Hinglish via context cues, the meaning traps, and hidden places. Never memorise practice names.

## Member-3: link
You own the link module (`aegis/link/`). Use the hammer-build skill. Read SPEC.md, contracts/types.md and the link contract. Build against the mock. Do not touch other modules. If a question touches a contract, log it in Open questions instead of deciding alone.
First milestone: strong-ID linking plus cross-script name normalisation, evaluated against `dev/truth/truth.json` (`patients`, `linkability`, `traps.homonym_pairs`) with a small script of your own, aiming for precision first (F0.5). Then name + second-clue rules and the over-merge split.

## Member-4: privacy
You own the privacy module (`aegis/privacy/`, `config/policy.yaml`, `scripts/risk_report.py`, README and brief). Use the hammer-build skill. Read SPEC.md, contracts/types.md and the privacy contract, plus docs/kit/ATTACKS.md. Build against the mock. Do not touch other modules. If a question touches a contract, log it in Open questions instead of deciding alone.
First milestone: per-patient secret date shift that keeps the original date format, truthful age bands, PIN prefix, and placeholders for every type. Then rare-condition / small-cell handling and a risk report you can quote in the brief.
