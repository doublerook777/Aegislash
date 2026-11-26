# Experiment report: Presidio + spaCy compared with our detect

Date: 2026-11-26. Branch: `detect/presidio-lab`. Research only: nothing in `aegis/` was changed.

**Update:** a fresh unseen test was run after this report, including Presidio. See
[FRESH_TEST.md](FRESH_TEST.md). It answers the "not run on fresh text" points below and puts a
column-header fix ahead of the recommendations here.

## Short answer

- **Do not add Presidio or spaCy.** Out of the box they find much less than our rules, flag a lot of
  medical text, and go over our time and memory targets.
- On the two datasets, **Presidio found no real name or number that we missed entirely.** Where it
  covered more than we did, the extra text was the family word in 14 chat sender names
  ("Kamal **Bhaiya**"). We already remove "Kamal".
- Reading its code showed **one real gap**: we have no rule for voter ID, passport, vehicle number
  or GSTIN. Neither dataset contains them, so only a small separate check shows this.

## Read this before the numbers

**These are not results on unseen data.** Our rules were written while looking at the practice data,
and the self-test cases were used to fix our rules. Both favour us heavily. Presidio was not tuned at
all. So "ours 99.6%" does **not** say how we will do on the hidden data. Our own earlier measurement
on fresh text (`aegis/detect/README.md`, not rerun here) was about **82-85%**.
I did not run Presidio on fresh text, so I cannot say which would do better there.

## What was run

| Setup | What it is |
|---|---|
| Ours | `aegis.detect.detect_file`, unchanged |
| Presidio+lg | `presidio-analyzer` 2.2.366 with its default settings (model `en_core_web_lg`, score threshold 0), plus the Indian recognizers |
| Presidio+lg+headers | same, and the column header / JSON key is passed in as "context words" (this is not a default) |
| Presidio+sm | same as Presidio+lg with the small English model |
| Presidio+xx | same with the multilingual model `xx_ent_wiki_sm` |

**Indian recognizers:** all six ship switched off and were added by hand: `InAadhaarRecognizer`,
`InPanRecognizer`, `InPassportRecognizer`, `InVehicleRegistrationRecognizer`, `InVoterRecognizer`,
`InGstinRecognizer`. The 18 recognizers that are on by default were left on.

| Package / model | Version | Installed size | Licence |
|---|---|---|---|
| presidio-analyzer | 2.2.366 | | MIT |
| spaCy | 3.8.18 | | MIT |
| en_core_web_lg | 3.8.0 | 425 MB (download 382 MB) | MIT (trained on OntoNotes 5 and other sources) |
| en_core_web_sm | 3.8.0 | 15 MB | MIT (trained on OntoNotes 5 and other sources) |
| xx_ent_wiki_sm | 3.8.0 | 39 MB | MIT (trained on WikiNER, CC BY 4.0) |

The whole environment with all three models is 789 MB. Python 3.14.10 worked, so 3.12 was not needed.
None of the three models is a transformer.

**Hindi:** spaCy's model list for 3.8 has no Hindi model. My Hugging Face searches (spaCy tag with
Hindi / `hi_` / Hinglish) showed no usable Hindi NER model: `amank22/hi_ud_hi_ewt` has no NER step,
no licence and needs spaCy 3.1, and the other Hindi-tagged result was access-restricted and did not
look like an NER model. So option (c) is `xx_ent_wiki_sm`, which is multilingual but **not trained on
Hindi**. Hindi transformer NER models were not considered, because of the 50M-parameter limit
(I did not check their sizes).

## How a match is counted (same for every setup)

- Every setup gets the same input: the fields produced by our own parser (CSV cells, JSON values,
  decoded base64, keys, headers, file names). Presidio gets one field at a time.
- Only flagged character ranges count. The type label is ignored, except in the "right label" column.
  Our CONDITION / DISTRICT / GENDER findings do not count, because we never remove them.
- A personal item is **found** only if every letter and digit of every occurrence is flagged.
  Partly covered counts as not found.
- For names in `dev/input`, only the identifying words listed in `truth.json` are required, as the
  official scoring does. Leaving "sahab" or "ji" is not a miss. Self-test strings are required in full.
- Medical / staff text is **damaged** if any of its characters is flagged.
- 7 items inside the 5 files that our parser cannot read are left out for everyone.
- This is my own rule in `score.py`. It is not the official F2 score and not `check_dev.py`.

## Results: `dev/input` (3227 personal items, 4854 must-keep phrases)

"Right label" counts a Presidio hit only if its label means that thing (PERSON for a name, and so on).
It matters: for example, Presidio's **US driver licence** pattern accidentally covers parts of Indian numbers.
A dash means Presidio has no label for that type.

