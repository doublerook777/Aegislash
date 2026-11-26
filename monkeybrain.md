# monkeybrain.md: Aegislash explained simply

This is the plain-language guide for the four of us. You don't need to read any code to understand it. If a word confuses you, check the glossary at the bottom.

---

## 1. What are we building, in one breath?

A program that takes a messy pile of hospital files and gives back a **clean copy**:

- every personal detail is removed or blurred (names, phone numbers, Aadhaar, addresses, exact birthdays, ...);
- every medical detail stays **exactly** as it was (BP 117/82, "Paracetamol 500mg 1-0-1", "Addison's disease", ...);
- the same patient gets **the same code name** in every file (`PSN-7KQ2MX`), even if their name is written in English in one file and in Hindi in another.

It runs offline on a normal laptop CPU, with no AI chatbot (no LLM) and no internet. It's just rules, word lists and careful code.

**Analogy:** we are a black-marker censor at a hospital records office. Doctors may read everything medical. Nobody should be able to work out *who* the patient is.

---

## 2. Why is this hard?

The files are deliberately nasty:

| Problem | Example |
|---|---|
| Three ways of writing | English `Ramesh Kumar`, Hindi `रमेश कुमार`, Hinglish `Ramesh ji ko bukhar hai` |
| Many file types | CSV, TSV, JSON, FHIR (a hospital JSON standard), plain text notes |
| Broken encodings | UTF-16, Windows cp1252, files with a BOM, half-corrupted text |
| PII in odd places | file names, column headers, JSON keys, base64-encoded attachments |
| Medical "traps" | `Dr. Ramesh` (a doctor, keep it), `C/O fever` (complaint of, keep it) vs `C/O Ramesh` (care of, a relative, remove it) |
| Same name, different people | Two different "Sunita Devi"s must **not** be merged |
| Attacker | The judges run a program holding a voter list. It tries to re-identify patients from what we leave behind (age, village, visit date, rare disease). |

---

## 3. How do we get points?

The judges run our program on 3 hidden datasets (one has formats we've never seen) and score us out of 100:

| Category | Points | In plain words |
|---|---|---|
| Privacy vs attacker | 25 | The attacker can't work out who anyone is |
| Detection | 20 | We found the personal info (missing some hurts more than over-removing) |
| Clinical utility | 20 | Medical values are still there, unchanged |
| Identity resolution | 15 | Same patient → same code name. Wrongly merging two people hurts more than missing a match |
| Integrity | 10 | Output files have the same structure as the input and are valid |
| Speed / reliability | 10 | Fast, low memory, never crashes |

Penalties: −1 for each leaked identifier, −3 for each "canary" (secret test value the judges planted), −10 if we claim success when we failed, and more. The organizers' own solution scores about 80–85. The starter code they gave out scores about 8.

**Golden rule:** when in doubt, remove it. A leak costs more than an over-cleaned word.

---

## 4. The big picture: one assembly line, four stations

```
   input folder                                                   output folder
  (raw hospital files)                                         (clean copy + reports)
        │                                                               ▲
        ▼                                                               │
  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────────┐   ┌──────────┐
  │    io     │ →  │  detect   │ →  │   link    │ →  │  privacy   │ → │    io    │
  │  (read)   │    │ "what is  │    │ "who is   │    │ "what do   │   │ (write + │
  │           │    │ personal?"│    │  who?"    │    │ we replace │   │  final   │
  │           │    │           │    │           │    │  it with?" │   │  check)  │
  └───────────┘    └───────────┘    └───────────┘    └────────────┘   └──────────┘
   Member-1         Member-2         Member-3         Member-4          Member-1
```

It's done in **two passes**:

1. **Pass 1 (look at everything):** read every file, find everything personal in it. Nothing gets written yet.
2. **Middle:** with the whole dataset in view, decide which records belong to the same patient (link), then decide how to blur each one (privacy).
3. **Pass 2 (write):** apply the replacements, run a final safety check, write the clean files.

Why two passes? To link "Ramesh in file A" with "रमेश in file Z", you have to have seen both files first.

---

## 5. Follow one note through the machine

Input: a nursing note in a text file:

> Shahid sahab ka BP 117/82. Dr. Ramesh ne dekha. Attendant (S/o Zubair) ph 9876543210.

**Step 1: io reads it.** It works out the file encoding, sees it's a text file and turns it into one *record* (one patient's chunk of data). Each piece of text inside a record is a *field*.

