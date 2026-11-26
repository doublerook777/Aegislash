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
