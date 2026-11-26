# Conventions

- **Branches:** `<module>/<short-topic>`, e.g. `detect/hindi-names`, `link/cross-script`, `io/fhir`, `privacy/date-shift`. Branch from `main`, merge back small and often.
- **Commits:** `<module>: <what changed>` in the imperative, e.g. `detect: add Verhoeff check for Aadhaar`.
- **Folders:** you only edit your own `aegis/<module>/`. Shared files (`aegis/types.py`, `contracts/`, `SPEC.md`) change only under the change rules in SPEC.md. `main.py` and `raksha.toml` belong to io.
- **Before every merge:** `.venv/bin/python scripts/check_contracts.py` passes, and (once io calls the modules) `RAKSHA_SECRET=practice .venv/bin/python main.py --input dev/input --output out && python3 validate_output.py --input dev/input --output out` prints CONTRACT OK.
- **Measure:** `python3 check_dev.py --output out` after each change; paste the headline numbers in your PR/commit message.
- **Never:** print, log or write raw values (counts only); iterate a `set` to make output (sort instead); add hardcoded practice names or file names; make network calls; commit `out/` or `.venv/`.
- **Setup:** `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.
