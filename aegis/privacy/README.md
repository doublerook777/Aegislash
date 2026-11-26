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

Small releases (fewer than `max(10, 2 * min_group_size)` profiles): the k-anonymity tiers used to be switched off
there, so every patient kept a 5-year band, a PIN prefix, the village (as its district) and the raw district, and was
unique on them. Now the tiers run at any size, so a cell under `min_group_size` gets the wide band and no PIN or village.
In a small release a district shared by fewer than `min_group_size` profiles is also replaced by `[DISTRICT]` (and the
village is suppressed, not generalised to that district). Conditions, dates (shifted, intervals kept) and gender stay.
Larger releases are unchanged: hiding a rare district there would cost generalisation utility on standard data, so it
is left for a team decision (audit V1, point 2). Checked: dev and every committed set give byte-identical output.
