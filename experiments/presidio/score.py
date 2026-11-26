"""Score every setup with ONE rule and print the comparison tables (also saved to out/results.md).

How a match is counted (the same for all setups):
  * A setup's findings are only character ranges. Type labels are ignored: any flagged range counts
    as "would be removed". (Ours: CONDITION/DISTRICT/GENDER are never removed, so they don't count.)
  * A truth item is looked up by its text in its own record (ignoring case, extra spaces and
    Unicode form). Occurrences inside a must-keep phrase (Ramesh in "Dr. Ramesh") are not counted.
  * FOUND   = every letter, vowel sign and digit of every occurrence is inside flagged ranges
              (several ranges may add up). For names in dev/input only the identifying words listed
              in truth.json ("tokens") are required, as in docs/kit/SCORING.md: leaving "sahab",
              "ji" or "Devi" behind is not a miss. Self-test strings are required in full.
    PARTIAL = some, but not all.   MISSED = none.   Only FOUND counts in the percentages.
  * A must-keep (medical / staff) phrase is DAMAGED if any of its letters or digits is flagged,
    not counting characters that are themselves personal data.
  * Items whose text is in no parsed field (e.g. inside quarantined files) are left out for everyone.
This is stricter than check_dev.py (which only asks whether the exact string survives) and is not
the official F2 score.
"""
from __future__ import annotations

import json
import unicodedata
from collections import Counter, defaultdict

import common

SETUPS = ("ours", "lg", "lg_ctx", "sm", "xx")
LABEL = {"ours": "Ours", "lg": "Presidio+lg", "lg_ctx": "Presidio+lg+headers", "sm": "Presidio+sm",
         "xx": "Presidio+xx"}
# Presidio labels that actually mean the truth type (it has no label for the types left empty)
RIGHT_LABEL = {"PATIENT_NAME": ("PERSON",), "RELATIVE_NAME": ("PERSON",), "PHONE": ("PHONE_NUMBER",),
               "EMAIL": ("EMAIL_ADDRESS",), "AADHAAR": ("IN_AADHAAR",), "PAN": ("IN_PAN",), "DOB": ("DATE_TIME",),
               "VILLAGE": ("LOCATION",), "LOCALITY": ("LOCATION",), "HOUSE": ("LOCATION",),
               "LANDMARK": ("LOCATION",), "AADHAAR_MASKED": (), "ABHA_NUMBER": (), "MRN": (), "INSURANCE_ID": (),
               "PIN": ()}
DATE_LIKE = ("DATE", "AGE", "DOB", "DATE_TIME")
GROUPS = {"medicine, dose, frequency": ("medication", "dose", "frequency"),
          "vitals and lab values": ("vital", "lab", "lab_test", "range"),
          "diagnosis, complaint, history": ("diagnosis", "diagnosis_code", "complaint", "history", "eponym", "procedure"),
          "doctor names": ("doctor",),
          "ward, department, hospital, district, other": ("ward", "department", "hospital", "district", "context",
                                                          "amount", "package")}


def alnum(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LNM"


def normalised(text: str) -> tuple[str, list[int]]:
    """NFKC + casefold + single spaces, with the original offset of every output character."""
    chars, where = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch).casefold():
            if c.isspace():
                if chars and chars[-1] == " ":
                    continue
                c = " "
            chars.append(c)
            where.append(i)
    return "".join(chars), where


def occurrences(needle: str, fields: list, cache: dict, bounded: bool) -> list[tuple[str, int, int]]:
    """[(path, start, end)] in original offsets. bounded: no letter or digit may touch either side."""
    n = normalised(needle)[0].strip()
    out, loose = [], []
    if not n:
        return out
    for f in fields:
        key = (id(f), f["path"])
        if key not in cache:
            cache[key] = normalised(f["value"])
        hay, where = cache[key]
        i = hay.find(n)
        while i >= 0:
            j = i + len(n)
            hit = (f["path"], where[i], where[j - 1] + 1)
            loose.append(hit)
            if not ((i and alnum(hay[i - 1]) and alnum(n[0])) or (j < len(hay) and alnum(hay[j]) and alnum(n[-1]))):
                out.append(hit)
            i = hay.find(n, i + 1)
    return out if bounded or out else loose


def unit_fields(records: list, loc: str) -> list:
    if loc in ("@file", "@filename", "@header"):
        fields = [f for r in records if r["loc"] == "@file" for f in r["fields"]]
        want = {"@filename": "filename", "@header": "header"}.get(loc)
        return [f for f in fields if not want or f["kind"] == want]
    same = [r for r in records if r["loc"] == loc]
    return [f for r in (same or records) for f in r["fields"]]


