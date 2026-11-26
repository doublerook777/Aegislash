#!/usr/bin/env python3
"""Contract check for in-process Python contracts (adapted from the hammer-skill HTTP checker).

Every module boundary in Aegislash is a Python function call, so instead of calling HTTP
endpoints this script imports each contract's function, calls it with the example inputs,
and validates the result against the schema.

Usage (from the repo root):
    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python scripts/check_contracts.py              # check whatever each module exports now
    .venv/bin/python scripts/check_contracts.py --mock       # also exact example answers + mock-only error cases
    .venv/bin/python scripts/check_contracts.py --only link

Exit code: 0 all cases pass, 1 any case fails, 2 no contracts found.

Contract file format: contracts/<name>.contract.json
{
  "name": "link", "provider": "link", "consumer": "io",
  "setup": {"call": "pkg.mod:func", "args": [...], "env": {...}, "as": "plan"},      # optional
  "cases": [
    {
      "case": "human-readable name",
      "call": "aegis.link:resolve",                  # module:function
      "args": [ <arg>, ... ],                        # positional arguments, see below
      "env": {"RAKSHA_SECRET": "practice"},          # optional; "" means unset
      "expect": "return" | "raise",
      "exception": "RuntimeError",                   # optional, for expect=raise
      "message": "secret_missing",                   # optional, for expect=raise
      "response_schema": {...},                      # JSON Schema; may use "#/$defs/<Name>" from contracts/types.schema.json
      "deterministic": true,                         # optional: call twice, results must be identical
      "checks": ["same_length_as_arg0", ...],        # optional extra checks, see CHECKS below
      "example_only": {"equals": <value>},           # optional: exact answer, enforced only with --mock
      "mock_only": true                              # optional: whole case runs only with --mock
    }
  ]
}

Argument forms: a literal JSON value; {"$file": "path.json"} (loaded JSON);
{"$file": "path.json", "$key": "results"} (one key of it); {"$ref": "plan"} (the setup result).
Paths are relative to the repo root.
"""
from __future__ import annotations

import argparse
import copy
import glob
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit("jsonschema missing: .venv/bin/pip install -r requirements-dev.txt")

DEFS = json.loads((ROOT / "contracts" / "types.schema.json").read_text(encoding="utf-8"))["$defs"]


class env:
    """Temporarily set environment variables ("" = unset)."""

    def __init__(self, values: dict | None):
        self.values, self.saved = values or {}, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            if v == "":
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def resolve_func(spec: str):
    mod, _, name = spec.partition(":")
    return getattr(importlib.import_module(mod), name)


def resolve_arg(a, refs):
    if isinstance(a, dict) and "$file" in a:
        data = json.loads((ROOT / a["$file"]).read_text(encoding="utf-8"))
        return data[a["$key"]] if "$key" in a else data
    if isinstance(a, dict) and "$ref" in a:
        return refs[a["$ref"]]
    return copy.deepcopy(a)


def validate(schema, value):
    schema = dict(schema)
    schema["$defs"] = DEFS
    errs = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message[:200]}" for e in errs]