**Step 2: detect looks for personal info** and reports *findings*: "characters 0–6 are a PATIENT_NAME (`Shahid`)", "63–69 is a RELATIVE_NAME (`Zubair`)", "74–84 is a PHONE". It deliberately does **not** flag `Dr. Ramesh` (a doctor) or `117/82` (a medical value). It also writes down *evidence* for linking: name = Shahid, relative = Zubair, phone = 9876543210.

**Step 3: link decides who this is.** It compares this evidence with every other record in the dataset. Same phone number found in a CSV row for "Mohd. Shahid"? Same person. Both records get the same secret *patient key*, which becomes the code name `PSN-XXXXXX`.

**Step 4: privacy decides the replacements.** Patient name → `PSN-XXXXXX`. Relative's name → `[RELATIVE_NAME]`. Phone → `[PHONE]`. A date would be shifted by a secret number of days that's the same for all of this patient's dates. An age `48/M` would become `45-49/M`.

**Step 5: io writes the clean file:**

> PSN-7KQ2MX sahab ka BP 117/82. Dr. Ramesh ne dekha. Attendant (S/o [RELATIVE_NAME]) ph [PHONE].

Before saving, the **leak gate** scans the finished file for any raw value we found anywhere in the dataset. If it still sees `9876543210` (or `Shahid Khan`, or an Aadhaar number), it refuses to write that file and puts it in *quarantine* instead. Better to skip a file than leak.

---

## 6. The four modules (who does what)

### io: Member-1 (done ✅)
The front door and the back door. Lives in `main.py` and `aegis/io/`.
- Walks the input folder in a fixed order (so running it twice gives byte-identical output).
- Decodes text in any encoding; reads CSV/TSV/JSON/FHIR/text; decodes base64 attachments.
- Splits files into records (a CSV row, a JSON patient entry, or a whole text document).
- After everyone else has done their job, puts the replacements back in the exact same place and keeps the file structure identical.
- Renames files whose *names* contain PII.
- Runs the leak gate, quarantines anything unsafe or unreadable.
- Writes `sanitized/`, `report.json` and `records.jsonl`.

Since io is finished, Member-1 now helps with detect.

### detect: Member-2 (hardest 🔥)
The eyes. Lives in `aegis/detect/`. Answers: "which bits of this text are personal?"
- Patterns for numbers: phone (all formats), Aadhaar (with its checksum), ABHA, MRN/UHID, PAN, PIN, email, dates.
- Names in English, Hindi and Hinglish, using clues like `Name:`, `Mr./Smt.`, `ji`, `sahab`, `didi`, `S/o D/o W/o`, `Attendant`, plus name lists and transliteration.
- Guessing what a column holds from its header **and** its values, so `pt_nm` or `मरीज़ का नाम` still counts as a name column.
- Protecting medical text (the "meaning traps": `Dr. X`, `C/O fever`, doses, lab values).
- Collecting evidence (name, DOB, relatives, IDs, village, age) for link.

