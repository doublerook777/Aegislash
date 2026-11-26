# privacy: quasi-identifiers, measurement, write-up (owner: Member-4)

Owns every replacement string: PSN for linked names/MRNs, `[TYPE]` placeholders, per-patient secret
date shifts in the original format, truthful age bands, PIN prefix, village generalization,
rare-condition / small-cell handling (k-anonymity), `config/policy.yaml`. Also owns
`scripts/risk_report.py` (our measured re-identification risk), `README.md` and the 2-page brief
(`brief/`).

Contract it provides: [privacy](../../contracts/privacy.md). Reads findings from detect and keys
from link ([types](../../contracts/types.md)).

Implementation layout (`__init__.py` is wired to `engine.py`):
- `engine.py` — `plan()`, `replace()`, `stats()` and k-anonymity / rare-condition tiering
- `dates.py` — HMAC-SHA256 keyed per-patient/per-record date shifting & format preservation (also compact `YYYYMMDD[HHMM[SS]]`, the HL7 v2 date)
- `generalize.py` — age banding (`85+` top-coding), PIN prefixing, and village generalization
- `policy.py` — `config/policy.yaml` loader with defaults
- `test_privacy.py` — unit tests for contracts, date formats, k-anonymity, and `risk_report.py`

`scripts/risk_report.py`: the attacker files are `dev/attacker/registry.csv` and `dev/attacker/known_facts.jsonl`. A
`--registry` or `--known-facts` path that does not exist is an error (exit 2, message on stderr). Before, it was skipped
without a word and the attack sections were simply missing from the report.
