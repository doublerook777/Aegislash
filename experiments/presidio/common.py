"""Inputs shared by every setup: the two datasets, as detect Records.

Both come from files already in the repo. dev/input is read with Aegislash's own io parser, so
every setup sees exactly the same fields (CSV cells, JSON leaves, decoded base64, file names).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out"
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from aegis.detect import selftest  # noqa: E402
from aegis.io.decode import decode  # noqa: E402
from aegis.io.formats import SUPPORTED_EXT, Unsupported, parse  # noqa: E402


def dev_files() -> list[tuple[str, list]]:
    """[(relative path, records)] for every file our pipeline can read (same skips as io)."""
    inp, out = ROOT / "dev" / "input", []
    for path in sorted((p for p in inp.rglob("*") if p.is_file()), key=lambda p: p.relative_to(inp).as_posix()):
        rel, raw = path.relative_to(inp).as_posix(), path.read_bytes()
        if PurePosixPath(rel).suffix.lower() not in SUPPORTED_EXT or not raw.strip():
            continue
        text = decode(raw)
        if text is None:
            continue
        try:
            out.append((rel, parse(rel, text).records))
        except (Unsupported, RecursionError, ValueError, UnicodeError):
            continue
    return out


# tables whose expected cell is a whole address line (label words included) are not scored as one span
_SKIP_TABLE_HEADERS = ("पता_ग्राम_पिन",)


def selftest_files() -> list[tuple[str, list]]:
    """Each self-test line is its own one-record file (as selftest.py runs it); each table is one file."""
    out = []
    for n, (line, _, _) in enumerate(selftest.CASES):
        name = f"line{n:02d}.txt"
        out.append((name, [{"record_id": f"{name}#doc", "file": name, "loc": "doc", "fmt": "text",
                            "fields": [{"path": "text", "kind": "text", "context": None, "value": line}]}]))
    for t, (headers, rows, _) in enumerate(selftest.TABLES):
        name = f"table{t}.csv"
        out.append((name, [{"record_id": f"{name}#row:{n}", "file": name, "loc": f"row:{n}", "fmt": "csv",
                            "fields": [{"path": f"col:{i}", "kind": "value", "context": h, "value": v}
                                       for i, (h, v) in enumerate(zip(headers, row))]}
                           for n, row in enumerate(rows, 1)]))
    return out


DEVA_RX = re.compile(r"[ऀ-ॿ]")
_HINDI_WORDS = re.compile(r"\b(?:ka|ki|ke|ko|ne|hai|hain|karein|raha|rahi|gaya|diya|aur|se|aayi|dekha|kiya|lena)\b")


def script_of(item: str, line: str) -> str:
    """Script of one self-test string: by its own letters, else Hinglish if the line is romanised Hindi."""
    if DEVA_RX.search(item):
        return "deva"
    return "hinglish" if _HINDI_WORDS.search(line) else "latin"


def selftest_truth() -> dict:
    """The self-test expectations in the same shape as dev/truth/truth.json."""
    files = {}
    for n, (line, must_find, must_keep) in enumerate(selftest.CASES):
        files[f"line{n:02d}.txt"] = {"clean": False, "units": {"doc": {
            "entities": [{"type": "SELFTEST", "surface": s, "script": script_of(s, line)} for s in must_find],
            "preserve": [{"kind": "keep", "text": s, "script": script_of(s, line)} for s in must_keep]}}}
    for t, (headers, rows, expected) in enumerate(selftest.TABLES):
        units = {}
        for n, row in enumerate(rows, 1):
            entities, keep = [], []
            for header, kind in expected.items():
                if header in _SKIP_TABLE_HEADERS:
                    continue
                value, path = row[headers.index(header)], f"col:{headers.index(header)}"
                item = {"script": script_of(value, value), "path": path}
                if kind is None:
                    keep.append({"kind": "keep", "text": value, **item})
                else:
                    entities.append({"type": "SELFTEST", "surface": value, **item})
            units[f"row:{n}"] = {"entities": entities, "preserve": keep}
        files[f"table{t}.csv"] = {"clean": False, "units": units}
    return {"files": files}
