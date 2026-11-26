"""Bytes -> text. Handles UTF-8, UTF-8 with BOM, UTF-16 (with or without BOM), cp1252 and
mostly-valid UTF-8 with a few corrupt bytes. Returns None when the bytes are not text."""
from __future__ import annotations

import re

_UTF8_MULTIBYTE = re.compile(rb"[\xc2-\xf4][\x80-\xbf]+")


def decode(raw: bytes) -> str | None:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            return None
    head = raw[:4096]
    if head and head.count(b"\x00") > len(head) // 4:  # BOM-less UTF-16
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue
            if "\x00" not in text:
                return text
        return None
    if b"\x00" in head:
        return None  # binary
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Mostly UTF-8 with corrupt bytes (it already holds valid multi-byte sequences): replace the bad bytes.
    if _UTF8_MULTIBYTE.search(raw):
        text = raw.decode("utf-8", errors="replace")
        if text.count("�") <= max(4, len(text) // 50):
            return text
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        return text if text.count("�") <= max(4, len(text) // 50) else None
