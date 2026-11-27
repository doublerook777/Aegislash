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
| `hl7.py` | HL7 v2 messages saved as text: roles by segment and field position (PID, NK1, GT1, IN1) |
| `ids.py` | phone, Aadhaar, ABHA, PAN, email, insurance, record numbers |
| `dates.py` | dates (day/month order decided per file), date of birth, age |
| `address.py` | house, locality, landmark, village, district, PIN |
| `names.py` | name cues in free text, protected spans, medical / stop words |
| `gazetteer.py` | surname list and the rules for a name with no cue; `looks_like_person_cell` (whole-column check) |
| `normalize.py` | Devanagari digits, Devanagari -> Latin, `decode_view` (URL escapes, `\uXXXX`, HTML entities with a position map) |
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

## Identifiers of people in FHIR and FHIR-like JSON
- `Identifier.value` under a `Patient`, `RelatedPerson` or `Person` resource, under a `subject` / `patient` /
  `beneficiary` reference, or in a plain JSON `identifier` list whose parent key names a patient (`patient`,
  `patients`, ...) is a patient identifier **whatever its shape** (digits only, a short code, a made-up format).
  The whole value is removed (`engine._identifier_role`, `_plain_identifier_role`; role prefix `pid:`).
- The kind comes from the `system` / `type` beside it (Aadhaar, ABHA, PAN, insurance, ... via `labels.classify`);
  it is `MRN` by default. Nothing else in the file changes: resource `id`, `fullUrl`, references, coding systems and
  codes, Observation values, and `Encounter` / `Organization` / `assigner` / `generalPractitioner` identifiers stay.
- Selftest: three JSON documents added to `DOCS` (invented data).

## Fixes for the red-team set (`tests/test_results_and_observations.md`, Dataset 4)
- Added: lowercase PAN; `(912) 455-7781`, `912/450/7781` and landline phones; `ref` no longer means doctor (`ref_by`
  still does); `organization.patient.name` and `organization.contact.name` are people (nearest parent decides);
  `caller=<Name>`; a full name run together or lowercase in a file name, if the file also holds that name.
- Narrow, and chosen after seeing the failing cases: `case_sheet` = record number; `dak` = PIN (other `*_code`
  columns are still kept untouched); JSON keys count as people only in `by_*` tables or in `*_map/_index/_lookup/
  _directory` tables named for people or contacts. A looser key rule removed `Room Rent` and `Joint Stiffness`.
- Lowercase names: only on lines with no capital letter, and only with a listed surname of 4+ letters.
- Checks: selftest 81/81; dev output byte-identical to before; 810 lowercase-rule hits on lowercased dev data were
  all words from real identifiers. Dataset 4 was **not** rerun (not in the repo), and is no longer unseen for detect.
- Known false positive: `Lot no 0912-334455` reads as a landline.

## Fixes after the retest of `a7faabf`
- Added: `98.76.54.32.10` phones; any grouping after `+91`; Aadhaar with two different separators; hidden characters
  (removed for detection, positions mapped back); look-alike Cyrillic / Greek letters in words that also have Latin
  letters; accented letters matched as plain ones; `_` splits words in file names; `Surname, Given` in name columns;
  a bare year in a birth column (`DOB`, `norm` null); `yob`, `rogee`, `postal6`-style and `pehchaan_sankhya` labels
  (the last two are narrow, chosen after seeing the failing cases).
- Leaks on the committed sets, before -> after, on Linux: `tests/adversarial` 19 -> 6 of 157; breaker set 2 8 -> 1 of 40;
  set 3 4 -> 3 of 80; set 1 5 -> 5 of 35. Medical values kept: same counts. Dev output identical (apart from
  `report.json` timing and memory). **These are not unseen results:** the fixes were written from these failures.
- Left (since done, see the next section: URL-encoded names, wrapped / `data:` base64, base64 file names); names with no
  label or surname clue; a person as a key or under `reviewer`.
- Known false positive: `2025-2026 2027` reads as Aadhaar (with matching separators it already did).

