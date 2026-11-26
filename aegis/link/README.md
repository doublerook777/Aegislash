# link: linkage + pseudonyms (owner: Member-3)

Owns deciding which records belong to the same patient across files, hospitals and scripts:
cross-script name normalization (Mohammad / Mohd / Md. / मोहम्मद), blocking, matching rules
(strong ID, or name + DOB / relative / village+age±1 unique in the dataset), clustering without
transitive over-merge, homonym separation, canonical patient keys. `psn.py` (keyed HMAC) is done.

Contract it provides: [link](../../contracts/link.md). Reads `Evidence` from detect
([types](../../contracts/types.md)).

The real code goes in this folder; switch the `resolve` import in `__init__.py` from `mock` when ready.
