# detect: detection engine (owner: Member-2)

Owns finding every piece of PII (Latin, Devanagari, Hinglish) and producing `Evidence` for linking,
while never flagging medical values. Column/key classification by header *and* values (hidden data
renames columns), regex + checksum IDs, context cues (Name:, ji/sahab/didi/behenji, S/o D/o W/o,
C/O-relative vs C/O-complaint, Attendant, `Dr.` kept), gazetteers + transliteration, hidden places
(keys, headers, file names, metadata, base64, `\u` escapes), date order per file.

Contract it provides: [detect](../../contracts/detect.md). Evidence feeds [link](../../contracts/link.md);
findings feed [privacy](../../contracts/privacy.md). Shapes: [types](../../contracts/types.md).

The real code goes in this folder; switch the import in `__init__.py` from `mock` when ready.
