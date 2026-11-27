# Fresh unseen test (batch 4)

Date: 2026-11-26. Detector: `aegis/` as at commit `8553c85` (unchanged). Nothing was fixed.

**Update:** `main` later gained changes that already fix `Kin.Ref` and the 3 landline misses. The header,
`h.no` and `r/o` fixes are on branch `detect/header-value-check`. They have **no unseen result**: a new
batch could not be written because the `agy` worker ran out of quota. The text below describes `8553c85`.

## Short answer

- On new text we covered **88.7%** of personal data in single lines and **87.2%** in table exports.
  We kept **99.1%** and **99.8%** of the medical / staff text.
- We were well ahead of Presidio on both measures in the totals.
- **The biggest problem is column headers.** 47 of our 83 misses go away when five misread headers are
  replaced by meaningless ones. We are better off not understanding those headers at all.

## How the test was kept blind

1. The scorer (`fresh_test.py`) was committed (`4f13d80`) **before** the cases were written. It uses the
   round-3 matching rule, and on the old round-3 cases it reproduced the README's current figures
   (92.0% and 93.5% covered, 100% kept).
2. The cases were written by the `agy-worker` window (Gemini 4 Hydrogen, High), not by me.
   Its tool log for this task shows only writing, editing and running its own script. I found no
   reads of the repo or of earlier cases. The task did not describe our rules or weak points.
3. The score below is from the **first run**, before any failure was read. The case files have not been
   edited (SHA-256 starts `9bd5d2a4` for `lines.jsonl` and `04b17095` for `files.jsonl`).

**Limits on "unseen":**
- The worker is the one that wrote the round-3 cases, in the **same conversation**. I tried to clear it,
  but my `/clear` arrived as an ordinary message. It was told not to reuse anything. Measured reuse
  from round 3: 0 of 60 lines, 0 of 86 column names, 2% of personal strings, 17% of medical / staff
  strings, 21% of the words in names and places (common words and names can repeat by chance).
- It is one writer and one batch of synthetic text. The task asked it to try to break a detector, and
  7 lines begin with test-like labels such as "Context-only:". Real hospital data may differ.
- I did not independently check the labels. When reading the failures I saw no clearly wrong label among
  the misses; one "lost" item is debatable (below). Items scored as successes were not reviewed.

## First-run results

60 lines (25 English, 20 Hinglish, 15 Hindi) and 8 exports of 6 records each. Network off.
"Covered" means every letter and digit of the item is flagged.

| | Ours | Presidio+lg | Presidio+sm | Presidio+xx |
|---|---|---|---|---|
| **Lines: personal data covered** (274) | **88.7%** | 58.4% | 56.9% | 58.8% |
| English (115) | 90.4% | 67.0% | 60.9% | 66.1% |
| Hinglish (90) | 90.0% | 66.7% | 64.4% | 70.0% |
| Hindi (69) | 84.1% | 33.3% | 40.6% | 31.9% |
| **Lines: medical / staff text kept** (215) | **99.1%** | 73.5% | 67.4% | 65.6% |
| **Exports: personal data covered** (406) | **87.2%** | 66.3% | 62.1% | 65.3% |
| Latin (382) | 86.9% | 70.2% | 65.4% | 68.8% |
| Devanagari (24) | 91.7% | 4.2% | 8.3% | 8.3% |
| **Exports: medical / staff text kept** (467) | **99.8%** | 71.3% | 64.7% | 61.0% |

**How sure can we be?** Resampling whole cases gives a 95% range for our coverage of **85-92%** for lines
and **78-96%** for exports. The export range is wide because there are only 8 exports, each with its own
headers: single exports went from **63% to 100%**. These ranges cover only which cases from this writer
we happened to get, not other writers or real data. Presidio did better than us on one export (83.6%
against 76.4%), one of those with a misread address header.