### link: Member-3 (hard)
The memory. Lives in `aegis/link/`. Answers: "which records are the same human?"
- Turns names into one comparable form across scripts (`रमेश` ≈ `Ramesh`).
- Strong ID match (same Aadhaar/phone/MRN) → same person.
- Same name **plus** a second clue (DOB, relative's name, village + similar age) that is unique in the dataset → same person.
- Not sure → `None` (no code name). Wrongly merging two people is worse than missing a match.
- Turns a patient key into `PSN-XXXXXX` using a secret (HMAC). This part is already done.

### privacy: Member-4 (medium, but worth the most points)
The blur tool. Lives in `aegis/privacy/`. Answers: "what does each personal bit become?"
- Names and MRN of linked patients → their `PSN-XXXXXX`.
- Other direct identifiers (phone, Aadhaar, ...) → `[PHONE]`, `[AADHAAR]`, ...
- Dates → shifted by a secret per-patient number of days, keeping the same format. Gaps between a patient's visits stay the same, which matters for the research.
- Ages → 5-year bands. PIN → first 3 digits + `***`. Village → district or `[VILLAGE]`.
- Rare disease in a tiny group → blur more, so the attacker can't single them out.
- Also owns the README, the 2-page brief, and a script that measures our own re-identification risk.

---

## 7. How the modules talk: contracts

Each station passes a box to the next. A **contract** is the agreed shape of that box, written down so nobody has to read anyone else's code.

| Box | Plain meaning | Who makes it → who uses it |
|---|---|---|
| **Record** | one patient-chunk of a file, with its fields (the text plus a hint like the column header) | io → detect |
| **Finding** | "from character X to Y in field Z is a PHONE" | detect → privacy, io |
| **Evidence** | the identity clues of one record (names, IDs, DOB, village, ...) | detect → link |
| **patient key** | "this record belongs to patient #abc" (or `None`) | link → privacy, io |
| **Replacement** | "replace this finding with this text" | privacy → io |

The details are in `contracts/*.md` (for humans) and `contracts/*.contract.json` (for the checker). The shared shapes are in `aegis/types.py`.

**Mocks:** until your neighbour finishes, their module is a *mock*: a fake that returns example answers in the right shape. That's why everyone can run the whole program from day one. When the real module is ready it replaces the mock, and nobody else changes anything.

**Contract rules:**
- Adding a new *optional* field: fine, just note it in `SPEC.md`.
- Changing or removing a field: both owners must agree.
- After the freeze (4 hours before the deadline): no changes unless the demo is broken.

---

## 8. Where things live

```
Aegislash/
├── main.py              ← the program the judges run (just calls aegis/io)
├── raksha.toml          ← tells the judges how to install and run us
├── aegis/
│   ├── types.py         ← shared box shapes (part of the contract)
│   ├── io/              ← Member-1: read, write, leak gate, reports
│   ├── detect/          ← Member-2: find PII
│   ├── link/            ← Member-3: same-patient matching + PSN codes
│   └── privacy/         ← Member-4: what each PII becomes
├── contracts/           ← the agreed box shapes + examples
├── scripts/check_contracts.py  ← tests that each module keeps its contract
├── config/policy.yaml   ← privacy settings
├── dev/                 ← practice data from the organizers (input + answer key)
├── validate_output.py   ← kit: "is our output in the right format?"
├── check_dev.py         ← kit: "how many leaks? medical values kept? linking score?"
├── check_submission.py  ← kit: "is the repo ready to submit?"
├── docs/kit/            ← the organizers' rules and scoring docs
├── brief/               ← template for our 2-page brief
├── SPEC.md              ← the plan, the status table, open questions
├── KICKOFF.md           ← each member's starting prompt
├── CONVENTIONS.md       ← branch and commit naming
└── monkeybrain.md       ← you are here
```

---

## 9. Running it

One-time setup:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Run on the practice data:
```bash
RAKSHA_SECRET=practice .venv/bin/python main.py --input dev/input --output out
```

Check the result:
```bash
.venv/bin/python validate_output.py --input dev/input --output out   # format OK?
.venv/bin/python check_dev.py --output out                           # leaks, medical kept, linking
.venv/bin/python scripts/check_contracts.py                          # does my module keep its contract?
.venv/bin/python check_submission.py --run                           # ready to submit?
```

What you get in `out/`:
- `sanitized/`: the clean copy of every file, same folders, same names (unless the name held PII).
- `records.jsonl`: one line per record: which file, where in the file, and which `PSN-` code (or none).
- `report.json`: counts (files, records, identifiers found, linked, quarantined), timing, memory.

`RAKSHA_SECRET` is the secret key for code names and date shifts. Never print it, log it or save it anywhere.

---

## 10. Team rules

1. **Only edit your own folder** (`aegis/<your module>/`). Need something from a neighbour? Read their contract, don't read their code.
2. **Branch per task:** `detect/phone-regex`, `link/translit`, ... **Commit messages:** `detect: add Aadhaar checksum`.
3. **Run `check_contracts.py` and `check_dev.py` before you ask for a merge.** A human merges, not the AI.
4. **Contract question?** Write it in `SPEC.md` → Open questions. Don't decide it alone.
5. **Never print personal data**, not even while debugging. Print counts and types only. The judges scan our logs, temp files and error messages for PII.
6. **Update the Status table** in `SPEC.md` with a line or two when you finish something.
7. **Understand your module.** The judges ask each of us technical questions in the desk review.

---

## 11. Questions the judges might ask (and short answers)

- **Why no LLM?** The rules forbid it. Also, rules are explainable and deterministic, run on a CPU, and never send data anywhere.
- **How do you stop leaks you missed?** The leak gate: every raw identifier found anywhere in the dataset is searched for again in every output file and file name. Any hit means that file is quarantined, not written.
- **How do you avoid merging two different people?** We only link on a strong ID, or a name plus a second unique clue. Otherwise we leave the record unlinked. A wrong merge costs more than a missed one.
- **Why shift dates instead of deleting them?** Researchers need time gaps (length of stay, days between visits). A per-patient secret shift keeps the gaps but hides the real dates.
- **What if the program crashes on one file?** That file is quarantined with a reason code. The run continues, and nothing half-written is saved.
- **Is output the same every run?** Yes. Fixed file order, no randomness, so the same input and secret give byte-identical output. A different secret gives different codes and shifts.
- **Where is data stored?** Only in memory while running. Nothing goes to temp files or the home folder.

---

## 12. Glossary

| Word | Meaning |
|---|---|
| **PII** | Personally Identifiable Information: anything that points to a specific person |
| **Direct identifier** | Points to a person on its own: name, phone, Aadhaar, MRN, email, address |
| **Quasi-identifier** | Harmless alone, identifying in combination: age, DOB, village, PIN, visit date |
| **Record** | One patient's chunk of a file (a CSV row, a JSON patient entry, a whole note) |
| **Field** | One piece of text inside a record (a cell, a JSON value, a file name) |
| **Finding** | "this span of text is personal info of type X" |
| **Evidence** | the identity clues of a record, used for linking |
| **Linking** | deciding that two records are the same person |
| **Pseudonym / PSN** | the code name `PSN-XXXXXX`, the same for every record of one patient |
| **HMAC** | a way to turn a key + secret into a code nobody can reverse without the secret |
| **Date shift** | moving all of one patient's dates by the same secret number of days |
| **Age band** | 48 → 45-49 |
| **Quarantine** | a file we refuse to output (unreadable, broken or unsafe), listed in the report with a reason |
| **Leak gate** | the final scan that blocks any output still containing a raw identifier |
| **Canary** | a fake secret value the judges plant. Leaking it costs −3 |
| **Mock** | a fake version of a module returning example answers, so others aren't blocked |
| **Contract** | the agreed shape of what one module hands to another |
| **Freeze** | 4 hours before the deadline: no more contract changes |
| **F2 / F0.5** | scores that weigh mistakes. F2: missing PII hurts more. F0.5: wrong merges hurt more |
| **FHIR** | a hospital JSON standard. Our output must still be valid FHIR |
| **Transliteration** | writing a word in another script: `रमेश` ↔ `Ramesh` |
| **Deterministic** | same input → exactly the same output, every time |
