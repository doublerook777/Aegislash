# Shared data shapes (used by every contract)

Status: approved. Owners: all four (changes follow the spec's change rules; a change here needs sign-off from every module that reads the shape).

All shapes are plain JSON-serializable dicts (`TypedDict` in `aegis/types.py`). Raw PII lives in these dicts **in memory only**: never print, log, pickle, or write them to disk.

## Record (made by `io`, read by `detect`, `privacy`)
| Field | Type | Notes |
|---|---|---|
| record_id | str | `"<input rel path>#<loc>"`, unique and stable across runs |
| file | str | input path relative to `{input}`, POSIX slashes |
| loc | str | `row:N` (0-based, header excluded) · RFC 6901 pointer `/visits/3` · `doc` · `@file` (file-level channels: file name, CSV header, JSON keys, export metadata) |
| fmt | str | `csv` · `tsv` · `json` · `fhir` · `text` |
| fields | list[Field] | in document order |

## Field
| Field | Type | Notes |
|---|---|---|
| path | str | unique inside the record. CSV: `col:<i>` · JSON leaf: pointer relative to file (`/visits/3/notes`) · JSON key: `key:<pointer of the object>/<key>` · CSV header cell: `header:<i>` · file name: `filename` · text doc: `text` · text inside a base64 run of another field: `<that field's path>#b64:<n>` (same `kind` and `context`; made by `io`, which puts the run back, re-encoded, on write) |
| kind | str | `value` · `key` · `header` · `filename` · `text` |
| context | str or null | the column header or JSON key above this value (`"Patient Name"`, `"patient_ref"`), lower-cased by nobody (raw) |
| value | str | the text to scan. Non-string JSON leaves (numbers) arrive as their JSON text (`"397205839628"`); `io` restores the type on write |

## Finding (made by `detect`)
| Field | Type | Notes |
|---|---|---|
| path | str | `Field.path` it was found in |
| start, end | int | character offsets into `Field.value`; `0 <= start < end <= len(value)`; findings in one field never overlap |
| type | str | one of the TYPES list below |
| text | str | `value[start:end]` |
| norm | str or null | normalized value: digits only for numeric IDs and PIN; ISO `YYYY-MM-DD` for DOB/DATE; integer string for AGE; casefolded Latin transliteration for names, village, condition |
| role | str or null | `patient` · `relative` · null |

TYPES
- Direct identifiers (always replaced): `PATIENT_NAME`, `RELATIVE_NAME`, `PHONE`, `AADHAAR`, `AADHAAR_MASKED`, `ABHA_NUMBER`, `ABHA_ADDRESS`, `EMAIL`, `MRN` (UHID/IPD/registration numbers), `PAN`, `INSURANCE_ID`, `HOUSE`, `LOCALITY`, `LANDMARK`, `OTHER_ID` (an identifier-looking value of unknown kind, including canaries).
- Quasi-identifiers (replacement decided by `privacy`): `DOB`, `DATE` (any clinical/event date or datetime), `AGE`, `VILLAGE`, `PIN`.
- Info only (never replaced unless `privacy` decides): `CONDITION` (diagnosis text or ICD code; feeds rare-value handling), `DISTRICT`, `GENDER`.

## Evidence (made by `detect`, read by `link`)
| Field | Type | Notes |
|---|---|---|
| record_id | str | |
| names | list[{text, norm, script, role, relation}] | `script`: `latin` · `deva` · `hinglish`; `role`: `patient` · `relative`; `relation`: `S/o` · `D/o` · `W/o` · `C/O` · null (for a relative: how they relate to the patient) |
| ids | list[{type, norm}] | strong identifiers of the patient only (PHONE, AADHAAR, ABHA_NUMBER, ABHA_ADDRESS, EMAIL, MRN, PAN, INSURANCE_ID) |
| dob | str or null | ISO |
| age | int or null | |
| gender | `M` · `F` · null | |
| village, district, pin | str or null | normalized |
| hospital | str or null | short code if known (`snj`, `jjh`, `asr`, `dhh`) |

## RecordResult (returned by `detect` per record)
`{record_id: str, findings: list[Finding], evidence: Evidence}`. `@file` records have `evidence` with empty lists and nulls.