**Compared with round 3** (code before its fixes: 82% lines, 85% exports covered; 96% and 99.0% kept):
this batch scored higher. It does not prove how much we improved, because the batches differ, the writer
had seen its own earlier batch, and I added two labelling notes to the task (keep label words out of
expected strings; visit, bill, sample, lab and ambulance numbers are not patient identifiers).

## Why we missed things

**Everything from here on was done after reading the failures. This batch is now "seen".** The
percentages below show how much a cause explains. They are not new results.

Of 83 missed items (31 in lines, 52 in exports):

| Cause | Items | How it was confirmed |
|---|---|---|
| Five column headers misread | 47 | neutral headers: exports 87.2% → **98.8%**, same medical text kept |
| Lowercase `h.no` | 6 | writing `H.No.` covers all 6: lines 88.7% → 90.9% |
| Landline numbers with no label we know | 3 | variants (below) |
| Other numbers or IDs | 4 | not tested further |
| Other names and places | 23 | mixed; not all tested |

### 1. Column headers (the main finding)

| Header | We read it as | What happens | Extra items covered with a neutral header |
|---|---|---|---|
| `geo_hamlet_pin`, `Home Place & Pin`, `PostalLine` | PIN code column | only the PIN is removed; house and place stay | **36** (these columns go from 18/54 to 54/54) |
| `Kin.Ref` | doctor column | relatives are treated as doctors | 6 |
| `Bed & Patient` | text to keep | no cue or rule is applied to the column | 5 |

"We read it as" is what `labels.classify` returned for the last three; for the address headers it was
`pin`. In a `Kin.Ref` cell such as "wife Medha Kulkarni", only the surname was flagged (copied from
elsewhere in the file). Under a neutral header the whole name was found.

A **related problem seen in a separate small check** (not part of the counts): under a header read
correctly as a patient-name column (`Patient`), the cell "Bed 4 - Rameshwar Prasad Gupta" flags only
the word **"Bed"** and leaves the whole name.

### 2. Lowercase `h.no`
`H.No. 19/B` is found, `h.no 19/B` is not. The `H` / `Hno` part of the pattern in `address.py` is
case-sensitive, unlike the words next to it ("house", "flat").

### 3. Landlines
`Phone 0731-2449108` and `Tel: 011-27045192` are found. `call 0755-2554321`, `(0731-2449108)`,
`Tel~011-27045192` and `संपर्क सूत्र: 0755-2554321` are not. Our label-free phone pattern covers
mobile numbers (starting 6-9) only.