## Fixes for the remaining leaks of PR #15 (2026-11-26, branch `fix/remaining-leaks`)
- **URL escapes.** `%20`, `%5C`, `%2B`, `%C3%AD` and the like are read for detection (`normalize.unquote_view`, combined with
  the hidden-character removal in `engine._view`). Every character of the read text remembers the stretch of the original it
  came from, so a finding's `start`/`end`/`text` point into the original value (`Priyanka%20Sengupta`, not `Priyanka Sengupta`).
  Escapes that are not valid UTF-8, or that stand for control characters, are left alone (`5%DEXTROSE`, `%0A`). This also
  stops `%5Cdischarge` from reading as the name "Cdischarge".
- **Names joined by `_`** (`...\Rukhsana_Bhattacharya\...`, `summary_Zubin_Pathak_2026.pdf`): given name + listed surname, same
  rules as with a space (`gazetteer.find_joined_names`). Words like `Lab_Reports` or `Ward_Singh_Round` are not names.
- **`patient=<Name>`** (log lines, query strings) now works like `patient: <Name>`.
- **Years from 1800** are dates (`01/01/1892`, `1889-07-21`, `02 Feb 1895`, a birth year `1893`). `12 Mar 1830 hrs` is still a
  time of day. Privacy shifts such a date like any other (`01/01/1892` -> `17/12/1891`).
- **Family and helper words are not the patient** in the action cues of PR #17 (`Uncle signed the consent`, `Dietician took
  discharge ...`): `names._NOT_THE_PATIENT`. (`<Name> signed the ...`, `<Name> took discharge` and `given to <Name>` are PR #17's
  rules; this branch first had its own copy, dropped when `main` gained them.)
- **URL parameters:** `patient=Priyanka%20Sengupta` is one finding. PR #17's `find_url_pii` reads the raw text; now that
  escapes are decoded first, a name value is extended over the following name words.
- Checks (on `main` 214d2a6 + this branch): selftest 115/115 (14 new cases; 7 of them fail on `214d2a6`, the rest are medical or
  staff text that must survive). Detect findings on all 273 parseable files of `dev/` and `tests/` changed only where the
  fixes apply (31,772 -> 31,785); `dev/` sanitized output and `records.jsonl` are byte-identical to `214d2a6`.
- **Left on purpose** (do not "fix" without a new idea; `Devika`, `Priyanka`, `Rohan` are now found by PR #17's cues):
  - `Sakshi returned for headache review`: "<word> returned" is also how symptoms read (`Wheezing returned`). Removing it
    would delete medical text.
  - `Tindwari` in `R. Mishra (32/M), Tindwari, copper low`: a bare word after age/sex is as often a diagnosis (`(40/F),
    Migraine,`) as a village. There is no village list.
  - `Pahari` in breaker set 3 is another patient's block column; it stays by team decision.
  - A query string whose values are not names or numbers (`?q=...`) is only read by the general rules, not by key.

## Fixes from the batch 4 fresh test (headers, "h.no", "r/o")
- Batch 4: 60 lines + 8 exports by another AI. The cases and full write-up are not in this repository (they are on the
  local, unpushed branch `detect/presidio-lab`). Its first, unseen score on `8553c85`: 88.7% / 87.2% of personal data covered (lines / exports), 99.1% / 99.8% kept.
- A column read as "PIN" whose cell has a comma, a PIN and other words is parsed as an address. "Ward / Patient"
  columns take the name after a bed number and are otherwise read like free text. `Bed 8 - <name>` no longer flags
  "Bed". Lowercase `h.no` / `hno`. `r/o` followed by something that looks like an illness is not a village; when
  unsure it is still removed.
- **No unseen result for these fixes.** Batch 4 had been read, so it only shows they work there: from `a7faabf` to
  this change, lines 89.8% -> 92.0% covered, exports 88.7% -> 99.0%, medical kept 99.1% -> 99.5% / 99.8% -> 99.8%,
  nothing newly failing. A batch 5 could not be written (the writer ran out of quota). Round 3 and the inputs in
  `dev/` and `tests/` gave the same results as before.
- Checks: selftest 95/95; practice output and records byte-identical to `a7faabf`.
- Still open: a "PIN" cell holding a place with no comma or no PIN; landlines spaced like `0522 2345678`; a hospital
  named after a person (`Pt. <name>`); one-word names with no clue; "sister <name>" meaning a relative.

## Fixes from the batch 5 fresh test, and how little they carried over to batch 6
- Batches 5 and 6 (60 lines + 8 exports each) were written by Claude agents that were not given the code or any
  failure. Cases, scorer and write-up: `experiments/presidio/FRESH_TEST.md`. Batch 6's writer saw this fix's commit
  title, which names the areas changed.
- Fixed: dotted headers ("P.I.N."), notes columns written by a nurse or doctor, "relative contact" columns (a
  regression: their names were missed once "संपर्क" became a phone word), `<name> Kumari`, HL7 `Family^Given`, more
  relation words and `=`, relation before or after a name in relative columns, `MR#` / TPA / insurance labels, Hindi
  and roman-numeral months, landmark / neighbourhood / `Student` / `fon` headers, oddly spaced phone columns.
