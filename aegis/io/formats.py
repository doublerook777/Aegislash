"""Parse one input file into Records (contracts/types.md) and write it back with new values.

Every Field gets a path that is unique inside its record; `write()` takes a mapping
(record_id, path) -> new text and rebuilds the file in its original format and structure.
"""
from __future__ import annotations

import base64
import binascii
import csv
import re
import io
import json
from dataclasses import dataclass, field as dc_field
from pathlib import PurePosixPath
from typing import Any

from aegis.types import Field, Record

SUPPORTED_EXT = (".csv", ".tsv", ".json", ".txt")
MAX_JSON_DEPTH = 1000      # deeper JSON is quarantined ("json_too_deep"); the practice sets expect 950 levels to be read
COMPACT_ABOVE_DEPTH = 64   # deeper JSON is written without indentation: indent=2 would multiply its size by hundreds


class Unsupported(Exception):
    """Raised with a reason code (never file content) when a file must be quarantined."""


def esc(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


@dataclass
class ParsedFile:
    rel: str
    fmt: str                       # csv | tsv | json | fhir | text
    records: list[Record]
    file_record_id: str            # the @file record
    text: str | None = None
    delimiter: str = ","
    header: list[str] = dc_field(default_factory=list)
    rows: list[list[str]] = dc_field(default_factory=list)
    data: Any = None
    leaf_refs: dict = dc_field(default_factory=dict)   # pointer -> (container, key, original value)
    key_refs: dict = dc_field(default_factory=dict)    # key path -> (object, key)
    doc_record_id: str | None = None                   # set when the file is a single document
    b64_ptrs: dict = dc_field(default_factory=dict)    # leaf pointer -> _B64Form (re-encoded the same way on write)
    jsonl: bool = False                                # one JSON object per line (written back the same way)
    runs: dict = dc_field(default_factory=dict)        # (record_id, path) -> _Parent: base64 runs inside a longer value


_B64_RX = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_B64_LINE = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_DATA_URI = re.compile(r"data:[^,;\s]*(?:;[^,;\s]*)*;base64,", re.I)
_B64_NAME = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")


@dataclass(frozen=True)
class _B64Form:
    """How a base64 value was written, so the sanitized text is written back the same way."""
    lead: str = ""          # whitespace before the value
    prefix: str = ""        # "data:text/plain;base64,"
    width: int = 0          # line length when the value was wrapped (0 = one line)
    newline: str = "\n"
    padded: bool = True
    tail: str = ""          # whitespace (a final newline) after the value


def _readable(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(c.isprintable() or c in "\n\r\t" for c in text)
    return text if text and printable >= 0.95 * len(text) else None


def _texty(text: str) -> bool:
    """Text a person could have written: letters, digits, spaces and usual punctuation, not noise that happens to be
    valid UTF-8."""
    if len(text) < 8 or "�" in text or sum(c.isalpha() for c in text) < 4:
        return False
    return sum(c.isalnum() or c in " \n\r\t.,;:=-_/@()'\"[]{}&|+#%?!*" for c in text) >= 0.85 * len(text)


def _b64_decode(v: str, loose: bool = False) -> tuple[str, _B64Form] | None:
    """Readable text and layout when the whole string is base64 of UTF-8: one line, wrapped over several lines
    (MIME style) and/or behind a "data:...;base64," prefix. None for anything else. `loose` (a run found inside a
    longer value): 16 characters are enough, the padding may be missing, and the text must look like writing."""
    stripped = v.strip()
    lead, tail = v[:len(v) - len(v.lstrip())], v[len(v.rstrip()):]
    m = _DATA_URI.match(stripped)
    prefix = m.group(0) if m else ""
    body = stripped[len(prefix):]
    parts = re.split(r"\r\n|\n|\r", body)
    newline = "\r\n" if "\r\n" in body else ("\r" if "\r" in body else "\n")
    lines = [p.strip() for p in parts]
    if not all(_B64_LINE.fullmatch(p) for p in lines):
        return None
    flat = "".join(lines)
    wrapped = len(lines) > 1
    if wrapped:
        width = len(lines[0])
        # a wrapped value has equal lines and a shorter last one; "=" may only close the last line
        if width < 16 or any(len(p) != width for p in lines[:-1]) or len(lines[-1]) > width or any("=" in p for p in lines[:-1]):
            return None
    else:
        width = 0
    padded = len(flat) % 4 == 0
    if not prefix and not loose and (len(flat) < 24 or not padded):
        return None                 # without a prefix, only a properly padded, long value counts
    if loose and not prefix and (len(flat.rstrip("=")) < 16 or not re.search(r"[A-Za-z]", flat)):
        return None
    if len(flat) % 4 == 1 or (prefix and len(flat) < 8):
        return None
    try:
        text = _readable(base64.b64decode(flat + "=" * (-len(flat) % 4), validate=True))
    except (binascii.Error, ValueError):
        return None
    if text is None or (loose and not _texty(text)):
        return None
    return text, _B64Form(lead, prefix, width, newline, padded, tail)


def _b64_encode(text: str, form: _B64Form) -> str:
    out = base64.b64encode(text.encode("utf-8")).decode("ascii")
    if not form.padded:
        out = out.rstrip("=")
    if form.width:
        out = form.newline.join(out[i:i + form.width] for i in range(0, len(out), form.width))
    return form.lead + form.prefix + out + form.tail


_RUN_RX = re.compile(
    r"data:[^,;\s]*(?:;[^,;\s]*)*;base64,[A-Za-z0-9+/]+={0,2}"
    r"|(?<![A-Za-z0-9+/_-])(?:[A-Za-z0-9+/]{16,}\r?\n)+[A-Za-z0-9+/]+={0,2}(?![A-Za-z0-9+/_-])"
    r"|(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/_-])", re.I)


_QUICK = re.compile(r"[A-Za-z0-9+/]{16}|;base64,")


def find_runs(text: str) -> list[tuple[int, int, str, _B64Form]]:
    """Base64 runs of readable UTF-8 text inside a longer value (a CSV cell, a line of a note, a data URI in a
    sentence): (start, end, decoded text, layout). Ordinary tokens, hashes, IDs and drug names decode to noise and
    are not runs."""
    out: list[tuple[int, int, str, _B64Form]] = []
    if len(text) < 16 or not _QUICK.search(text):
        return out
    for m in _RUN_RX.finditer(text):
        hit = _b64_decode(m.group(0), loose=True)
        if hit is not None:
            out.append((m.start(), m.end(), hit[0], hit[1]))
        elif "/" in m.group(0) and not m.group(0).lower().startswith("data:"):   # a URL path or a/b/c word: each part
            pos = m.start()
            for part in m.group(0).split("/"):
                sub = _b64_decode(part, loose=True) if len(part) >= 16 else None
                if sub is not None:
                    out.append((pos, pos + len(part), sub[0], sub[1]))
                pos += len(part) + 1
    return out


def _b64_filename(name: str) -> str | None:
    """The text inside a file name whose stem is base64 (padding left off, URL-safe letters allowed), with the
    extension put back; None when the stem is not base64 of readable text."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    if not _B64_NAME.fullmatch(stem) or ("+" in stem or "/" in stem) and ("-" in stem or "_" in stem):
        return None
    flat = stem.rstrip("=")
    if len(flat) % 4 == 1:
        return None
    try:
        text = _readable(base64.b64decode(flat.replace("-", "+").replace("_", "/") + "=" * (-len(flat) % 4), validate=True))
    except (binascii.Error, ValueError):
        return None
    if text is None or "\n" in text or "\r" in text:
        return None
    return text + (dot + ext if ext else "")


@dataclass
class _Parent:
    """A field that holds base64 runs. Detect sees `marked` (each run replaced by one private-use character) and the
    text of every run as a field of its own (path "<path>#b64:<n>"); `write` puts the runs back, re-encoded the same
    way when their text changed."""
    original: str
    marked: str
    runs: list[tuple[str, str, _B64Form, str]]      # (mark, original run, layout, decoded text), in order
    kids: list[str]


_MARK0 = 0xE000


def _expand_runs(pf: ParsedFile) -> None:
    for rec in pf.records:
        out: list[Field] = []
        for fld in rec["fields"]:
            out.append(fld)
            v = fld["value"]
            if fld["kind"] not in ("value", "text") or fld["path"] in pf.b64_ptrs or len(v) < 16:
                continue
            runs = find_runs(v)
            if not runs or any(_MARK0 <= ord(c) < _MARK0 + 256 for c in v):
                continue
            pieces: list[str] = []
            info: list[tuple[str, str, _B64Form, str]] = []
            kids: list[Field] = []
            pos = 0
            for a, b, dec, form in runs[:255]:
                if a < pos:
                    continue
                mark = chr(_MARK0 + len(info))
                pieces += [v[pos:a], mark]
                pos = b
                info.append((mark, v[a:b], form, dec))
                kids.append({"path": f"{fld['path']}#b64:{len(kids)}", "kind": fld["kind"],
                             "context": fld["context"], "value": dec})
            pieces.append(v[pos:])
            marked = "".join(pieces)
            pf.runs[(rec["record_id"], fld["path"])] = _Parent(v, marked, info, [k["path"] for k in kids])
            fld["value"] = marked
            out.extend(kids)
        rec["fields"] = out


def _restore_runs(pf: ParsedFile, new: dict[tuple[str, str], str]) -> dict[tuple[str, str], str]:
    """`new` with every run put back in its field: the sanitized text re-encoded the way it was written when it
    changed, the original run otherwise. A run whose mark was replaced or removed is gone."""
    if not pf.runs:
        return new
    merged = dict(new)
    for (rid, path), par in pf.runs.items():
        value = merged.get((rid, path), par.marked)
        for (mark, orig, form, dec), kid in zip(par.runs, par.kids):
            fresh = merged.pop((rid, kid), None)
            value = value.replace(mark, orig if fresh is None or fresh == dec else _b64_encode(fresh, form))
        if value == par.original:
            merged.pop((rid, path), None)
        else:
            merged[(rid, path)] = value
    return merged


def _rid(rel: str, loc: str) -> str:
    return f"{rel}#{loc}"


def _file_record(rel: str, fmt: str) -> Record:
    name = PurePosixPath(rel).name
    # a base64 name is shown to detect as the text it holds; the renamed output file is plain text (see pipeline)
    return {"record_id": _rid(rel, "@file"), "file": rel, "loc": "@file", "fmt": fmt,
            "fields": [{"path": "filename", "kind": "filename", "context": None, "value": _b64_filename(name) or name}]}


def parse(rel: str, text: str) -> ParsedFile:
    pf = _parse(rel, text)
    _expand_runs(pf)
    return pf


def _parse(rel: str, text: str) -> ParsedFile:
    ext = PurePosixPath(rel).suffix.lower()
    stripped = text.lstrip()
    if ext == ".json" or (ext in (".csv", ".tsv", ".txt") and stripped[:1] in "{[" and _looks_json(stripped)):
        return _parse_json(rel, text)
    if ext in (".csv", ".tsv", ".txt") and stripped[:1] == "{":
        lines = _json_lines(text)
        if lines is not None:
            return _parse_json(rel, text, lines=lines)
        if ext != ".txt" and _first_line_is_object(text):
            # a table that starts like JSON Lines but is not: reading it as CSV would keep every value
            raise Unsupported("malformed_json_lines")
    if ext in (".csv", ".tsv"):
        return _parse_csv(rel, text, "\t" if ext == ".tsv" else _sniff_delimiter(text))
    if ext == ".txt":
        return _parse_text(rel, text)
    raise Unsupported("unsupported_format")


def _looks_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except (ValueError, RecursionError):
        return False


def _first_line_is_object(text: str) -> bool:
    first = next((ln for ln in text.split("\n") if ln.strip()), "")
    try:
        return isinstance(json.loads(first), dict)
    except (ValueError, RecursionError):
        return False


def _json_lines(text: str) -> list[dict] | None:
    """JSON Lines: two or more non-blank lines, each one a complete JSON object. None when it is not that.
    (Split on "\n" only: U+2028 and friends may sit inside a JSON string.)"""
    out = []
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
        except (ValueError, RecursionError):
            return None
        if not isinstance(obj, dict):
            return None
        out.append(obj)
    return out if len(out) >= 2 else None


def _sniff_delimiter(text: str) -> str:
    first = text.split("\n", 1)[0]
    if "," in first:
        return ","
    counts = [(first.count(d), d) for d in ("\t", ";", "|")]
    best = max(counts)
    return best[1] if best[0] > 0 else ","


# ---------------------------------------------------------------------------- text
def _parse_text(rel: str, text: str) -> ParsedFile:
    frec = _file_record(rel, "text")
    doc: Record = {"record_id": _rid(rel, "doc"), "file": rel, "loc": "doc", "fmt": "text",
                   "fields": [{"path": "text", "kind": "text", "context": None, "value": text}]}
    return ParsedFile(rel, "text", [frec, doc], frec["record_id"], text=text, doc_record_id=doc["record_id"])


# ---------------------------------------------------------------------------- csv / tsv
def _parse_csv(rel: str, text: str, delimiter: str) -> ParsedFile:
    fmt = "tsv" if delimiter == "\t" else "csv"
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows:
        raise Unsupported("empty_file")
    header, body = rows[0], rows[1:]
    frec = _file_record(rel, fmt)
    for i, h in enumerate(header):
        frec["fields"].append({"path": f"header:{i}", "kind": "header", "context": None, "value": h})
    records = [frec]
    for n, row in enumerate(body):
        fields: list[Field] = [{"path": f"col:{i}", "kind": "value",
                                "context": header[i] if i < len(header) else None, "value": v}
                               for i, v in enumerate(row)]
        records.append({"record_id": _rid(rel, f"row:{n}"), "file": rel, "loc": f"row:{n}", "fmt": fmt, "fields": fields})
    return ParsedFile(rel, fmt, records, frec["record_id"], delimiter=delimiter, header=header, rows=body)


# ---------------------------------------------------------------------------- json / fhir
_PERSON_KEY = re.compile(r"patient|uhid|mrn|(^|_)name|naam|mobile|phone|aadha|abha|guardian|dob|"
                         r"birth|reg_?no|ipd|beneficiar|member|subject|person|मरीज|नाम")


def _person_key(k: str) -> bool:
    return bool(_PERSON_KEY.search(re.sub(r"[^\w]+", "_", k.casefold())))


# The last word of a key that describes the export: "patient_export_source", "patientTotal", "patient_batch"
_META_WORDS = frozenset("export source meta metadata count total version schema format batch pages size".split())


def _describes_export(k: str, v: Any) -> bool:
    """True only when both the key and the value are about the export: the key ENDS in an export word
    ("batch_patient_name" ends in "name": a patient) and the value is a count or a short code such as
    "HIS-Lucknow-Ward-3". Words that could be a name, and long numbers that could be an ID, are not."""
    words = re.sub(r"[^\w]+", "_", re.sub(r"(?<=[a-z])(?=[A-Z])", "_", k)).casefold().strip("_").split("_")
    if words[-1] not in _META_WORDS:
        return False
    if v is None or isinstance(v, bool):
        return True
    if isinstance(v, int):
        return 0 <= v < 100_000
    if not isinstance(v, str):
        return False
    return (any(c.isdigit() for c in v) and not any(c.isspace() for c in v)
            and not re.search(r"\d{5}", re.sub(r"[-./]", "", v)))


def _person_records(v: Any) -> bool:
    """An array of objects whose elements carry person fields (a list of patient records)."""
    return (isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)
            and any(_person_key(k) for x in v[:20] for k in x))


def _record_pointers(data: Any) -> list[str]:
    """Records are elements of top-level arrays of person records (/visits/3, /0). A file whose top
    level itself describes one subject (a `patient` object next to `panels`) is one doc."""
    if isinstance(data, list):
        return [f"/{i}" for i in range(len(data))] if _person_records(data) else []
    if not isinstance(data, dict) or data.get("resourceType") == "Bundle":
        return []
    if any(_person_key(k) and not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v))
           and not _describes_export(k, v) for k, v in data.items()):
        return []
    out = []
    for k, v in data.items():
        if _person_records(v):
            out.extend(f"/{esc(k)}/{i}" for i in range(len(v)))
    return out


def _json_depth(data: Any, limit: int = MAX_JSON_DEPTH) -> int:
    """Nesting depth (a scalar is 1), counted without recursion; stops early once it passes `limit`."""
    deepest, stack = 1, [(data, 1)]
    while stack:
        node, d = stack.pop()
        if d > deepest:
            deepest = d
            if deepest > limit:
                return deepest
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        stack.extend((c, d + 1) for c in children if isinstance(c, (dict, list)))
    return deepest


def _leaf_text(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _parse_json(rel: str, text: str, lines: list[dict] | None = None) -> ParsedFile:
    """`lines` is the list of objects of a JSON Lines file: each line is one record, `row:N` like a CSV row."""
    if lines is not None:
        data = lines
    else:
        try:
            data = json.loads(text)
        except RecursionError:
            raise Unsupported("json_too_deep") from None
        except ValueError:
            raise Unsupported("malformed_json") from None
    if _json_depth(data) > MAX_JSON_DEPTH:
        raise Unsupported("json_too_deep")
    fmt = "fhir" if isinstance(data, dict) and data.get("resourceType") == "Bundle" else "json"
    frec = _file_record(rel, fmt)
    pf = ParsedFile(rel, fmt, [frec], frec["record_id"], data=data, jsonl=lines is not None)
    rec_ptrs = [f"/{i}" for i in range(len(data))] if lines is not None else _record_pointers(data)
    if rec_ptrs:
        by_ptr = {}
        for p in rec_ptrs:
            loc = f"row:{p[1:]}" if lines is not None else p
            r: Record = {"record_id": _rid(rel, loc), "file": rel, "loc": loc, "fmt": fmt, "fields": []}
            by_ptr[p] = r
            pf.records.append(r)
        top_len = {p.rsplit("/", 1)[0] for p in rec_ptrs}

        def owner(ptr: str) -> Record:
            parts = ptr.split("/")
            # record pointers have the form /<key>/<i> or /<i>
            for depth in (3, 2):
                cand = "/".join(parts[:depth])
                if cand in by_ptr and (cand.rsplit("/", 1)[0] in top_len):
                    return by_ptr[cand]
            return frec
    else:
        doc: Record = {"record_id": _rid(rel, "doc"), "file": rel, "loc": "doc", "fmt": fmt, "fields": []}
        pf.records.append(doc)
        pf.doc_record_id = doc["record_id"]

        def owner(ptr: str) -> Record:
            return doc

    # iterative walk (deep JSON must not blow the stack)
    stack: list[tuple[Any, str, str | None]] = [(data, "", None)]
    while stack:
        node, ptr, ctx = stack.pop()
        if isinstance(node, dict):
            items = list(node.items())
            for k, v in items:
                kp = f"key:{ptr}/{esc(k)}"
                pf.key_refs[kp] = (node, k)
                owner(ptr + "/" + esc(k))["fields"].append({"path": kp, "kind": "key", "context": None, "value": k})
            for k, v in reversed(items):
                child = f"{ptr}/{esc(k)}"
                if isinstance(v, (dict, list)):
                    stack.append((v, child, k))
                else:
                    _add_leaf(pf, owner, node, k, v, child, k)
        elif isinstance(node, list):
            for i in range(len(node) - 1, -1, -1):
                v = node[i]
                child = f"{ptr}/{i}"
                if isinstance(v, (dict, list)):
                    stack.append((v, child, ctx))
                else:
                    _add_leaf(pf, owner, node, i, v, child, ctx)
        else:  # top-level scalar
            _add_leaf(pf, owner, None, None, node, "", None)
    # the walk visits leaves in reverse order inside each container; restore document order
    order = {p: i for i, p in enumerate(_document_order(data))}
    for r in pf.records:
        r["fields"].sort(key=lambda f: (order.get(_field_ptr(f["path"]), -1), f["kind"] != "key"))
    return pf


def _add_leaf(pf, owner, container, key, v, ptr, ctx):
    if v is None or isinstance(v, bool):
        return
    pf.leaf_refs[ptr] = (container, key, v)
    text = _leaf_text(v)
    if isinstance(v, str):
        hit = _b64_decode(v)
        if hit is not None:
            text = hit[0]
            pf.b64_ptrs[ptr] = hit[1]
    owner(ptr)["fields"].append({"path": ptr, "kind": "value", "context": ctx, "value": text})


def _field_ptr(path: str) -> str:
    return path[4:] if path.startswith("key:") else path


def _document_order(data: Any) -> list[str]:
    out, stack = [], [(data, "")]
    while stack:
        node, ptr = stack.pop()
        out.append(ptr)
        if isinstance(node, dict):
            for k, v in reversed(list(node.items())):
                stack.append((v, f"{ptr}/{esc(k)}"))
        elif isinstance(node, list):
            for i in range(len(node) - 1, -1, -1):
                stack.append((node[i], f"{ptr}/{i}"))
    return out


# ---------------------------------------------------------------------------- write
def write(pf: ParsedFile, new: dict[tuple[str, str], str]) -> str:
    """Rebuild the file. `new` maps (record_id, path) -> replacement text for changed fields only."""
    new = _restore_runs(pf, new)
    if pf.fmt == "text":
        return new.get((pf.doc_record_id, "text"), pf.text)
    if pf.fmt in ("csv", "tsv"):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=pf.delimiter, lineterminator="\n")
        w.writerow([new.get((pf.file_record_id, f"header:{i}"), h) for i, h in enumerate(pf.header)])
        for n, row in enumerate(pf.rows):
            rid = f"{pf.rel}#row:{n}"
            w.writerow([new.get((rid, f"col:{i}"), v) for i, v in enumerate(row)])
        return buf.getvalue()
    # json / fhir: mutate in place (we own the parsed copy), leaves first, then keys
    owner_of = {(r["record_id"], f["path"]) for r in pf.records for f in r["fields"]}
    leaf_new, key_new = {}, {}
    for (rid, path), text in new.items():
        if (rid, path) not in owner_of:
            continue
        if path.startswith("key:"):
            key_new[path] = text
        elif path in pf.leaf_refs:
            leaf_new[path] = text
    for ptr in sorted(leaf_new):
        container, key, orig = pf.leaf_refs[ptr]
        if ptr in pf.b64_ptrs:
            value = _b64_encode(leaf_new[ptr], pf.b64_ptrs[ptr])
        else:
            value = _restore_type(orig, leaf_new[ptr])
        if container is None:
            pf.data = value
        else:
            container[key] = value
    renames: dict[int, tuple[dict, dict]] = {}
    for kp in sorted(key_new):
        obj, key = pf.key_refs[kp]
        renames.setdefault(id(obj), (obj, {}))[1][key] = key_new[kp]
    for _, (obj, mapping) in sorted(renames.items(), key=lambda x: str(list(x[1][1]))):
        items, used = [], set()
        for k, v in obj.items():
            nk = mapping.get(k, k)
            base, n = nk, 2
            while nk in used:
                nk, n = f"{base}#{n}", n + 1
            used.add(nk)
            items.append((nk, v))
        obj.clear()
        obj.update(items)
    if pf.jsonl:
        return "".join(json.dumps(obj, ensure_ascii=False) + "\n" for obj in pf.data)
    deep = _json_depth(pf.data, COMPACT_ABOVE_DEPTH) > COMPACT_ABOVE_DEPTH
    return json.dumps(pf.data, ensure_ascii=False, indent=None if deep else 2) + "\n"


def _restore_type(orig: Any, text: str) -> Any:
    if isinstance(orig, str):
        return text
    try:
        v = json.loads(text)
    except ValueError:
        return text
    return v if type(v) is type(orig) else text
