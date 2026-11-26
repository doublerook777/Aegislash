# Aegislash: privacy firewall for Track 3 "Secret Wards"

Offline, CPU-only, LLM-free de-identification of multi-hospital records (English, Hindi, Hinglish).

> Work in progress. Plan: [SPEC.md](SPEC.md). Contracts: [contracts/](contracts/). Team rules: [CONVENTIONS.md](CONVENTIONS.md).

## Run
```bash
pip install -r requirements.txt
RAKSHA_SECRET=<secret> python main.py --input <input dir> --output <empty output dir>
python3 validate_output.py --input dev/input --output <output dir>   # must print CONTRACT OK
python3 check_dev.py --output <output dir>                            # practice self-check
```

## Models
None. Rules, gazetteers and transliteration only (no LLMs, no pretrained transformers).

## Credits
`dev/`, `docs/kit/`, `validate_output.py`, `check_dev.py`, `check_submission.py`, `scoring.toml`, `brief/` and the
starting skeleton of `main.py` come from the organizers' Secret Wards ToolKit (MIT).