- **A leak older than this change:** "Ref Dr <x> Patient <y>" protected all of it as the doctor's name.
- **Rules that protect, shorten or give a column a role can leak.** Earlier drafts of this change did, while the
  self-test, practice data and test batches passed. A generated comparison with the previous code found them:
  `experiments/presidio/differential.py <old root> <new root>`. So a newly understood header only ADDS checks
  (`labels.extra_checks`), and the new relation words have their own cues.
- Personal data covered, previous code -> this code (lines / exports):

  | batch | status | previous | now |
  |---|---|---|---|
  | 5 | its failures were fixed | 53.7% / 71.0% | 66.9% / 80.3% |
  | 6 | never read | 56.9% / 60.5% | 59.5% / 61.9% |

  **Expect the batch 6 gain, about 1-3 points, not the batch 5 one.** (An earlier draft scored 60.3% / 63.5% on its
  first run; part of that came from the unsafe rules.) Medical text kept on batches 5 and 6 did not go down.
- Unseen coverage has ranged from about 55% to 89% across batches from different writers. Do not quote one batch.
- Still open: names with no clue; places in free text with no capital or cue; a medical term right after a relation
  word ("son <diagnosis>") can be removed as a name; in an address cell, "<name> came with <relation> <name>" removes
  only the second name; a bare capital `DR <name>` is not protected as a doctor (on purpose).

## Hindi honorifics, relation words and places in running text (F1)
- **Cause.** The Hindi cues were weaker than the English and Hinglish ones: only `श्री / श्रीमती / कुमारी / सुश्री` and
  `पुत्र / पुत्री / पत्नी / सुपुत्र` were cues, and each took the next 3 Hindi words with no check of where the name ends (so
  `श्रीमती रीना फॉलो-अप ...` removed "फॉलो"). `श्रीमान`, `स्व.`, `पति`, `भाई`, `बेटे`, `बहन`, ... were no cues. `<kin word> जी`
  and `पति को ...` were read as a name because a bare kin word went through the "<name> जी" and "<name> को" cues. The danda
  `।` also sits inside the Devanagari block, so `(?![ऀ-ॿ])` made a cue fail at the end of a sentence. Places: only
  `ग्राम / गाँव / गांव` announced a village; `निवासी X` and `X से (लेकर) आए` did not.
- **Change.** `names._hindi_cue_names` replaces the two greedy cues. Honorifics (strong: first word is taken if nothing
  better) and relation words (weak: need an end) are followed by 1-3 Hindi words; the name ends at a comma / danda, at a
  number or Latin text, or before a word in `names.HI_NOT_NAME` (particles, verb forms, relation words, honorifics, time
  and medical words, taken from `gazetteer` lists plus a general Hindi vocabulary list). No end and no listed surname means no
  name (`पति रोज़ ...` stays text). `HI_NOT_NAME` is also part of `STOP`, so a kin word is never trimmed in as a name.
  `address._NIWASI` and `address._BROUGHT_FROM` add the two place cues (the place cannot be a `HI_NOT_NAME` word:
  घर, अस्पताल, वहाँ, कल ...). `gazetteer.DEVA_*` are public names for the existing Hindi lists (no new data).