### Personal data found, by type

| Type | Items | Ours | Presidio+lg | lg, right label | Presidio+sm | Presidio+xx |
|---|---|---|---|---|---|---|
| Patient name | 958 | 100% | 75.9% | 73.5% | 51.8% | 60.8% |
| Relative name | 232 | 94.0% | 71.6% | 71.6% | 42.2% | 63.8% |
| MRN / hospital number | 850 | 100% | 16.0% | - | 17.3% | 13.1% |
| Phone | 306 | 100% | 100% | 100% | 100% | 100% |
| Aadhaar | 70 | 100% | 92.9% | 80.0% | 95.7% | 92.9% |
| Aadhaar, masked | 16 | 100% | 75.0% | - | 87.5% | 0% |
| ABHA number | 46 | 100% | 30.4% | - | 50.0% | 0% |
| PAN | 22 | 100% | 100% | 100% | 100% | 100% |
| Insurance ID | 22 | 100% | 0% | - | 4.5% | 0% |
| Email | 1 | 100% | 100% | 100% | 100% | 100% |
| DOB | 111 | 100% | 100% | 100% | 100% | 100% |
| PIN | 136 | 100% | 100% | - | 100% | 100% |
| Village | 150 | 100% | 64.7% | 1.3% | 30.7% | 60.0% |
| Locality | 103 | 100% | 49.5% | 3.9% | 41.7% | 46.6% |
| House | 136 | 100% | 0% | 0% | 3.7% | 12.5% |
| Landmark | 64 | 100% | 0% | 0% | 0% | 0% |
| Canary | 4 | 100% | 75.0% | not scored | 50.0% | 75.0% |
| **All** | **3227** | **99.6%** | **57.2%** | | **47.0%** | **50.8%** |

Passing headers as context words gave the same coverage as Presidio+lg at the default threshold.

### Personal data found, by script

| Script | Items | Ours | Presidio+lg | Presidio+sm | Presidio+xx |
|---|---|---|---|---|---|
| Latin | 2973 | 100% | 58.6% | 48.7% | 53.3% |
| Devanagari | 143 | 100% | 8.4% | 8.4% | 9.8% |
| Hinglish | 111 | 87.4% | 84.7% | 51.4% | 36.0% |

### Medical / staff text wrongly flagged (lower is better)

| Group | Phrases | Ours | Presidio+lg | Presidio+sm | Presidio+xx |
|---|---|---|---|---|---|
| Medicine, dose, frequency | 1383 | 0% | 8.6% | 26.4% | 18.7% |
| Vitals and lab values | 1712 | 0% | 8.8% | 12.4% | 16.8% |
| Diagnosis, complaint, history | 848 | 0% | **54.8%** | 49.8% | 44.8% |
| Doctor names | 511 | 0% | **100%** | 100% | 81.8% |
| Ward, department, hospital, district, other | 400 | 0% | 36.8% | 32.8% | 26.2% |
| **All** | **4854** | **0%** | **28.7%** | **33.8%** | **29.8%** |
| of which Devanagari phrases | 66 | 0% | 16.7% | 24.2% | 16.7% |
| Ranges flagged in the 5 clean files (dates/ages not counted) | | 0 | 31 | 37 | 55 |

Presidio is not built to keep doctor names: a doctor is a person, so it flags them. Our project must keep them.

There were also 5,980 Presidio+lg ranges that touched no listed personal data (9,089 for xx; dates and
ages not counted). The largest groups were `IN_PAN` 1203, `PERSON` 1179, `UUID` 1161 and
`US_DRIVER_LICENSE` 1083. The weakest PAN pattern (score 0.01) also matches pieces of dates. We had
107 such ranges. I did not check them one by one, so some may be real data that the truth file does not list.

## Results: self-test cases (83 personal items, 72 must-keep phrases)

| | Ours | Presidio+lg | Presidio+sm | Presidio+xx |
|---|---|---|---|---|
| Found, Latin (72) | 98.6% | 62.5% | 59.7% | 69.4% |
| Found, Devanagari (7) | 100% | 14.3% | 28.6% | 14.3% |
| Found, Hinglish (4) | 100% | 100% | 75.0% | 75.0% |
| Found, all (83) | 98.8% | 60.2% | 57.8% | 65.1% |
| Must-keep damaged, Latin (53) | 0% | 26.4% | 32.1% | 39.6% |
| Must-keep damaged, Devanagari (7) | 0% | 0% | 0% | 14.3% |
| Must-keep damaged, Hinglish (12) | 0% | 66.7% | 41.7% | 33.3% |

