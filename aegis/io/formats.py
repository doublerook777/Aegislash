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
    b64_ptrs: set = dc_field(default_factory=set)      # leaves that were base64 text (re-encoded on write)


_B64_RX = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _b64_text(v: str) -> str | None:
    """Decoded text when the whole string is base64 of readable UTF-8 (FHIR attachments), else None."""
    if len(v) < 24 or len(v) % 4 or not _B64_RX.fullmatch(v):
        return None
    try:
        text = base64.b64decode(v, validate=True).decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    printable = sum(c.isprintable() or c in "\n\r\t" for c in text)
    return text if text and printable >= 0.95 * len(text) else None


def _rid(rel: str, loc: str) -> str:
    return f"{rel}#{loc}"


def _file_record(rel: str, fmt: str) -> Record:
    return {"record_id": _rid(rel, "@file"), "file": rel, "loc": "@file", "fmt": fmt,
            "fields": [{"path": "filename", "kind": "filename", "context": None, "value": PurePosixPath(rel).name}]}


def parse(rel: str, text: str) -> ParsedFile:
    ext = PurePosixPath(rel).suffix.lower()
    stripped = text.lstrip()
    if ext == ".json" or (ext in (".csv", ".tsv", ".txt") and stripped[:1] in "{[" and _looks_json(stripped)):
        return _parse_json(rel, text)
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
           for k, v in data.items()):
        return []
    out = []
    for k, v in data.items():
        if _person_records(v):
            out.extend(f"/{esc(k)}/{i}" for i in range(len(v)))
    return out


def _leaf_text(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _parse_json(rel: str, text: str) -> ParsedFile:
    try:
        data = json.loads(text)
    except RecursionError:
        raise Unsupported("json_too_deep") from None
    except ValueError:
        raise Unsupported("malformed_json") from None
    fmt = "fhir" if isinstance(data, dict) and data.get("resourceType") == "Bundle" else "json"
    frec = _file_record(rel, fmt)
    pf = ParsedFile(rel, fmt, [frec], frec["record_id"], data=data)
    rec_ptrs = _record_pointers(data)
    if rec_ptrs:
        by_ptr = {}
        for p in rec_ptrs:
            r: Record = {"record_id": _rid(rel, p), "file": rel, "loc": p, "fmt": fmt, "fields": []}
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
        decoded = _b64_text(v)
        if decoded is not None:
            pf.b64_ptrs.add(ptr)
            text = decoded
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
            value = base64.b64encode(leaf_new[ptr].encode("utf-8")).decode("ascii")
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
    return json.dumps(pf.data, ensure_ascii=False, indent=2) + "\n"


def _restore_type(orig: Any, text: str) -> Any:
    if isinstance(orig, str):
        return text
    try:
        v = json.loads(text)
    except ValueError:
        return text
    return v if type(v) is type(orig) else text