- **Never across a line.** A Hindi cue reads its name only up to the end of the line, and a word followed by `:` is a label
  (`उम्र:`), never part of a name. A first attempt read `पुत्र: <name>` into the next line's `उम्र:` label.
- **Checks.** selftest 177/177 (14 new cases, 9 fail on the base commit; the others are medical text or labels that must survive);
  `dev/` sanitized output and `records.jsonl` byte-identical to the base; the committed sets (adversarial, three breaker
  sets) also byte-identical, so no recorded number changed. These sets do not contain the failing shapes, so this is
  **not** an unseen measurement.
- **Left.** Name followed by a word that is neither listed nor a surname (`पति रमेश ऑफिस ...`) is not found by the relation
  cue (a bare name with no cue is still found by the surname list). `<place> के निवासी`, Hinglish `<place> se laye`,
  and `मास्टर / सरदार` are not cues. A district written in Devanagari is removed like a village (there is no Devanagari
  district list).

## Column-level name inference and dotted Aadhaar (finding F2)
- **Cause.** A table column whose header the label rules do not know (`Applicant`, `Escort`, `Enrollee`, `Accompanied By`) was
  searched cell by cell, so a cell was removed only when its own text looked like a name (a listed surname). Other rows of the same
  column kept their full names. `engine._guess_role` did judge such a column from its values, but only for Latin cells and only when
  40% of them carried a listed surname; Devanagari columns were never judged.
- **Change.** For a CSV/TSV column with no role: if at least 80% of its non-empty cells (3 or more) read as a 2-3 word person name
  (TitleCase Latin or Devanagari words, no digit or punctuation, none of the place / hospital / ward / staff / trade / diagnosis /
  medicine words: `gazetteer.looks_like_person_cell`), at least 3 values and 30% of the cells are distinct, and the header is not
  a category, medical, hospital or doctor header (`labels.category_column`), the whole column is a name column. The first such column
  in a file is the patient, a later one the relative (the existing rule). A listed-surname cell is never needed.
  Medical columns are never turned into names: their header already says so, and their cells fail the word lists, the diagnosis
  endings (`-itis`, `-osis`, `-pathy` ...) or the repeat check.
- **Dotted Aadhaar.** `ids.AADHAAR` allowed only `-`, space or no separator. `1234.5678.9012` (4-4-4 with dots) is now matched,
  unless it reads as `year.monthday.hourminute` (`2024.0115.1030`). Dotted shapes with a fourth group (`1.2345.6789.0123`), versions
  and lab values (`4.2.1`, `7.5000`) are still not matched (checked in the selftest).