def as_json(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


# ---- extra checks ------------------------------------------------------------------------
def check_same_length_as_arg0(result, args, case):
    if len(result) != len(args[0]):
        return f"returned {len(result)} results for {len(args[0])} records"
    for got, rec in zip(result, args[0]):
        if got.get("record_id") != rec["record_id"]:
            return f"order mismatch: {got.get('record_id')} != {rec['record_id']}"
    return None


def check_spans_match_arg0(result, args, case):
    for got, rec in zip(result, args[0]):
        values = {f["path"]: f["value"] for f in rec["fields"]}
        by_path = {}
        for f in got["findings"]:
            if f["path"] not in values:
                return f"finding on unknown path {f['path']!r}"
            v = values[f["path"]]
            if not (0 <= f["start"] < f["end"] <= len(v)) or v[f["start"]:f["end"]] != f["text"]:
                return f"span {f['start']}:{f['end']} does not match its text in {f['path']!r}"
            by_path.setdefault(f["path"], []).append((f["start"], f["end"]))
        for spans in by_path.values():
            spans.sort()
            if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
                return "overlapping findings in one field"
    return None


def check_keys_match_arg0_record_ids(result, args, case):
    want = sorted(e["record_id"] for e in args[0])
    return None if sorted(result) == want else "output keys differ from input record_ids"


def check_reversed_input_same_output(result, args, case):
    again = resolve_func(case["call"])(list(reversed(copy.deepcopy(args[0]))), *args[1:])
    return None if as_json(again) == as_json(result) else "output depends on input order"


def run_check(name, result, args, case):
    if name.startswith("differs_under_env:"):
        k, _, v = name.split(":", 1)[1].partition("=")
        with env({k: v}):
            other = resolve_func(case["call"])(*copy.deepcopy(args))
        return None if as_json(other) != as_json(result) else f"same result with {k} changed"
    fn = globals().get(f"check_{name}")
    return fn(result, args, case) if fn else f"unknown check {name!r}"


# ---- runner ------------------------------------------------------------------------------
def run_case(case, refs, mock):
    args = [resolve_arg(a, refs) for a in case.get("args", [])]
    func = resolve_func(case["call"])
    with env(case.get("env")):
        try:
            result = func(*copy.deepcopy(args))
        except Exception as exc:  # noqa: BLE001
            if case["expect"] != "raise":
                return False, f"raised {type(exc).__name__}"
            if case.get("exception") and type(exc).__name__ != case["exception"]:
                return False, f"raised {type(exc).__name__}, expected {case['exception']}"
            if case.get("message") and str(exc) != case["message"]:
                return False, "raised with the wrong message"
            return True, f"raised {type(exc).__name__} as expected"
        if case["expect"] == "raise":
            return False, "returned normally, expected an exception"
        problems = validate(case.get("response_schema", {}), result)
        if problems:
            return False, "; ".join(problems[:3])
        if case.get("deterministic") and as_json(func(*copy.deepcopy(args))) != as_json(result):
            return False, "not deterministic (two calls differ)"
        for name in case.get("checks", []):
            msg = run_check(name, result, args, case)
            if msg:
                return False, msg
        if mock and "example_only" in case:
            want = resolve_arg(case["example_only"]["equals"], refs)
            if as_json(want) != as_json(result):
                return False, "does not equal the contract's example response"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", default=str(ROOT / "contracts"))
    ap.add_argument("--only")
    ap.add_argument("--mock", action="store_true", help="also check exact example answers and mock-only cases")
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(a.contracts, "*.contract.json")))
    if a.only:
        paths = [p for p in paths if Path(p).name == f"{a.only}.contract.json"]
    if not paths:
        print("no contracts found")
        return 2
    failed = total = 0
    for p in paths:
        c = json.loads(Path(p).read_text(encoding="utf-8"))
        print(f"== {c['name']} ({c['provider']} -> {c['consumer']})")
        refs = {}
        if "setup" in c:
            s = c["setup"]
            try:
                with env(s.get("env")):
                    refs[s["as"]] = resolve_func(s["call"])(*[resolve_arg(x, refs) for x in s.get("args", [])])
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL  setup {s['call']}: raised {type(exc).__name__}")
                failed += len(c["cases"])
                total += len(c["cases"])
                continue
        for case in c["cases"]:
            if case.get("mock_only") and not a.mock:
                print(f"  skip  {case['case']} (mock only)")
                continue
            total += 1
            try:
                ok, msg = run_case(case, refs, a.mock)
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, f"checker error: {type(exc).__name__}"
            failed += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {case['case']}" + ("" if ok and msg == "ok" else f"  [{msg}]"))
    print(f"\n{total - failed}/{total} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
