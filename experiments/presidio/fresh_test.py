"""Score fresh cases written by someone who has not read our rules.

    python fresh_test.py <folder>            # check the format, then score (prints no case text)
    python fresh_test.py <folder> --show     # afterwards only: list every failure

<folder> holds lines.jsonl  {"script": "en|hinglish|hi", "line": str, "pii": [str], "keep": [str]}
         and  files.jsonl  {"name": str, "fmt": "csv|json", "records": [{"fields": {}, "pii": [], "keep": []}]}

The matching rule and record layout are those of the round-3 unseen test (aegis/detect/README.md),
so the numbers can be compared with it:
  * every exact occurrence of an expected string in a field is one item;
  * personal data is covered only if EVERY letter and digit of the occurrence is flagged;
  * medical / staff text is lost if any non-date, non-age finding overlaps it;
  * our CONDITION / DISTRICT / GENDER findings do not count (never removed).
For Presidio, DATE_TIME is treated like our DATE / AGE, so both sides get the same allowance.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import common  # noqa: F401  (puts the repo on sys.path)
import run_setup

DATE_TYPES = ("DATE", "AGE", "DATE_TIME")
SIDES = ("ours", "lg", "sm", "xx")


def load(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


def _field(path, kind, context, value):
    return {"path": path, "kind": kind, "context": context, "value": value}


def _record(name, loc, fmt, fields):
    return {"record_id": f"{name}#{loc}", "file": name, "loc": loc, "fmt": fmt, "fields": fields}


def build(case: dict) -> tuple[list, list]:
    """(records of one file, [(record, expectation)] to score)."""
    if "line" in case:
        record = _record("t.txt", "doc", "text", [_field("text", "text", None, case["line"])])
        return [record], [(record, case)]
    fmt, name = case["fmt"], "export." + case["fmt"]
    columns = list(dict.fromkeys(k for r in case["records"] for k in r["fields"]))
    top = [_field("filename", "filename", None, name)]
    if fmt == "csv":
        top += [_field(f"header:{i}", "header", None, c) for i, c in enumerate(columns)]
    records, scored = [_record(name, "@file", fmt, top)], []
    for n, row in enumerate(case["records"]):
        if fmt == "csv":
            fields = [_field(f"col:{i}", "value", c, str(row["fields"].get(c, ""))) for i, c in enumerate(columns)]
            records.append(_record(name, f"row:{n + 1}", fmt, fields))
        else:
            fields = [_field(f"/{n}/" + k.replace(".", "/"), "value", k.split(".")[-1], str(v))
                      for k, v in row["fields"].items()]
            records.append(_record(name, f"/{n}", fmt, fields))
        scored.append((records[-1], row))
    return records, scored


def check_format(cases: list[dict]) -> list[str]:
    """Problems by position only, so no case text is shown before scoring."""
    problems = []
    for c, case in enumerate(cases):
        for r, (record, expected) in enumerate(build(case)[1]):
            for kind in ("pii", "keep"):
                for s, text in enumerate(expected.get(kind, [])):
                    if not text or not any(text in f["value"] for f in record["fields"]):
                        problems.append(f"case {c} record {r} {kind}[{s}] is not in any value")
    return problems


def judge(case: dict, run, extra=None) -> list[tuple]:
    """[(kind, script, ok, context, expected string, field value, [overlapping findings])]."""
    records, scored = build(case)
    spans = run(records)
    if extra:  # union with another setup's chosen findings
        more, pick = extra
        spans = [a + [s for s in b if pick(records[i], s)] for i, (a, b) in enumerate(zip(spans, more(records)))]
    by_id = {r["record_id"]: s for r, s in zip(records, spans)}
    out = []
    for record, expected in scored:
        found = by_id[record["record_id"]]
        for kind in ("pii", "keep"):
            for text in expected.get(kind, []):
                for f in record["fields"]:
                    for m in re.finditer(re.escape(text), f["value"]):
                        here = [s for s in found if s[0] == f["path"] and s[1] < m.end() and m.start() < s[2]]
                        if kind == "pii":
                            flagged = {i for s in here for i in range(s[1], s[2])}
                            ok = all(m.start() + i in flagged for i, ch in enumerate(text) if ch.isalnum())
                        else:
                            here = [s for s in here if s[3] not in DATE_TYPES]
                            ok = not here
                        script = case.get("script") or ("hi" if common.DEVA_RX.search(text) else "latin")
                        out.append((kind, script, ok, f["context"], text, f["value"],
                                    [(s[3], f["value"][s[1]:s[2]]) for s in here]))
    return out


def rate(rows: list[tuple], kind: str) -> tuple[int, int]:
    group = [r for r in rows if r[0] == kind]
    return sum(r[2] for r in group), len(group)


def show_rate(good: int, total: int) -> str:
    return "-" if not total else f"{100 * good / total:.1f}% ({good}/{total})"


def interval(per_case: list[list[tuple]], kind: str, rounds: int = 4000) -> str:
    """95% range when whole cases are resampled (how much the number depends on which cases we got)."""
    counts = [rate(rows, kind) for rows in per_case]
    rng, values = random.Random(1), []
    for _ in range(rounds):
        pick = [counts[rng.randrange(len(counts))] for _ in counts]
        total = sum(t for _, t in pick)
        if total:
            values.append(100 * sum(g for g, _ in pick) / total)
    values.sort()
    return f"{values[int(0.025 * len(values))]:.0f}-{values[int(0.975 * len(values))]:.0f}%"


def main() -> int:
    folder, show = Path(sys.argv[1]), "--show" in sys.argv
    sides = [s for s in SIDES if "--ours-only" not in sys.argv or s == "ours"]
    sets = {"lines": load(folder / "lines.jsonl"), "exports": load(folder / "files.jsonl")}
    for name, cases in sets.items():
        problems = check_format(cases)
        print(f"{name}: {len(cases)} cases, {len(problems)} format problems")
        for p in problems[:20]:
            print("   ", p)
    runs = {s: run_setup.load_ours()[0] if s == "ours" else run_setup.load_presidio(s)[0] for s in sides}
    results = {(s, name): [judge(c, runs[s]) for c in cases] for s in sides for name, cases in sets.items()}
    print(f"network off: {run_setup.network_is_off()}")
    for name, cases in sets.items():
        for kind, title in (("pii", "personal data covered"), ("keep", "medical / staff text kept")):
            print(f"\n### {name}: {title}\n| group | " + " | ".join(sides) + " |\n|" + "---|" * (len(sides) + 1))
            scripts = sorted({r[1] for rows in results[(sides[0], name)] for r in rows})
            for group in [*scripts, "ALL"]:
                cells = [show_rate(*rate([r for rows in results[(s, name)] for r in rows
                                          if group in ("ALL", r[1])], kind)) for s in sides]
                print(f"| {group} | " + " | ".join(cells) + " |")
            print("| 95% range, ALL | " + " | ".join(interval(results[(s, name)], kind) for s in sides) + " |")
            if name == "exports":
                for n, case in enumerate(cases):
                    cells = [show_rate(*rate(results[(s, name)][n], kind)) for s in sides]
                    print(f"| export {n} ({case['fmt']}) | " + " | ".join(cells) + " |")
    if "lg" in sides:  # the open question: does NER help on text our rules have not seen?
        print("\n### ours plus Presidio PERSON (union)\n| set | added | personal covered | medical kept |\n|---|---|---|---|")
        picks = {"nothing": None,
                 "lg PERSON, all fields": ("lg", lambda rec, s: s[3] == "PERSON"),
                 "lg PERSON, free text only": ("lg", lambda rec, s: s[3] == "PERSON" and rec["fmt"] == "text"),
                 "xx PERSON, all fields": ("xx", lambda rec, s: s[3] == "PERSON")}
        for name, cases in sets.items():
            for label, pick in picks.items():
                extra = None if pick is None else (runs[pick[0]], pick[1])
                rows = [r for c in cases for r in judge(c, runs["ours"], extra)]
                print(f"| {name} | {label} | {show_rate(*rate(rows, 'pii'))} | {show_rate(*rate(rows, 'keep'))} |")
    if show:
        for name, cases in sets.items():
            for n, case in enumerate(cases):
                for kind, script, ok, context, text, value, hits in results[("ours", name)][n]:
                    if not ok:
                        others = {s: results[(s, name)][n] for s in sides if s != "ours"}
                        also = [s for s, rows in others.items()
                                if any(r[0] == kind and r[4] == text and r[5] == value and r[2] for r in rows)]
                        print(f"{name} {n} {'MISSED' if kind == 'pii' else 'LOST'} [{script}] [{context}] {text!r} "
                              f"in {value[:150]!r} ours_hits={hits} right_in={also}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