- **Review fix (before merging PR #25): evidence of people is required.** "Two capitalised words not in a word list" also fits
  organisms, drugs and vaccines (`Escherichia Coli`, `Piperacillin Tazobactam`, `Measles Rubella` under headers like `Isolate`,
  `Sensitive To`, `Vaccine Given`). The first version redacted such columns whole. Now a column that only looks like names
  (`PERSON_SHAPED`) counts as names when at least one cell, and a fifth of them, holds a listed surname (Latin or Devanagari).
  It also counts when at least half its rows, two or more, end in the same word as another column of people in the same
  row (`engine._shares_surnames`: patient and relative share a surname). Otherwise it is left alone.
  Selftest table "Isolate / Sensitive To / Vaccine Given / Next Due" (13 problems before, 0 after). Committed sets and the
  judge's fresh batches give identical output. Left: a lone column of people whose surnames are all unlisted and who share
  no surname with another column is read cell by cell, as before F2.
- **Limits.** A file with fewer than 3 filled cells in the column, or with names mixed with other text in the column, is still read
  cell by cell. A name column whose header is an unknown *category-like* word (`Occupation`) is left alone on purpose. An unknown
  header holding 2-3 word TitleCase trade or status values that are not in the word lists (`Govt Employee`) can still be read as names
  when all the rows are different; the veto list in `labels._CATEGORY` is where such headers are added.
- Checks: selftest 164/164 (4 new tables and 1 new line; 19 problems and 1 case fail on the previous code); `dev/` sanitized output,
  `records.jsonl` and every `tests/` set are byte-identical to before (the committed sets already had labelled name columns or listed
  surnames). Dev with every CSV/TSV header replaced by an unreadable one: 86 of 3230 leaked and 4824 of 4825 medical kept, both before and after.

## Next (generalisation)
1. Another round of fresh unseen cases; fix general causes, never single sentences.
2. Known blind spots: one-word names with no clue (nicknames, "<name> signed"); full names whose surname is not in
   `gazetteer.py` and that have no cue; "Surname, Given" order in running text; a doctor written without "Dr." in running text can be
   removed as a patient name (also true for a doctor column with an unreadable header: it counts as doctors only if
  more than half its names appear as `Dr. <name>` elsewhere, so that patients are never exposed by one shared name);
  lowercase names with an unlisted surname; a person used as a JSON key outside the tables above;
   a zero-width character used in place of the space between two names.
3. The 1 lost medical value and 1 wrong merge on practice data (find which module causes each).

## Hidden payloads, R2b (2026-11-27, branch of `judge/integration`)
- **Escapes written out in text are read.** `engine._view` now uses `normalize.decode_view`: `%XX` (as before), `\uXXXX` / `\u{...}`
  (surrogate pairs joined; control characters left alone) and HTML entities (`&amp;`, `&#74;`, `&#x4A;`), up to three layers
  (`%5Cu0932`). Each character of the decoded text remembers the stretch of the original it came from, so a finding covers the
  whole escaped name and `start`/`end`/`text` still point into the original value. `unquote_view` is unchanged in behaviour.
- **Base64 inside a value is done by io**, not here: io hands detect the decoded text as a field of its own
  (`<path>#b64:<n>`; the engine reads such a JSON path like its parent key, `_segments`), so roles, cues and propagation work on it.
- **A cue word followed by a Devanagari name** (`attendant लता बैरवा`, `informed by ...`): `names._cue` with `_DEVA_FUNCTION` (Hindi
  function words such as `के`, `को`, `साथ` are not names). Before, only the Latin name after a cue was found.
- Checks: selftest 184/184 (6 new cases, 4 of them fail before); committed sets: outputs byte-identical to the base, no run
  found in any of the 268 parseable committed input files (no false positive from the base64 rule).

## HL7 v2 messages saved as text (`hl7.py`)
- A value (a `.txt` file, or a JSON string) with a line starting `MSH|` is read as an HL7 v2 message. Segments are split on
  `\r`, `\n` or `\r\n` (also behind an MLLP `0x0b`); the separators come from MSH-2 (default `^~\&`).
- A field's role comes from its **segment and position**, not from words: PID-2/3/4 identifier lists (the ID before the
  first `^`, every `~` repetition; Aadhaar / ABHA / PAN shapes keep their type, the rest is `MRN`), PID-5 / PID-9 names
  (family, given, middle: one finding per word, so `^` stays), PID-6 mother's maiden name and NK1-2, GT1-3/4, IN1-16
  names (relatives), PID-7 and NK1-16 / GT1-19 / IN1-18 dates of birth, PID-8 sex, PID-11 / NK1-4 / GT1-5 / IN1-19 addresses
  (street -> `HOUSE`, other designation and city -> `LOCALITY`, zip -> `PIN`; state and country stay), PID-13/14,
  NK1-5/6, GT1-6/7 phones (number, area, local number, e-mail), PID-19/20, GT1-12, IN2-2 national ids, IN1-36 policy
  number, PID-23 birth place. Name findings carry `Cand.full_name` (given family) so every word of one name gives the
  same evidence name; the words then propagate through the file like other names.
