"""Counts only: no case text is printed, so a fresh batch stays unread.

    python compare_blind.py <cases folder> <revision> [revision ...]

For each version of aegis/: how many items differ from the first version, and what SHAPE the missed values have.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHILD = """
import json,sys,hashlib
from pathlib import Path
import fresh_test as ft, run_setup
run = run_setup.load_ours()[0]; out = []
for name in ('lines.jsonl','files.jsonl'):
    for c in ft.load(Path(sys.argv[1])/name):
        records, scored = ft.build(c)
        out += [[name, r[0], r[2], r[4]] for r in ft.judge(c, run)]
        spans = run(records)
        out.append([name, 'findings', hashlib.sha256(json.dumps(spans).encode()).hexdigest(), ''])
print(json.dumps(out))
"""


def shape(text: str) -> str:
    digits = sum(ch.isdigit() for ch in text)
    if "@" in text:
        return "email or ABHA address"
    if digits == 0:
        script = "Devanagari" if re.search(r"[ऀ-ॿ]", text) else "Latin"
        return f"{script} words, {'1' if len(text.split()) == 1 else '2+'}"
    if digits <= 4 and len(text) <= 6:
        return "short number (at most 4 digits)"
    if digits >= 10 and not re.search(r"[A-Za-z]{2}", text):
        return "long number (10+ digits)"
    if digits == 6 and len(text) <= 7:
        return "six-digit number"
    if re.fullmatch(r"\d{1,4}[-/. ]\w{1,9}[-/. ]\d{2,4}", text) or re.fullmatch(r"(19|20)\d{6}", text):
        return "date-like"
    return "other value with digits"


def main() -> int:
    cases, revisions = Path(sys.argv[1]).resolve(), sys.argv[2:]
    repo = subprocess.check_output(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip()
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        for rev in revisions:
            side = Path(tmp) / rev.replace("/", "_") / "experiments" / "presidio"
            side.mkdir(parents=True)
            archive = subprocess.run(["git", "-C", repo, "archive", rev, "aegis"], check=True, capture_output=True)
            subprocess.run(["tar", "-x", "-C", str(side.parents[1])], input=archive.stdout, check=True)
            for name in ("common.py", "run_setup.py", "fresh_test.py"):
                (side / name).write_bytes((HERE / name).read_bytes())
            raw = subprocess.check_output([sys.executable, "-B", "-c", CHILD, str(cases)], cwd=side, text=True)
            results[rev] = json.loads(raw)
    base = results[revisions[0]]
    print("version   items scored differently from the first | cases whose findings differ at all")
    for rev in revisions[1:]:
        pairs = list(zip(base, results[rev]))
        scored = sum(a[2] != b[2] for a, b in pairs if a[1] != "findings")
        changed = sum(a[2] != b[2] for a, b in pairs if a[1] == "findings")
        print(f"{rev:10}{scored:6} | {changed}")
    last = results[revisions[-1]]
    for name in ("lines.jsonl", "files.jsonl"):
        group = [r for r in last if r[0] == name and r[1] == "pii"]
        total, missed = Counter(shape(r[3]) for r in group), Counter(shape(r[3]) for r in group if not r[2])
        print(f"\n{name} at {revisions[-1]}: missed / all, by shape of the expected value")
        for kind, n in total.most_common():
            print(f"  {kind:34}{missed[kind]:4} / {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
