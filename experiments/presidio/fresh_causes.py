"""After the blind score only: how much does each confirmed cause explain?

Changes ONE thing in an in-memory copy of the cases and rescores. aegis/ is not touched.
These are diagnosis numbers made after reading failures, never unseen-data results.

    python fresh_causes.py fresh
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import fresh_test as ft
import run_setup

ADDRESS = ("geo_hamlet_pin", "Home Place & Pin", "PostalLine")  # read as "PIN code only"
HEADER_SETS = {"3 address headers made neutral": ADDRESS, "'Kin.Ref' made neutral": ("Kin.Ref",),
               "'Bed & Patient' made neutral": ("Bed & Patient",),
               "all 5 headers made neutral": (*ADDRESS, "Kin.Ref", "Bed & Patient")}


def neutral_headers(case: dict, headers: tuple) -> dict:
    case = copy.deepcopy(case)

    def new_key(key: str) -> str:
        parts = key.split(".") if case["fmt"] == "json" else [key]
        if case["fmt"] == "csv" and key in headers:
            return f"zz{headers.index(key)}"
        if case["fmt"] == "json" and parts[-1] in headers:
            return ".".join([*parts[:-1], f"zz{headers.index(parts[-1])}"])
        return key

    for record in case["records"]:
        record["fields"] = {new_key(k): v for k, v in record["fields"].items()}
    return case


def capital_house(case: dict) -> dict:
    case = copy.deepcopy(case)
    fix = lambda s: re.sub(r"\bh\.no\b", "H.No.", str(s))  # noqa: E731
    for record in [case] if "line" in case else case["records"]:
        record["pii"] = [fix(s) for s in record["pii"]]
        if "line" in record:
            record["line"] = fix(record["line"])
        else:
            record["fields"] = {k: fix(v) for k, v in record["fields"].items()}
    return case


def main() -> int:
    folder = Path(sys.argv[1])
    run = run_setup.load_ours()[0]
    lines, exports = ft.load(folder / "lines.jsonl"), ft.load(folder / "files.jsonl")

    def report(label: str, name: str, cases: list) -> None:
        rows = [r for c in cases for r in ft.judge(c, run)]
        print(f"{name:8} {label:34} covered {ft.show_rate(*ft.rate(rows, 'pii'))}   "
              f"kept {ft.show_rate(*ft.rate(rows, 'keep'))}")

    report("as written", "exports", exports)
    for label, headers in HEADER_SETS.items():
        report(label, "exports", [neutral_headers(c, headers) for c in exports])
    report("as written", "lines", lines)
    report("'h.no' written 'H.No.'", "lines", [capital_house(c) for c in lines])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
