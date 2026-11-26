Write test data only: a new batch of test cases.
For this task do NOT open, search or run ANY existing file or folder: no code, docs, rules, practice data or earlier test batches. The tests must be written without knowing how the detector works. Do not commit, push or open a PR. Do not start other agents.

We test a rule-based detector of personal data in INDIAN hospital data. All data must be invented. Create a new folder called batch/ and write these two files (JSON Lines, UTF-8).

pii = patient or relative names, phone numbers, Aadhaar (also masked), ABHA number/address, hospital record numbers (UHID/MRN/IPD), email, PAN, insurance IDs, house numbers, localities, landmarks, village names, 6-digit PIN codes, full dates of birth.
keep = drug names and doses, dose patterns like 1-0-1, vitals, lab values and ranges, diagnoses, ICD codes, diseases named after people, doctor names written with Dr (or in a doctor column), ward names, ASHA worker, hospital names, bill amounts.
Dates other than birth dates, and ages, go in neither list. Visit, bill, sample, lab and ambulance run numbers are not patient identifiers: put them in neither list.
A pii or keep string holds only the value itself, not its label words ("Village", "S/o", "Mob:" stay outside). Every pii/keep string must appear exactly in the line / in one of the values.

1. batch/lines.jsonl: 60 cases, one per line: {"script": "en" | "hinglish" | "hi", "line": "...", "pii": [...], "keep": [...]}
   One line of hospital text each: 25 English ("en"), 20 Hinglish ("hinglish"), 15 Hindi in Devanagari ("hi"). Try hard to break a detector: names introduced only by context, relatives in many wordings, unusual labels/abbreviations/separators, oddly written phones and record numbers, traps where a medicine/disease/organisation/ordinary word looks like a name. Use varied names from all Indian regions and communities.

2. batch/files.jsonl: 8 different invented hospital exports, one JSON object per line:
   {"name": "x", "fmt": "csv" or "json", "records": [ {"fields": {"<column or key>": "<string>", ...}, "pii": [...], "keep": [...]}, ... 6 records ]}
   Records in one export use the same columns (at least 10): include patient name, a relative, phone, record number, address parts, doctor, diagnosis, drug, lab or vital, and free-text remarks that mention people.
   Each export must use a very different, UNUSUAL naming style for columns. For json, keys may be dotted like "demographics.fullNm" meaning nesting.

This batch must be INDEPENDENT of any test data written before: do not reuse or lightly edit earlier lines, names, phone numbers, IDs, column names, export themes or sentence templates. Imagine different sources again, for example: eye camp register, mental health helpline log, organ donor form, school health check sheet, home-care visit diary, ICU transfer summary, mortuary or medico-legal register, vaccination SMS replies, billing dispute emails. Write the way tired staff really type, with inconsistent punctuation and spacing.

Before finishing, check that both files parse, the counts are right and every pii/keep string is present. Finish with a one-paragraph report that lists which files you opened. Do not do anything else.
