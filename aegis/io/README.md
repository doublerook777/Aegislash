# io: ingest, export, orchestration (owner: Member-1)

Owns `main.py`, `raksha.toml`, and everything that touches files:
walk + decode (UTF-8/BOM/UTF-16/cp1252, invalid bytes), parse CSV/TSV/JSON/FHIR/text, quarantine
(xml, pdf, jpg, empty, truncated, 1,500-deep JSON, JSON behind `.csv`), split files into `Record`s
(`row:N`, JSON pointers, `doc`, plus one `@file` record for file name / header / keys / `_export_meta`),
apply findings right-to-left with `privacy.replace`, restore JSON types, keep FHIR a valid R4 Bundle,
rename PII file names, final leak gate, `report.json`, `records.jsonl`, determinism, time and memory.

Contracts it calls: [detect](../../contracts/detect.md), [link](../../contracts/link.md), [privacy](../../contracts/privacy.md). Shapes: [types](../../contracts/types.md).

Files: `decode.py` (bytes → text), `formats.py` (parse into Records, write back in the same
structure, base64 attachments), `leakgate.py` (final scrub + verify), `pipeline.py` (orchestration,
report, records). `main.py` is a thin entry point.
