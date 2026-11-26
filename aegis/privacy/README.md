# privacy: quasi-identifiers, measurement, write-up (owner: Member-4)

Owns every replacement string: PSN for linked names/MRNs, `[TYPE]` placeholders, per-patient secret
date shifts in the original format, truthful age bands, PIN prefix, village generalization,
rare-condition / small-cell handling (k-anonymity), `config/policy.yaml`. Also owns
`scripts/risk_report.py` (our measured re-identification risk), `README.md` and the 2-page brief
(`brief/`).

Contract it provides: [privacy](../../contracts/privacy.md). Reads findings from detect and keys
from link ([types](../../contracts/types.md)).

The real code goes in this folder; switch the import in `__init__.py` from `mock` when ready.