The sample is very small for Devanagari and Hinglish. `selftest.py` itself passes 69/69 with its own,
looser rule. My scorer is stricter, hence our one partial item: the cell "Father Suraj Bhagat", where
"Father" is left. No setup covered it fully. Of the 4 column tables, the one expected address cell was
left out, because it includes label words.

## Speed and memory

Median of 3 runs, 2 CPUs, **network off**, empty home folder. Reading the files is not included.

| Dataset | Setup | Load | Detect | Peak memory |
|---|---|---|---|---|
| dev | Ours | ~0 s | **2.9 s** | **41 MB** |
| dev | Presidio+lg | 2.3 s | 124 s | 787 MB |
| dev | Presidio+lg+headers | 2.1 s | 122 s | 787 MB |
| dev | Presidio+sm | 2.5 s | 116 s | 799 MB |
| dev | Presidio+xx | 4.6 s | 71 s | 1167 MB |
| self-test | Ours | ~0 s | 0.07 s | 18 MB |
| self-test | Presidio (the 4 variants) | 2.5-4.5 s | 0.8-1.0 s | 766-1153 MB |

Our targets are under 60 s and 512 MB. **Every Presidio setup is over both** (all are under the 4 GB limit).
The small model did not save memory here. I did not find out why. I called Presidio once per field and
did not try its batch interface or profile it, so a better integration might be faster.

**Network off:** every timed run used its own network namespace (`unshare -rn`). Each run first checked
that a connection fails, and all 30 passed and finished. One warning: on first use, Presidio's email
recognizer (through the `tldextract` library) **tries to download** a list of web domain endings from
`publicsuffix.org`. Offline, it fails and uses the copy shipped inside the library. The request does not
contain record text, but our rule is no network calls during a run, so this would need to be turned off.
`run_setup.py` only hides the log message. No cloud, remote or LLM recognizer was used, and record text
was only analysed with the network off or by our own local code.

## Where Presidio found something we missed

**dev: 14 items** (Presidio+lg fully covers 10 of them, sm 7, xx 13). All 14 are relative names on WhatsApp
sender lines such as `[date, time] Kamal Bhaiya: <attachment>`. Others end in Chachu, Mama or Papa.

- **Why:** our rule flags only the first word ("Kamal"). The spaCy model often labels both words as
  one PERSON.
- **Does it matter?** The identifying given name is removed. But `truth.json` lists "bhaiya", "mama"
  and so on as name words, so under the formula in `docs/kit/SCORING.md` these should count as half
  leaked (my reading; I did not run the official evaluator). `check_dev.py` would not show it, because
  it only looks for the whole string.

**Self-test: none.**

**Not in either dataset** (`probe_other_ids.py`: invented values, each written bare, with a label and as
a CSV column; this only shows whether a rule exists, not how accurate it is):

| ID | Ours | Presidio+lg | Strength of Presidio's own rule (score for bare / labelled) |
|---|---|---|---|
| Voter ID | missed 3/3 | found 3/3 | 0.4 / 0.75 |
| Passport | missed 3/3 | found 3/3 | weak: 0.1 / 0.45 |
| Vehicle number | missed 3/3 | found 3/3 | 1.0 / 1.0 |
| GSTIN | missed 3/3 | found 3/3 | 1.0 / 1.0 |

- **Why:** `aegis/detect/ids.py` has no pattern for these four. A column or label we do not know about
  could still hide some of them in other wording; I only tried the labels in the script.

## Recommendations, in priority order

None of these has been applied. The first two would be our own small rules and need **no new dependency**.

### 1. Add rules for voter ID, then passport and vehicle number. Recommended.
- **Evidence:** the table above (missed 3/3 each).
- **Benefit:** closes a gap if the hidden data holds these. Practice data has none, so the score gain
  is **unknown**, and may be zero.
- **Cost / risk:** low to medium effort. Loose patterns can eat lab codes or batch numbers. Voter ID
  (3 letters + 7 digits) is fairly distinct. A passport number (letter + 7 digits) is not: require a
  label such as "Passport". This borrows Presidio's idea of letting nearby words decide a weak match.
  For vehicles, use only full plate shapes with real state codes, not its very weak short patterns.
- **GSTIN:** lower priority. It usually identifies a business (perhaps the hospital on a bill), so only
  remove it when the label ties it to the patient. How to handle it is a team decision.
- Check with new self-test cases, including look-alike medical codes that must survive.

