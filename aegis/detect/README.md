# detect: detection engine (owner: Member-2)

Finds every piece of personal data (English, Devanagari, Hinglish) and builds the `Evidence` that `link`
uses, while leaving medical text alone. Rules and word lists only: no model, no network, standard library only.

Contract it provides: [detect](../../contracts/detect.md). Shapes: [types](../../contracts/types.md).

## How it works (one file at a time)
1. **Roles:** each CSV column / JSON key gets a role (name, phone, address, doctor, ...) from the *words* in its
   label, so renamed columns still work. `{"url": ".../mothers-name", "valueString": X}` pairs use the sibling label.
2. **Candidates:** structured rules for known roles, plus shape rules (IDs, dates, ages) and context cues in
   free text (`S/o`, `ji`, `Attendant:`, `Label: value` lines).
3. **Meaning traps:** `Dr. <name>`, eponyms, `ASHA`, `C/O <complaint>`, `K/C/O`, drug names are protected.
4. **Copying:** names and record numbers found once are searched for in the rest of the file (file name,
   headers, export paths, notes). An index by first word keeps this fast.
5. **Overlaps:** highest priority wins. **Evidence:** built from the final findings.

## Files
| File | Holds |
|---|---|
| `engine.py` | `detect_file`: the five steps above |
| `labels.py` | label words -> role |
| `fields.py` | what to flag in a value whose role is known |
| `ids.py` | phone, Aadhaar, ABHA, PAN, email, insurance, record numbers |
| `dates.py` | dates (day/month order decided per file), date of birth, age |
| `address.py` | house, locality, landmark, village, district, PIN |
| `names.py` | name cues in free text, protected spans, medical / stop words |
| `normalize.py` | Devanagari digits, Devanagari -> Latin |
| `evidence.py` | identity clues for `link` |
| `spans.py` | candidate type and overlap priority |
| `selftest.py` | made-up cases not from practice data (never imported by `main.py`) |
| `mock.py` | the old placeholder |

## Check your change
```bash
.venv/bin/python -m aegis.detect.selftest
.venv/bin/python scripts/check_contracts.py --only detect
RAKSHA_SECRET=practice .venv/bin/python main.py --input dev/input --output out
.venv/bin/python check_dev.py --output out --show 20
```

## Where it stands (2026-11-26)
- Practice data (with mock link and privacy): 0 / 3230 leaked, 0 canaries, 4855 / 4855 medical values kept.
  2,000-row CSV: about 3 s. All 771 must-link records carry a strong ID or name + second clue.
- **Treat the practice score as optimistic:** the rules were written while looking at practice data. Hidden data
  has unseen names, labels and formats.
- `check_contracts.py --mock` fails one case on purpose: only the mock raises for a file named "bad".

## Next (generalisation, in this order)
1. Grow `selftest.py` with unseen formats: other column names and label styles, other record-number, phone and
   date formats, names with only weak clues, more over-removal traps. Fix what fails with *general* rules.
2. Known blind spots: a name with no clue anywhere in its file; year-of-birth fields; zero-width characters and
   look-alike letters; unfamiliar honorifics; labels in languages / spellings missing from `labels.py`.
3. After real `link` and `privacy` merge, rerun everything above.