def build_items(truth: dict, files: list) -> tuple[list, list, Counter]:
    """Locate every truth entity and must-keep probe once; all setups are scored against these."""
    entities, probes, skipped = [], [], Counter()
    by_rel = dict(files)
    for rel, meta in truth["files"].items():
        for loc, unit in meta["units"].items():
            if rel not in by_rel:
                skipped["entity (file unreadable)"] += len(unit.get("entities") or [])
                skipped["probe (file unreadable)"] += len(unit.get("preserve") or [])
                continue
            records, cache = by_rel[rel], {}
            fields = unit_fields(records, loc)
            # which record each searched field belongs to (paths repeat between records)
            owner = {id(f): r["record_id"] for r in records for f in r["fields"]}
            def locate(text, path, bounded):
                chosen = [f for f in fields if f["path"] == path] if path else []
                hits = []
                for f in chosen or fields:
                    hits += [((owner[id(f)], p), s, e, f) for p, s, e in occurrences(text, [f], cache, True)]
                if not hits and not bounded:
                    for f in chosen or fields:
                        hits += [((owner[id(f)], p), s, e, f) for p, s, e in occurrences(text, [f], cache, False)]
                return hits
            keep_hits = [(p, locate(p["text"], p.get("path"), True)) for p in unit.get("preserve") or []]
            pii_chars: dict = defaultdict(set)
            for e in unit.get("entities") or []:
                hits = locate(e["surface"], e.get("path"), False)
                if not hits:  # e.g. JSON keys: truth files them under a record, the parser under @file
                    hits = [((r["record_id"], p), a, b, f) for r in records for f in r["fields"]
                            for p, a, b in occurrences(e["surface"], [f], cache, False)]
                protected = [(k, s, t) for _, hs in keep_hits for k, s, t, _ in hs]
                hits = [h for h in hits if not any(h[0] == k and s <= h[1] and h[2] <= t and t - s > h[2] - h[1]
                                                   for k, s, t in protected)]
                if not hits:
                    skipped["entity (text not in a field)"] += 1
                    continue
                for k, s, t, _ in hits:
                    pii_chars[k].update(range(s, t))
                need = []
                tokens = [normalised(t)[0] for t in e.get("tokens") or []]
                for k, s, t, f in hits:
                    whole = [(k, i) for i in range(s, t) if alnum(f["value"][i])]
                    hay, where = normalised(f["value"][s:t])
                    part = set()
                    for token in tokens:
                        i = hay.find(token)
                        if i < 0:  # a token we cannot place: require the whole occurrence
                            part, skipped["name token not placed (whole name required)"] = set(), \
                                skipped["name token not placed (whole name required)"] + 1
                            break
                        part.update(range(s + where[i], s + where[i + len(token) - 1] + 1))
                    need += [c for c in whole if c[1] in part] if part else whole
                entities.append({"type": e["type"], "script": e["script"], "surface": e["surface"], "file": rel,
                                 "loc": loc, "hits": hits, "need": need})
            for p, hits in keep_hits:
                chars = [(k, i) for k, s, t, f in hits for i in range(s, t)
                         if i not in pii_chars[k] and alnum(f["value"][i])]
                if not chars:
                    skipped["probe (not located or all personal)"] += 1
                    continue
                probes.append({"kind": p["kind"], "text": p["text"], "file": rel, "loc": loc, "chars": chars,
                               "script": p.get("script") or ("deva" if common.DEVA_RX.search(p["text"]) else "latin")})
    return entities, probes, skipped


def coverage(spans: dict, keep=lambda s: True) -> dict:
    """(record_id, path) -> set of flagged character offsets."""
    out: dict = defaultdict(set)
    for rid, found in spans.items():
        for s in found:
            if keep(s):
                out[(rid, s[0])].update(range(s[1], s[2]))
    return out


def status(entity: dict, cov: dict) -> str:
    got = sum(i in cov.get(k, ()) for k, i in entity["need"])
    return "found" if got == len(entity["need"]) else "partial" if got else "missed"


def damaged(probe: dict, cov: dict) -> bool:
    return any(i in cov.get(k, ()) for k, i in probe["chars"])


def pct(a: int, b: int) -> str:
    return "-" if not b else f"{100 * a / b:.1f}% ({a}/{b})"


