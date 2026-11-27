# io: ingest, export, orchestration (owner: Member-1)

Owns `main.py`, `raksha.toml`, and everything that touches files:
walk + decode (UTF-8/BOM/UTF-16/cp1252, invalid bytes), parse CSV/TSV/JSON/FHIR/text, quarantine
(xml, pdf, jpg, empty, truncated, 1,500-deep JSON, JSON behind `.csv`), split files into `Record`s
(`row:N`, JSON pointers, `doc`, plus one `@file` record for file name / header / keys / `_export_meta`),
apply findings right-to-left with `privacy.replace`, restore JSON types, keep FHIR a valid R4 Bundle,
rename PII file names, final leak gate, `report.json`, `records.jsonl`, determinism, time and memory.

Contracts it calls: [detect](../../contracts/detect.md), [link](../../contracts/link.md), [privacy](../../contracts/privacy.md). Shapes: [types](../../contracts/types.md).

Files: `decode.py` (bytes → text), `formats.py` (parse into Records, write back in the same
structure, base64 attachments and runs), `leakgate.py` (final scrub + verify), `pipeline.py` (orchestration,
report, records), `test_io.py` (unit and end-to-end tests with invented data). `main.py` is a thin entry point.

Check a change: `.venv/bin/python -m pytest -q aegis/io`, then the usual `main.py` + `validate_output.py` + `check_dev.py` run.

## Formats that hide their real shape (2026-11-26, from the breaker sets)
- **JSON Lines in a `.csv` / `.tsv` / `.txt`** (one JSON object per line). Read as CSV the first line becomes the header
  and every later line keeps its values. Now: a file whose non-blank lines (two or more) are all JSON objects is read as
  one record per line, `loc` = `row:N` (N counts non-blank lines), `fmt` = `json`, and is written back as one compact
  object per line. A `.csv` / `.tsv` whose first line is a JSON object but whose other lines are not is quarantined
  (`malformed_json_lines`): reading it as CSV would keep every value. A `.txt` like that stays plain text. Whole-file JSON
  behind `.csv` (one object, or pretty-printed) is handled as before. A `.json` file with several lines of objects is still
  `malformed_json` (quarantined), as before. A JSON Lines file with a `.jsonl` extension is still unsupported.
- **base64 values in JSON** (FHIR `data`, attachments). Decoded for detect when the whole string is base64 of readable
  UTF-8 in any of these layouts, and written back in the same layout: one line, wrapped over lines of equal length (`\n`
  or `\r\n`, with or without a final newline), behind a `data:<type>;base64,` prefix (padding may be missing there).
  Without a prefix a value must be at least 24 characters and padded, as before. Binary payloads (images), word lists
  and values cut at a wrong length are left alone.
- **base64 file names.** A stem that is base64 of readable text (padding left off, `-` `_` letters allowed, 16+
  characters) is shown to detect as the text it holds. If something is found, the output file is named from the
  sanitized text (not re-encoded base64); otherwise the original name is kept.
- **Leak gate.** Names are words split on anything that is not a letter, digit or Devanagari mark, so `Agustín_Fonseca`
  (a file name) is two words and also scrubs `Agustín Fonseca` in another file. A name learned as `Surname, Given` is also
  scrubbed as `Given Surname`. `%20`, `%5C`, `%2B` and the like count as separators when matching names and digit runs, so
  `Priyanka%20Sengupta` and `%2B91%209876543210` are caught in a file where detect missed them (detect itself reads URL
  escapes now; see its README).
- **Hidden payloads inside cells and running text (R2b).** Base64 *inside* a longer value (a CSV / TSV cell, a line of a
  `.txt`, part of a JSON string, a `data:...;base64,` URI in a sentence, a MIME-wrapped block in a note) is found by
  `formats.find_runs`. A run counts only when it decodes to readable UTF-8 that looks like writing (at least 8 characters,
  letters, digits, spaces and usual punctuation; at least 16 encoded characters; padding may be missing; `data:` URIs need
  8). Hashes, IDs, drug names, numbers and binary payloads (images) decode to noise and are never touched. `parse` then
  gives detect the value with every run replaced by one private-use character (U+E000...) and the run's text as an extra
  field of the same record (`path` = `<path>#b64:<n>`, same `kind` and `context`; additive, see `contracts/types.md`).
  Detect, the link evidence, the privacy plan and the leak gate treat that text like any other field, so a name or phone
  inside is found, replaced, and learned by the gate. `write` puts each run back: re-encoded in the same layout (prefix,
  padding, line width) when its text changed, the original characters when it did not (files without such runs, and runs
  without PII, are byte-identical). The whole-string JSON base64 handling above (FHIR `data`) is unchanged and runs first.
