"""Capability probe, NOT part of the comparison: which Indian ID types do the two sides know?

Neither dataset contains a voter ID, passport, vehicle number or GSTIN, so the main run says nothing
about them. The values below are invented to fit each format. A few hand-written strings show
only whether a rule exists; they are not an accuracy measurement. Run offline, like run_all.sh.
"""
from __future__ import annotations

import common  # noqa: F401  (puts the repo on sys.path)
import run_setup

IDS = {"voter ID": ("Voter ID", "XKD4829137"), "passport": ("Passport No", "M4827163"),
       "vehicle": ("Vehicle No", "MH12QX4821"), "GSTIN": ("GSTIN", "27QWXPE4412L1Z5")}


def records(label: str, value: str) -> dict:
    forms = {"bare": ("text", None, f"Noted {value} today."), "labelled": ("text", None, f"{label}: {value}"),
             "column": ("col:0", label, value)}
    return {name: {"record_id": f"p#{name}", "file": "p.txt" if path == "text" else "p.csv", "loc": "doc",
                   "fmt": "text" if path == "text" else "csv",
                   "fields": [{"path": path, "kind": "text" if path == "text" else "value", "context": ctx,
                               "value": text}]} for name, (path, ctx, text) in forms.items()}


def main() -> int:
    sides = {"ours": run_setup.load_ours()[0], "Presidio+lg": run_setup.load_presidio("lg")[0]}
    print("| ID | form | ours | Presidio+lg (label:score) |\n|---|---|---|---|")
    for kind, (label, value) in IDS.items():
        for form, record in records(label, value).items():
            cells = []
            for side, run in sides.items():
                start = record["fields"][0]["value"].index(value)
                hits = [s for s in run([record])[0] if s[1] < start + len(value) and s[2] > start]
                got = {i for s in hits for i in range(s[1], s[2])} >= set(range(start, start + len(value)))
                names = sorted({s[3] if side == "ours" else f"{s[3]}:{s[4]}" for s in hits})
                cells.append(("found " if got else "partial " if hits else "missed") + " ".join(names))
            print(f"| {kind} | {form} | {cells[0]} | {cells[1]} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