- Never touched: MSH, OBR / OBX values, codes, units, ranges, PV1 locations and doctors, titles / suffixes in names.
  A field that is only a time stamp (`202503011030`) and has no role is no longer taken for a 12-digit Aadhaar number.
- The sanitized text keeps its segments, its number of fields and every separator. `privacy/dates.py` shifts compact
  `YYYYMMDD[HHMM[SS]]` dates, so the date of birth stays a valid HL7 date.
- Selftest: `HL7_MESSAGES` (three invented messages: `\n` and `\r` separators, guarantor, insured person, OBX content).
- Left alone: HL7 inside base64 or a CSV cell is only read if the cell itself starts with `MSH|`; escape sequences
  (`\F\`, `\S\`) inside names are not decoded; ORC / OBR / PV1 doctor names stay (staff).

## Hinglish relation words, "Ghar <place> mein", "landmark <place>" and a name in brackets (finding F4)
- **Cause.** The English kin cues (`son`, `wife`, `brother` ...) had no Roman-script Hindi twin before a name: `beta`, `pati`,
  `bhai`, ... only worked *after* a name ("<name> beta"). A place had no Hinglish sentence cue: `Ghar <X> mein hai` and
  `landmark <X>` were not cues, and `<X> ke paas` worked only when X ended in a landmark noun (Mandir, Chowk ...). A
  `<name> ne <what a person does>` sentence (`Rekha ne raat ko dawa nahi li`) was a cue only for `ne sign / call ...`. A name in
  brackets after a found name was never read by itself, so its surname survived (`Nitin sahab (Nitin Ekka)`). Separately a
  relation word at the start of a sentence went through the "<Name> ko bukhar" and "<Name> sahab" cues, so
  `Beta ko bukhar nahi hai` and `Bhai Sahab ne ...` lost "Beta" / "Bhai" as if they were names.
- **Change.** `names._HINGLISH_KIN` (about 40 relation words; "didi", "sister", "maa" are left out on purpose: ASHA didi and
  nurses are staff) is a cue before a capitalised name. The first-word check (`_NEVER_FIRST`) drops `Beta Blocker`,
  `Bhai Sahab`, `Dr`, particles and medical words; a lowercase word after the relation word (`ko`, `ka`, `ne`) never matches.
  `names._after_kin_words` takes a leading relation word off a captured name for the "<Name> ko bukhar", "<Name> sahab / ji"
  and new `<Name> ne <raat|dawa|bataya|...>` cues (also after `ki`, `jo`, `jab`); nothing left means no name.
  `names._alias_names` reads `( <Given> <Surname> )` right after a found name and its honorific, if the words are capitalised
  and none is a stop, medical, hospital, staff or pronoun word. `address._HINGLISH_LOCALITY` (`Ghar / Makaan <Place words> mein`),
  `_LANDMARK_CUE` (`landmark <Place words>`) and `_PLACE_LANDMARK` (`<... Nagar / Colony / Vihar / Chowk / Marg> ke paas`) add the
  places; `_place_span` cuts report words and refuses a first word that is a stop or hospital word, and a doctor before it.
  No contract change (no new fields, types or files).
- **Checks.** selftest 196/196 (12 new cases with invented names; 9 fail on the base commit, the rest are Hinglish medical text,
  `Beta Blocker`, `Dr. <name> ke paas` and drug subjects that must survive). `dev/` sanitized output and `records.jsonl`, the adversarial
  set, the three breaker sets and `tests/breakers/adversarial_input` are byte-identical to the base (only `report.json` timings
  differ), so no recorded number changed; these sets do not contain the failing shapes, so this is **not** an unseen measurement.
- **Left.** `<X> ke paas` is a landmark only when X ends in Nagar / Colony / Vihar / Puri / Enclave / Chowk / Marg or a landmark noun
  (`Anita ke paas` is a person, not a place). `Mama <Capitalised noun>` (`Mama Earth`) still reads the noun as a name; `landmark Gate No 4`
  keeps "No 4"; the `ne` cue knows about 30 verbs and nouns, so `<name> ne <other verb>` is not a cue; lowercase names are not found by
  the new cues.
