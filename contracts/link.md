# Contract: link

Provider module: link (Member-3)
Consumer module: io (Member-1), fed with `Evidence` produced by detect (Member-2). Owners on this boundary: Member-3 and Member-2 (Evidence shape), Member-1 (call site).
Status: approved

## Interface
- `aegis.link.resolve(evidence: list[Evidence]) -> dict[str, str | None]`: maps every `record_id` to a canonical **patient key** or `None` (do not link).
- `aegis.link.pseudonym(patient_key: str) -> str`: `"PSN-" + 6 Crockford base32 chars` from HMAC-SHA256 keyed with `RAKSHA_SECRET`.

Called once, after `detect` has run on every file, with the evidence of **every** non-`@file` record in the dataset.

## Input
| Field | Type | Required | Notes |
|---|---|---|---|
| evidence | list[Evidence] | yes | sorted by `record_id` by the caller |

## Output
| Field | Type | Allowed values / range | Notes |
|---|---|---|---|
| (dict) | dict[record_id → str or null] | one entry per input record | |
| patient key | str | opaque, deterministic, independent of input order | must not contain raw PII if ever logged; never written to output (only its pseudonym is) |
| pseudonym | str | regex `^PSN-[0-9A-HJKMNP-TV-Z]{6}$` | same key + same secret → same value; different secret → different value |

Linking rules that are part of the contract:
- Link on a shared strong identifier, or same name (cross-script normalized) **plus** a second clue (DOB, relative name, or village + age ±1) that is unique in the dataset.
- Otherwise `None`. A wrong link costs more than a missed one.
- No transitive over-merge: a cluster that would contain two different DOBs or two different strong IDs of the same type is split back.

## Errors
| Case | Status | Response |
|---|---|---|
| empty list | ok | `{}` |
| record with no usable evidence | ok | that record maps to `None` |
| `RAKSHA_SECRET` missing or empty | raises `RuntimeError("secret_missing")` | `io` exits non-zero with the message `secret_missing` (never a false success) |
| internal bug | raises | `io` falls back to `None` for every record, logs only the exception type, keeps going |

## Example request
```json
[
  {"record_id": "notes/nn_01.txt#doc", "names": [{"text": "Shahid", "norm": "shahid", "script": "hinglish", "role": "patient", "relation": null}, {"text": "Zubair", "norm": "zubair", "script": "hinglish", "role": "relative", "relation": "S/o"}], "ids": [], "dob": null, "age": null, "gender": "M", "village": null, "district": null, "pin": null, "hospital": "asr"},
  {"record_id": "registration/arogya_legacy_export.csv#row:4", "names": [{"text": "Shahid Mohammad", "norm": "shahid mohammad", "script": "latin", "role": "patient", "relation": null}, {"text": "Zubair Mohammad", "norm": "zubair mohammad", "script": "latin", "role": "relative", "relation": "S/o"}], "ids": [{"type": "MRN", "norm": "010607"}], "dob": "1961-03-02", "age": 64, "gender": "M", "village": "bilgram", "district": "hardoi", "pin": "241301", "hospital": "asr"},
  {"record_id": "opd/x.json#/visits/0", "names": [], "ids": [], "dob": null, "age": null, "gender": null, "village": null, "district": null, "pin": null, "hospital": null}
]
```

## Example response
```json
{
  "notes/nn_01.txt#doc": "k:7f3a",
  "registration/arogya_legacy_export.csv#row:4": "k:7f3a",
  "opd/x.json#/visits/0": null
}
```
`pseudonym("k:7f3a")` with `RAKSHA_SECRET=practice` → e.g. `"PSN-7Q2K9D"`.

## Example error response
`RAKSHA_SECRET` unset → `RuntimeError: secret_missing`; stderr shows `error: secret_missing`, exit code 2.

## Machine-readable version
contracts/link.contract.json (used by scripts/check_contracts.py). Created in stage 4 from this approved contract. If this file and the JSON ever disagree, fix the JSON to match this file.

## Change log
- 2026-11-26: drafted and approved by the team (stage 3).
