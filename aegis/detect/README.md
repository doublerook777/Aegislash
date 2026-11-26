# detect: detection engine (owner: Member-2)

Finds every piece of personal data (English, Devanagari, Hinglish) and builds the `Evidence` that `link`
uses, while leaving medical text alone. Rules and word lists only: no model, no network, standard library only.

Contract it provides: [detect](../../contracts/detect.md). Shapes: [types](../../contracts/types.md).

## How it works (one file at a time)
1. **Roles:** each CSV column / JSON key gets a role (name, phone, address, doctor, ...) from the *words* in its
   label, so renamed columns still work. `{"url": ".../mothers-name", "valueString": X}` pairs use the sibling label.
2. **Candidates:** structured rules for known roles, plus shape rules (IDs, dates, ages) and context cues in
   free text (`S/o`, `ji`, `Attendant:`, `Label: value` lines). A name with no cue is found if it holds a given
   name plus a known surname (Latin or Devanagari) and is not a hospital, ward, road or staff member. Address
   parts next to a house number or PIN are followed ("Flat 3, <locality>, 600020").
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
| `gazetteer.py` | surname list and the rules for a name with no cue |
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

## Where it stands (2026-11-26, after unseen-format round 3)
- Practice data with real link and privacy: 0 / 3230 leaked, 0 canaries, 4854 / 4855 medical values kept, linking
  F0.5 0.99 (1 wrong merge). 2,000-row CSV: about 4 s in detect. Whole practice run: about 6 s, 68 MB.
- **Treat the practice score as optimistic:** the rules were written while looking at practice data.
- Best estimate of unseen performance (round 3: 60 lines + 8 exports written by another AI that was told not to read
  our code; scored **before** any of its failures were looked at; a value counts only if every letter and digit of it
  is removed):

  | | personal data covered | medical / staff text kept |
  |---|---|---|
  | lines, previous code | 54% | 96% |
  | lines, round-2 fixes | 82% | 96% |
  | exports, previous code | 63% | 99.8% |
  | exports, round-2 fixes | 85% | 99.0% |

  Round-3 failures were then fixed (now 92% / 93.5% covered, 100% kept), but that figure is **not** an unseen
  result. Expect new data to do about as well as the 82-85% row, perhaps a little better. For a new measurement,
  generate fresh cases.
- Some round-3 "misses" are scoring choices we left alone: visit / sample / ambulance run numbers (the kit does not
  count them as patient identifiers), and cue words inside the expected string ("Village <name>").
- `check_contracts.py --mock` fails one detect case on purpose: only the mock raises for a file named "bad".

## Next (generalisation)
1. Another round of fresh unseen cases; fix general causes, never single sentences.
2. Known blind spots: one-word names with no clue (nicknames, "<name> signed"); full names whose surname is not in
   `gazetteer.py` and that have no cue; "Surname, Given" order; a doctor written without "Dr." in running text can be
   removed as a patient name; year-of-birth fields; zero-width characters and look-alike letters.
3. The 1 lost medical value and 1 wrong merge on practice data (find which module causes each).
