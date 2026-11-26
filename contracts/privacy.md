# Contract: privacy

Provider module: privacy (Member-4)
Consumer module: io (Member-1); reads `Finding`s produced by detect (Member-2) and keys from link (Member-3)
Status: approved

## Interface
- `aegis.privacy.plan(results: list[RecordResult], keys: dict[str, str | None]) -> Plan`: one call for the whole dataset after linking. Builds the per-patient date shifts, decides the generalization level per record (k-anonymity / rare-condition cells).
- `aegis.privacy.replace(plan: Plan, record_id: str, finding: Finding) -> Replacement`: the text `io` writes in place of one finding.
- `aegis.privacy.stats(plan: Plan) -> {"records_generalized": int, "records_suppressed": int}` for the report.

`Plan` is opaque to `io` (any object). `privacy` owns **every** replacement string, so the PSN, placeholders and generalized values are decided in one place.

## Input
| Field | Type | Required | Notes |
|---|---|---|---|
| results | list[RecordResult] | yes | every record of every file, sorted by `record_id` |
| keys | dict | yes | output of `link.resolve` |
| record_id, finding | str, Finding | yes | for `replace` |

## Output: Replacement
| Field | Type | Allowed values / range | Notes |
|---|---|---|---|
| text | str or null | | the new text; `null` = keep the original (allowed only for `CONDITION`, `DISTRICT`, `GENDER`) |
| status | str | `sanitized` · `generalized` · `suppressed` | |

Replacement rules that are part of the contract:
- `PATIENT_NAME`, `MRN` in a linked record → the record's pseudonym (`link.pseudonym(key)`), so the PSN appears inside the record. Unlinked → `[PATIENT]` / `[MRN]`.
- Other direct identifiers → `[TYPE]` (e.g. `[PHONE]`, `[RELATIVE]`). Never any part of the original.
- `DATE` / `DOB` → shifted by the patient's secret per-patient offset, **written in the same format as the original** (`12/04/1977` stays `DD/MM/YYYY`); unlinked record → a per-record offset. All dates of one patient move by the same amount.
- `AGE` → a band that contains the true age, same style as the original (`48` → `45-49`, `48/M` → `45-49/M`).
- `PIN` → 3-digit prefix + `***`; `VILLAGE` → district-level text or `[VILLAGE]`.
- Values that must keep their JSON type are returned as text and `io` restores the type where the schema allows; when it cannot (number field given a band), `io` writes the string and notes it.

## Errors
| Case | Status | Response |
|---|---|---|
| unknown `finding.type` | ok | `{"text": "[REDACTED]", "status": "sanitized"}` (fail closed) |
| a DATE whose format it cannot reproduce | ok | `{"text": "[DATE]", "status": "suppressed"}` |
| unknown `record_id` | raises `KeyError` | `io` treats it as a bug: quarantines that file |
| internal bug in `plan` | raises | `io` exits non-zero (no partial release) |

## Example request
```python
replace(plan, "registration/sanjeevani_registration.csv#row:0",
        {"path": "col:3", "start": 0, "end": 10, "type": "DOB", "text": "12/04/1977", "norm": "1977-04-12", "role": "patient"})
```

## Example response
```json
{"text": "03/07/1977", "status": "generalized"}
```

## Example error response
```json
{"text": "[REDACTED]", "status": "sanitized"}
```
(for a finding of an unrecognized type)

## Machine-readable version
contracts/privacy.contract.json (used by scripts/check_contracts.py). Created in stage 4 from this approved contract. If this file and the JSON ever disagree, fix the JSON to match this file.

## Change log
- 2026-11-26: drafted and approved by the team (stage 3).