### 2. Cover the family word on chat sender lines. Optional and small.
- **Evidence:** the 14 items above, which is every dev item we did not fully cover.
- **Benefit:** probably a very small gain in official recall. Little real privacy gain.
- **Cost / risk:** a few lines. Apply it only where a name is already found on a sender line, because
  words like "Bhai" and "Mama" are common in normal Hinglish sentences. This fix comes from looking at
  practice data, so do not expect it to generalise.

### 3. Do not use spaCy NER as a second opinion for names. Not recommended.
This tests adding Presidio's output on top of ours:

| Added to ours | Extra items found (of our 14) | Extra must-keep phrases damaged |
|---|---|---|
| lg PERSON, all fields | 10 | 758 |
| lg PERSON, free text only | 10 | 153 |
| sm PERSON, all fields | 5 | 936 |
| xx PERSON, all fields | 13 | 664 |
| lg LOCATION, all fields | 0 | 89 |
| Six Indian recognizers (score 0.4 or more) | 0 | 0 |

- All the extra "finds" are the family words from point 2, and a few lines of rules can handle those.
  On the self-test it added nothing and damaged 12-18 phrases.
- **Cost / risk:** two new dependencies (spaCy and a model), a change to SPEC that needs team agreement,
  over 700 MB of memory in my runs, and medical text loss.
- **Still open:** NER might catch a name with no cue and an unlisted surname, which is a known blind spot
  of ours. These datasets cannot test that, because the only name words we miss in `dev/input` are
  those family words (and "Father" in one self-test cell). If someone
  wants to test it, use **fresh** text, free-text fields only, with doctor names and medical words filtered
  out. I did not test such filtering.

### 4. Keep our Aadhaar rule: do not require the checksum. Do not borrow.
- **Evidence:** Presidio's Aadhaar recognizer rejects numbers that fail the Verhoeff checksum. In the
  practice data it found all 56 mentions that pass and **missed all 14 that fail** (of 70). Our rule
  uses the checksum only to tell Aadhaar from a phone number, and found all 70.
- Practice numbers are synthetic, so real data may fail less often. For removing data, rejecting is
  still the risky direction: a mistyped Aadhaar is still personal data.

### 5. Do not add score-based context ranking now.
- **Evidence:** at the default threshold, header words changed no coverage. At a minimum score of 0.6
  they raised Presidio's found rate from 46.2% to 50.6% with the same damage. Below that threshold
  they made no difference. Our rules already use headers and labels more directly, to choose each
  column's role.
- **Cost:** it means reworking how our candidates are ranked. Point 1 only needs a "label required"
  check.

Also **do not copy** the broad patterns that caused noise (weak PAN, UUID, US driver licence).

### Licences, if any code or pattern is copied
Presidio is MIT, so copying code or a distinctive pattern means keeping its copyright and licence
notice. Take the notice from the Presidio repository: I saw no licence file in the installed package's
metadata folder. Writing our own rule from the public ID format is the simpler choice. spaCy and the
three models are listed as MIT (WikiNER data is CC BY 4.0). **Nothing was copied into this experiment.**

## What I did not run

- Any fresh or unseen test data, or any data outside the repo (apart from the invented ID check).
- The full pipeline, `check_dev.py` or the official evaluator with Presidio's findings.
- Presidio tuning: custom recognizers, deny/allow lists, a chosen set of entity types, or Hindi
  settings. I tried only the score thresholds and header context words.
- Presidio's batch, anonymizer, structured-data or image tools, and its Stanza or transformer engines.
- Whether Presidio gives identical results on every run, and any non-Linux system.
- I did not rerun the pipeline's practice results or the unseen-text numbers quoted from our README.

## How to rerun (Linux; installing needs internet, running does not)

```bash
git branch --show-current        # detect/presidio-lab
uv venv -p 3.14 experiments/presidio/.venv
VIRTUAL_ENV=experiments/presidio/.venv uv pip install -r experiments/presidio/requirements.txt
bash experiments/presidio/run_all.sh 3          # about 20 minutes; tables go to out/results.md
cd experiments/presidio && unshare -rn .venv/bin/python -B probe_other_ids.py
```

| File | What it does |
|---|---|
| `common.py` | loads the two datasets |
| `run_setup.py` | runs one setup in its own process; saves character ranges, time and memory |
| `score.py` | the single matching rule and all the tables; `out/details.json` lists our misses |
| `run_all.sh` | runs everything with the network off |
| `probe_other_ids.py` | the voter ID / passport / vehicle / GSTIN check |

`out/` and `.venv/` are not committed. `out/details.json` contains text from the practice data.
`requirements.txt` pins the main packages and models only, not everything they pull in.
