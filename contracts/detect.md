# Contract: detect

Provider module: detect (Member-2)
Consumer module: io (Member-1)
Status: approved

## Interface
`aegis.detect.detect_file(records: list[Record]) -> list[RecordResult]`

Called once per parsed input file, with **all** records of that file (including its `@file` record), so column-level classification and date-order inference (day-first vs month-first) can use every row. Shapes: [types.md](types.md).

## Input
| Field | Type | Required | Notes |
|---|---|---|---|
| records | list[Record] | yes | all from the same `file`, in document order; the `@file` record first |

## Output
| Field | Type | Allowed values / range | Notes |
|---|---|---|---|
| (list) | list[RecordResult] | same length and order as input | one result per record |
| findings[].type | str | TYPES in types.md | |
| findings[].start/end | int | inside the field value, non-overlapping | `io` applies them right-to-left |
| evidence | Evidence | | empty lists / nulls when nothing is known |

Behaviour that is part of the contract:
- Medical values (doses, `1-0-1`, vitals, labs, diagnoses, eponyms, `Dr. <name>`, `C/O <complaint>`, wards) are **never** returned as direct-identifier findings.
- Deterministic: same input → same output, same order (no set iteration).
- Pure: no printing, logging, file or network access.

## Errors
| Case | Status | Response |
|---|---|---|
| empty list | ok | returns `[]` |
| a field it cannot interpret | ok | no findings for that field (never raises for content) |
| internal bug (any exception) | raises | `io` catches it, quarantines the whole file with reason `detect_error`, logs only the exception type |

## Example request
```json
[
  {"record_id": "notes/nn_01.txt#@file", "file": "notes/nn_01.txt", "loc": "@file", "fmt": "text",
   "fields": [{"path": "filename", "kind": "filename", "context": null, "value": "nn_01.txt"}]},
  {"record_id": "notes/nn_01.txt#doc", "file": "notes/nn_01.txt", "loc": "doc", "fmt": "text",
   "fields": [{"path": "text", "kind": "text", "context": null,
     "value": "Shahid sahab ka BP 117/82. Dr. Ramesh ne dekha. Attendant (S/o Zubair) ph 9876543210."}]}
]
```

## Example response
```json
[
  {"record_id": "notes/nn_01.txt#@file", "findings": [],
   "evidence": {"record_id": "notes/nn_01.txt#@file", "names": [], "ids": [], "dob": null, "age": null,
                "gender": null, "village": null, "district": null, "pin": null, "hospital": null}},
  {"record_id": "notes/nn_01.txt#doc",
   "findings": [
     {"path": "text", "start": 0, "end": 6, "type": "PATIENT_NAME", "text": "Shahid", "norm": "shahid", "role": "patient"},
     {"path": "text", "start": 63, "end": 69, "type": "RELATIVE_NAME", "text": "Zubair", "norm": "zubair", "role": "relative"},
     {"path": "text", "start": 74, "end": 84, "type": "PHONE", "text": "9876543210", "norm": "9876543210", "role": "patient"}
   ],
   "evidence": {"record_id": "notes/nn_01.txt#doc",
     "names": [{"text": "Shahid", "norm": "shahid", "script": "hinglish", "role": "patient", "relation": null},
               {"text": "Zubair", "norm": "zubair", "script": "hinglish", "role": "relative", "relation": "S/o"}],
     "ids": [{"type": "PHONE", "norm": "9876543210"}],
     "dob": null, "age": null, "gender": "M", "village": null, "district": null, "pin": null, "hospital": null}}
]
```
Note: "Ramesh" after "Dr." is not a finding.

## Example error response
Exception raised by `detect_file` → `io` writes for that file in `report.json`:
```json
{"input_sha256": "51aa…", "output": null, "status": "quarantined", "reason": "detect_error"}
```

## Machine-readable version
contracts/detect.contract.json (used by scripts/check_contracts.py). Created in stage 4 from this approved contract. If this file and the JSON ever disagree, fix the JSON to match this file.

## Change log
- 2026-11-26: drafted and approved by the team (stage 3).