### 4. Other misses
Examples: one-word or nickname-style names ("Guddi", "Pappu"); several Hindi full names in running
text; "sister Nazia" / "sister Meera Thakur" meaning a family member (in the small check, "sister
Meera Thakur" is missed while "wife Meera Thakur" is found; we protect "Sister" as a nurse); house
numbers after `add~` or `Pata~`; a policy number and a Hindi-labelled MRN. I did not find one cause
for all of these. Presidio+lg covered 37 of our 83 misses in total (xx also 37, sm 26).

### 5. Medical / staff text lost (3 items)
- "**Meniere's** disease" after `r/o` was removed as a village. We read `r/o` as "resident of"; here it
  most likely means "rule out". The same disease without `r/o` is kept.
- "**Pt. B.D. Sharma** PGIMS", a hospital's name, was removed as a patient (`Pt.` = Pandit).
- "near Meenakshi Mission Hospital" was removed as a landmark. Debatable: it says where a relative waited.

## Does spaCy name detection help on new text?

This was the open question in `REPORT.md`. It adds a little coverage and loses a lot of medical text.

| Ours plus | Personal data covered | Medical / staff text kept |
|---|---|---|
| Lines: nothing | 88.7% | 99.1% |
| Lines: lg PERSON | 92.0% (+9 items) | **78.1%** |
| Lines: xx PERSON | 91.2% (+7) | 80.9% |
| Exports: nothing | 87.2% | 99.8% |
| Exports: lg PERSON | 90.9% (+15) | **83.1%** |
| Exports: xx PERSON | 90.4% (+13) | 80.9% |

The recommendation stays: **do not add it.** `fresh_test.py` also prints a "free text only" row. It
tells us nothing here: every line is free text, and no export field is marked as free text.
So NER limited to remarks columns, or with doctor and medical-word filtering, is still untested.

## Suggested fixes, in priority order (none applied)

1. **Check a header's role against the values in the column.** A "PIN" column whose cells are not 6-digit
   numbers should be treated by its contents. Likewise look again when a "doctor" column holds relation
   words, or a "keep" or name column holds "Bed 4 - Name". In these three address columns, treating
   them as addresses covered all 54 items. This is the general fix; adding the five header names to a
   list would only repair this batch. Check that real PIN, doctor and ward columns still behave.
2. **Make `h.no` case-insensitive.** Very small change; check it does not match ordinary words.
3. **Recognise landlines** with STD codes and more phone labels (`Tel~`, `संपर्क सूत्र`). Take care not to
   catch lab ranges or other number pairs.
4. **Treat `r/o` as "resident of" only when a place follows**, not a disease.
5. Leave the nickname and "sister" cases until the above are done. Removing "Sister <name>" everywhere
   would remove nurses.

The voter ID idea from `REPORT.md` is still a real gap, but this batch was not asked for such IDs, so it
adds no evidence. I would now put the header fix ahead of it.

**After fixing anything, this batch only checks for regressions.** A new number needs a new batch.

## Rerun

```bash
cd experiments/presidio
unshare -rn .venv/bin/python -B fresh_test.py fresh            # add --show to list failures
unshare -rn .venv/bin/python -B fresh_causes.py fresh          # the one-change-at-a-time numbers
```

The cases are invented. The worker's original copy is in its clone under `holdout4/` (untracked).
Because the worker can read that folder, do not treat it as blind if it is later asked to fix these misses.

---

# Second fresh test (batch 5, 2026-11-27)

**Everything above is about batch 4.** This section was written from counts only: **no batch 5 case text or failure
has been read by the person who wrote the fixes.**

## How it was kept blind
- Writer: a new Claude agent (the same model as the author of the fixes) that did not get the conversation. It got the
  task (`fresh_task.md`, plus its folder path, a no-web rule and "do not quote cases in your reply") and an empty folder.
- Its tool log shows writes and commands only in that folder, and no outside paths in tool inputs. Claude Code gave it
  git details automatically at startup: the branch, one untracked file name, five commit titles and the repository
  name. The titles show that earlier tests existed, not rules, failures or fixes.
- Versions and scorer were fixed before the writer started. Scored once, offline, with `score_versions.sh`.
- SHA-256 starts: `lines.jsonl` `6658c3ec`, `files.jsonl` `cfd99cdc`.
- **Limits:** one writer and one batch; the same model as me, so it may share my blind spots. **Labels have not been
  checked.** The writer said it left "Dr" out of doctor strings, usually put cities, districts and non-doctor staff in
  neither list, and edited some of its own address values and one name before finishing.

## Results

| | `a7faabf` | `c05e814` (my fixes) | `cb90eb4` | `main` `3e8818d` |
|---|---|---|---|---|
| Lines: personal data covered (121) | 53.7% | 53.7% | 53.7% | **53.7%** |
| Lines: medical / staff text kept (76) | 98.7% | 98.7% | 98.7% | **98.7%** |
| Exports: personal data covered (513) | 71.0% | 71.0% | 71.0% | **71.0%** |
| Exports: medical / staff text kept (237) | 99.6% | 99.6% | 99.6% | **99.6%** |

95% range from resampling cases: lines 44-62%, exports 57-83%.

## What it says about the fixes: nothing either way
`a7faabf` and `c05e814` produce **identical findings on every case**. The batch hardly contains what the fixes are for:

| Situation | Batch 4 | Batch 5 |
|---|---|---|
| lowercase `h.no` / `hno` | 8 | 0 |
| `r/o` | 1 | 1 |
| address cell under a "pin" header | 42 | 0 |
| header mixing patient with ward / bed | 6 | 0 |
| value starting with a bed / ward number | 6 | 0 |

So the fixes still have **no evidence of helping on unseen data**. They changed nothing here, good or bad.
(`cb90eb4` and `main` differ from `a7faabf` in the findings of one case, with no change to any scored item.)

## What it says about detect: much weaker than batch 4 suggested
The same `main` scores 92.0% / 99.0% on batch 4 (seen) and 53.7% / 71.0% here. Batch 4's first, unseen score on older
code was 88.7% / 87.2%. The batches have different writers, so this does **not** mean detect got worse. It means
**one batch is a poor estimate**: the result depends heavily on who wrote the cases. Earlier figures (README 82-85%,
batch 4 about 88%) should not be quoted as what to expect.

Values made only of words (names or places; the counts cannot tell which) are most of the misses: 39 of 56 in lines
and 106 of 149 in exports. Finding causes needs reading the failures. After that, batch 5 is "seen".

## Rerun
```bash
bash experiments/presidio/score_versions.sh experiments/presidio/fresh5 a7faabf c05e814 cb90eb4 3e8818d
cd experiments/presidio && unshare -rn .venv/bin/python -B compare_blind.py fresh5 a7faabf c05e814 cb90eb4 3e8818d
python3 -I count_fix_formats.py fresh5
```

---

# Batch 5 fixes, checked on batch 6 (2026-11-27)

After the section above, the batch 5 failures **were read** and fixed (batch 5 is now "seen"). Batch 6 was written by
another new Claude agent in an empty folder. Its tool log showed no file access outside that folder. **Its automatic
git details included the title of the fix commit**, "fix header, relation, ID, date and phone gaps...", so it knew
which areas had changed, though no rules or values. Same model as the author of the fixes. Labels not checked.
No batch 6 case or failure text has been read by the author of the fixes.

| Batch 6, personal data covered | previous (`2f3cb86`) | first run (`d53c05f`) | final (`6e027f9`) |
|---|---|---|---|
| Lines (116) | 56.9% | 60.3% | 59.5% |
| Exports (504) | 60.5% | 63.5% | 61.9% |

Medical / staff text kept was the same for all three: lines 100%, exports 97.3%. Nothing that passed before fails now.

**The final column is not a first run.** After the first score (totals only), a generated comparison showed that
`d53c05f` could leak names, and the code was changed. Part of the first run's gain came from the unsafe rules.

On batch 5, which the fixes were built from, the same code goes from 53.7% / 71.0% to 66.9% / 80.3%. **About 13 and 9
points on the data it was built from, about 1-3 points on new data.** That is the size of the memorisation gap.

## The leaks that tests and data did not catch
Hand-written tests, the practice data, the repo's test inputs and all the batches passed while the code could:

- hide a patient behind doctor protection: "SEEN BY DR <x> PT NAME <patient>" (introduced by my broader "DR" rule);
  "Ref Dr <x> Patient <patient>" already did this on `main`;
- stop searching a column for names because its header had gained a meaning ("P.I.N.", "Landmark", "Student", "fon");
- drop a whole finding because the captured text began with a word like "Witness" or "Admitted";
- stop searching a mostly-phones column, including its one cell that named a relative.

`differential.py` generates inputs from titles, relation words, headers and cell shapes, runs the old and new code,
and lists names the new code no longer covers. On the final code it lists 4: address cells reading
"<name> came with <new relation word> <name>", where only the second name is removed. The old code does the same with
older words such as "wife". It also lists 57 inputs with extra medical text flagged: artificial cells (a diagnosis
under "Student" or "Landmark") or medical words after a new relation word, mostly ones the old code already flags after
"son:". It only knows the shapes it was written with.

```bash
git archive 2f3cb86 aegis | tar -x -C <empty folder>
python3 experiments/presidio/differential.py <that folder> <this repository>
```

