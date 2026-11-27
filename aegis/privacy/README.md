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

Small releases and rare districts: the k-anonymity tiers run at any release size, so a cell under `min_group_size` gets the wide band and no PIN or village. Any district shared by fewer than `min_group_size` profiles is replaced by `[DISTRICT]` (and its villages are suppressed to `[VILLAGE]`) regardless of release size, reducing A2/A4 registry re-identification (`34.0%` -> `26.0%` on `dev`) at minimal utility cost. Conditions, shifted dates (uniform in `[-max_days, -1] U [1, max_days]`), and gender stay; `plan()` requires a non-empty `RAKSHA_SECRET` (`secret_missing` otherwise), and ages `>= elderly_age_threshold` (including `> 130`) are top-coded (`85+`). A `TEHSIL` finding (tehsil / block value) is written `[TEHSIL]` wherever the district is hidden (#33), and kept otherwise.