- **Escapes in text.** `\uXXXX` written out as text (not JSON-parsed), HTML entities (`&amp;`, `&#74;`) and `%XX` are read
  by detect and by the leak gate through `normalize.decode_view` (see the detect README); a hit is replaced as a whole.
- **Leak gate.** `scrub` and `contains_leak` work on that decoded view, so `Hector%20Pereira`, `Hector\u0020Pereira` and
  `&#72;ector Pereira` count as the name. The final check also decodes every base64 run in the output and quarantines the
  file when a learned name, phone or ID is still inside one.
- Still open: UTF-16 text inside base64; base64 in a header, a JSON key or a file name beyond the stem rule above; base64
  inside base64 (one layer is decoded); `\xNN` byte escapes and `U+0932` notation.

## Quarantine and leak-gate fixes from the audit (`report/vulnerability_audit_report.md`: V7, V8, V9, V11)
- **V8, binary files.** `decode()` looks for a NUL byte in the whole file, not only in the first 4 KB. A file with a NUL that is
  not UTF-16 (a binary trailer after byte 4,096) is quarantined as `undecodable_text` instead of exported with its bytes.
- **V7, deep JSON.** Nesting deeper than `MAX_JSON_DEPTH` (1,000 levels, counted without recursion) is quarantined as
  `json_too_deep`, for JSON and JSON Lines alike. The cap sits just above the 950 levels the practice sets expect to be read
  and below the 1,500-level bombs (the kit accepts either outcome for those). The audit suggested 256-500, which would
  quarantine a file the kit expects to be sanitized. JSON deeper than 64 levels is written without indentation: with
  `indent=2`, 950 levels grew from a few KB to 1.8 MB. Shallower JSON is written exactly as before.
- **V9, export metadata keys.** A top-level key is ignored when deciding what the file's subject is only when BOTH its
  key and its value describe the export (`_describes_export`): the key ends in an export word (`..._source`, `..._count`,
  `...Total`, `..._version`, `..._batch`) and the value is a count or a short code with no spaces (`HIS-Lucknow-Ward-3`).
  Then the `visits` array is split into one record per patient again. `batch_patient_name`, `source_patient_name`,
  `export_name`, or a name or long number under `patient_source`, still make the file one document: splitting such a file
  left the patient's first name or surname in the visit notes. When unsure the file stays one document.
- **V11, doctors in the leak gate.** A name that follows a doctor's title (`Dr.`, `Dr R.`, `Prof`, `डॉ.`) is not scrubbed by the
  gate, nor does it make `contains_leak` quarantine the file: detect already protects that span, and the gate used to turn
  `Dr. Suresh Pandey` into `Dr. [REDACTED]` whenever a patient had the same name. The same name elsewhere is still removed.
- **Checker note:** `check_dev.py` counts `Suresh Pandey` inside `Dr. Suresh Pandey` as a leak when a patient has that name.
  The official rule (`docs/kit/SCORING.md`, "allowed") does not. The numbers in the PR use the official rule.
- **V10 & LeakGate follow-up (2026-11-27):**
  - `decode()` also rejects files with high C0/DEL control-byte ratios outside `\n\r\t` (binary payloads without NUL bytes).
  - `_sniff_delimiter()` inspects up to 25 non-empty lines via `csv.reader`, picking a consistent multi-column body delimiter when its column count matches the header (preventing comma-in-header failures without misaligning mismatched headers).
  - `formats.write()` synchronizes FHIR `Bundle` `entry.fullUrl`, `resource.id` (FHIR-safe `[A-Za-z0-9\-\.]{1,64}`), and internal `reference` values (including `?query` / `#fragment` suffixes) whenever a resource ID is sanitized.
  - `LeakGate` now folds Cyrillic/Greek homoglyphs, strips zero-width characters and NFD combining marks via `detect.normalize.fold`/`visible`, supports up to 8-token names, and excludes UUIDs and ISO dates (`YYYY-MM-DD`) from 6-digit MRN suffix scrubbing.
  - `pipeline.run()` accurately counts `records_quarantined` (both `detect_error` and pass-2 quarantine) and rolls back `gate.hits` and per-file `entity_counts` if pass-2 export/leak-gate quarantines a file.
- Side effect, expected: a file that used to be exported and is now quarantined leaves its patient's cluster, and the patient
  key is a hash of the cluster's record ids (V13), so that one patient gets a new PSN and date shift. On `dev/input` this is
  the patient whose name and mobile sit at the bottom of `misc/deep_export.json`.