def table(title: str, head: list, rows: list) -> str:
    lines = [f"\n### {title}\n", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def recall_rows(entities, covs, key):
    names = sorted({e[key] for e in entities})
    rows = []
    for name in [*names, None]:
        group = [e for e in entities if name is None or e[key] == name]
        rows.append([name or "ALL", *(pct(sum(status(e, c) == "found" for e in group), len(group))
                                      for c in covs.values())])
    return rows


def keep_rows(probes, covs):
    rows = []
    groups = {**GROUPS, "ALL": None} if any(p["kind"] != "keep" for p in probes) else {"ALL": None}
    for name, kinds in groups.items():
        group = [p for p in probes if kinds is None or p["kind"] in kinds]
        rows.append([name, *(pct(sum(damaged(p, c) for p in group), len(group)) for c in covs.values())])
    return rows


def main() -> int:
    report, details = [], {}
    for dataset in ("dev", "selftest"):
        files = common.dev_files() if dataset == "dev" else common.selftest_files()
        truth = (json.loads((common.ROOT / "dev/truth/truth.json").read_text(encoding="utf-8"))
                 if dataset == "dev" else common.selftest_truth())
        entities, probes, skipped = build_items(truth, files)
        runs = {s: json.loads((common.OUT / f"{s}.{dataset}.json").read_text(encoding="utf-8")) for s in SETUPS}
        covs = {s: coverage(runs[s]["spans"]) for s in SETUPS}
        head = [LABEL[s] for s in SETUPS]
        report.append(f"\n## {dataset}: {len(entities)} personal items, {len(probes)} must-keep phrases; "
                      f"left out for all: {dict(skipped)}")
        if dataset == "dev":
            report.append(table("Personal data FOUND, by type", ["type", *head], recall_rows(entities, covs, "type")))
        if dataset == "dev":
            rows = []
            for kind in sorted(RIGHT_LABEL):
                group = [e for e in entities if e["type"] == kind]
                if group:
                    cells = []
                    for s in SETUPS[1:]:
                        c = coverage(runs[s]["spans"], lambda x: x[3] in RIGHT_LABEL[kind])
                        cells.append(pct(sum(status(e, c) == "found" for e in group), len(group)))
                    rows.append([kind, " ".join(RIGHT_LABEL[kind]) or "(Presidio has none)", *cells])
            report.append(table("Presidio FOUND counting only a label that means the right thing",
                                ["type", "labels counted", *head[1:]], rows))
        report.append(table("Personal data FOUND, by script", ["script", *head], recall_rows(entities, covs, "script")))
        report.append(table("Found / partial / missed", ["", *head], [
            [st, *(sum(status(e, c) == st for e in entities) for c in covs.values())]
            for st in ("found", "partial", "missed")]))
        report.append(table("Must-keep text DAMAGED (lower is better)", ["group", *head], keep_rows(probes, covs)))
        rows = []
        for script in sorted({p["script"] for p in probes}):
            group = [p for p in probes if p["script"] == script]
            rows.append([script, *(pct(sum(damaged(p, c) for p in group), len(group)) for c in covs.values())])
        report.append(table("Must-keep text DAMAGED, by script of the phrase", ["script", *head], rows))
        # flagged ranges that touch no personal data at all (date/age ranges left out)
        pii: dict = defaultdict(set)
        for e in entities:
            for k, s, t, _ in e["hits"]:
                pii[k].update(range(s, t))
        extra = {s: Counter(x[3] for rid, fs in runs[s]["spans"].items() for x in fs
                            if x[3] not in DATE_LIKE and not pii.get((rid, x[0]), set()) & set(range(x[1], x[2])))
                 for s in SETUPS}
        report.append(table("Flagged ranges touching no listed personal data (dates and ages not counted)",
                            ["", *head], [["ranges", *(sum(extra[s].values()) for s in SETUPS)],
                                          ["top types", *(", ".join(f"{t} {n}" for t, n in extra[s].most_common(4))
                                                          for s in SETUPS)]]))
        if dataset == "dev":
            clean = {rel for rel, m in truth["files"].items() if m.get("clean")}
            report.append(table(f"Non-date ranges flagged in the {len(clean)} 'clean' files (no personal data)",
                                ["", *head], [["ranges", *(
                                    sum(x[3] not in DATE_LIKE for rid, fs in runs[s]["spans"].items()
                                        if rid.split("#")[0] in clean for x in fs) for s in SETUPS)]]))

        # ---- what the others find that we miss
        ours = covs["ours"]
        gaps = [e for e in entities if status(e, ours) != "found"]
        gap_rows = []
        for e in gaps:
            gap_rows.append({"type": e["type"], "script": e["script"], "file": e["file"], "loc": e["loc"],
                             "surface": e["surface"], "ours": status(e, ours),
                             **{s: status(e, covs[s]) for s in SETUPS[1:]},
                             "lg_by": sorted({f"{x[3]}:{x[5]}:{x[4]}" for k, a, b, _ in e["hits"]
                                              for x in runs["lg"]["spans"].get(k[0], [])
                                              if x[0] == k[1] and x[1] < b and x[2] > a}),
                             "text": [f["value"][max(0, a - 50):b + 30] for _, a, b, f in e["hits"][:2]]})
        our_damage = [p for p in probes if damaged(p, ours)]
        details[dataset] = {"our_gaps": gap_rows, "our_damaged": [
            {"kind": p["kind"], "text": p["text"], "file": p["file"], "loc": p["loc"]} for p in our_damage]}
        report.append(f"\nItems we did not fully find: {len(gaps)}. Of these, fully found by: " + ", ".join(
            f"{LABEL[s]} {sum(status(e, covs[s]) == 'found' for e in gaps)}" for s in SETUPS[1:]))

        # ---- would adding part of Presidio to ours help? (union of ranges)
        variants = {
            "ours alone": lambda s, x: False,
            "+ lg PERSON, all fields": lambda s, x: s == "lg" and x[3] == "PERSON",
            "+ lg PERSON, free text only": lambda s, x: s == "lg" and x[3] == "PERSON" and x[0] == "text",
            "+ sm PERSON, all fields": lambda s, x: s == "sm" and x[3] == "PERSON",
            "+ xx PERSON, all fields": lambda s, x: s == "xx" and x[3] == "PERSON",
            "+ lg LOCATION, all fields": lambda s, x: s == "lg" and x[3] == "LOCATION",
            "+ lg PHONE_NUMBER and EMAIL": lambda s, x: s == "lg" and x[3] in ("PHONE_NUMBER", "EMAIL_ADDRESS"),
            "+ six Indian recognizers (score>=0.4)": lambda s, x: s == "lg" and x[3].startswith("IN_") and x[4] >= 0.4,
        }
        rows = []
        for name, pick in variants.items():
            merged = defaultdict(set, {k: set(v) for k, v in ours.items()})
            for s in ("lg", "sm", "xx"):
                for k, v in coverage(runs[s]["spans"], lambda x, s=s: pick(s, x)).items():
                    merged[k] |= v
            rows.append([name, sum(status(e, merged) == "found" for e in gaps),
                         sum(damaged(p, merged) and not damaged(p, ours) for p in probes)])
        report.append(table("Adding Presidio output on top of ours", ["variant", "extra items found",
                                                                     "extra phrases damaged"], rows))

        # ---- thresholds: does Presidio's context scoring help it separate real items from noise?
        rows = []
        for threshold in (0.0, 0.3, 0.4, 0.6):
            for s in ("lg", "lg_ctx"):
                c = coverage(runs[s]["spans"], lambda x: x[4] >= threshold)
                rows.append([threshold, LABEL[s], pct(sum(status(e, c) == "found" for e in entities), len(entities)),
                             pct(sum(damaged(p, c) for p in probes), len(probes))])
        report.append(table("Score threshold, without and with header context words",
                            ["min score", "setup", "found", "damaged"], rows))

        # ---- which Presidio recognizer does the work
        found_by, noise = Counter(), Counter()
        for e in entities:
            for k, a, b, _ in e["hits"]:
                for who in {x[5] for x in runs["lg"]["spans"].get(k[0], []) if x[0] == k[1] and x[1] < b and x[2] > a}:
                    found_by[who] += 1
        for p in probes:
            for who in {x[5] for k, i in p["chars"] for x in runs["lg"]["spans"].get(k[0], [])
                        if x[0] == k[1] and x[1] <= i < x[2]}:
                noise[who] += 1
        report.append(table("Presidio+lg by recognizer", ["recognizer", "personal-item occurrences touched",
                                                          "must-keep phrases damaged"],
                            [[w, found_by[w], noise[w]] for w in sorted(set(found_by) | set(noise),
                                                                        key=lambda w: (-found_by[w], w))]))

    # ---- run time and memory: median of all repeats
    runs_by = defaultdict(list)
    for line in (common.OUT / "timings.txt").read_text().splitlines():
        parts = line.split()
        values = dict(p.split("=") for p in parts[2:])
        runs_by[(parts[0], parts[1])].append(values)
    rows = []
    for (s, d), values in runs_by.items():
        med = lambda k, u: sorted(float(v[k].rstrip(u)) for v in values)[len(values) // 2]
        rows.append([d, LABEL[s], len(values), med("load", "s"), med("analyze", "s"), med("loaded", "MB"),
                     med("peak", "MB"),
                     all(v["offline"] == "True" for v in values)])
    report.append("\n## Run time and memory (median; 2 CPUs, network off, empty HOME)")
    report.append(table("Resources", ["dataset", "setup", "runs", "load s", "analyze s", "MB after load", "peak MB", "network off"], rows))
    text = "\n".join(report)
    (common.OUT / "results.md").write_text(text + "\n", encoding="utf-8")
    (common.OUT / "details.json").write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
