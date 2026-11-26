"""Patient record linkage engine (contracts/link.md)."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from aegis.link.normalize import (
    GENERIC_SURNAME_TOKENS,
    ascii_digits,
    full_names_match,
    normalize_name_mention,
    normalize_strong_id,
    normalize_tokens,
    phonetic_block_key,
    single_matches_full,
    tokens_similar,
    villages_match,
)
from aegis.link.psn import secret
from aegis.types import Evidence

# Strong IDs where a single patient never holds two distinct valid values.
_SINGLETON_ID_TYPES: tuple[str, ...] = (
    "AADHAAR",
    "ABHA_NUMBER",
    "PAN",
    "ABHA_ADDRESS",
    "EMAIL",
    "INSURANCE_ID",
)
_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MRN_PREFIX_RE = re.compile(r"^([a-z]+)(\d+)$")


@dataclass(frozen=True)
class _RelativeMention:
    relation: str | None
    tokens: tuple[str, ...]


@dataclass
class _RecordInfo:
    idx: int
    record_id: str
    hospital: str | None
    dob: str | None
    age: int | None
    gender: str | None
    village: tuple[str, ...]
    district: str | None
    pin: str | None
    singleton_ids: dict[str, tuple[str, ...]]
    phones: tuple[str, ...]
    mrns: tuple[str, ...]
    full_names: tuple[tuple[str, ...], ...]
    single_names: tuple[tuple[str, ...], ...]
    relatives: tuple[_RelativeMention, ...]


@dataclass
class _Cluster:
    root: int
    members: list[int] = field(default_factory=list)
    dobs: set[str] = field(default_factory=set)
    ages: set[int] = field(default_factory=set)
    genders: set[str] = field(default_factory=set)
    villages: set[tuple[str, ...]] = field(default_factory=set)
    districts: set[str] = field(default_factory=set)
    pins: set[str] = field(default_factory=set)
    hospitals: set[str] = field(default_factory=set)
    singleton_ids: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    phones: set[str] = field(default_factory=set)
    mrns: set[str] = field(default_factory=set)
    full_names: set[tuple[str, ...]] = field(default_factory=set)
    single_names: set[tuple[str, ...]] = field(default_factory=set)
    relatives: list[_RelativeMention] = field(default_factory=list)
    # Age per record that also carries a village (for village + age +/- 1 rule).
    village_age_pairs: list[tuple[tuple[str, ...], int]] = field(default_factory=list)

    @classmethod
    def from_record(cls, r: _RecordInfo) -> "_Cluster":
        c = cls(root=r.idx, members=[r.idx])
        if r.dob:
            c.dobs.add(r.dob)
        if r.age is not None:
            c.ages.add(r.age)
        if r.gender:
            c.genders.add(r.gender)
        if r.village:
            c.villages.add(r.village)
            if r.age is not None:
                c.village_age_pairs.append((r.village, r.age))
        if r.district:
            c.districts.add(r.district)
        if r.pin:
            c.pins.add(r.pin)
        if r.hospital:
            c.hospitals.add(r.hospital)
        for t, vals in r.singleton_ids.items():
            c.singleton_ids[t].update(vals)
        c.phones.update(r.phones)
        c.mrns.update(r.mrns)
        c.full_names.update(r.full_names)
        c.single_names.update(r.single_names)
        c.relatives.extend(r.relatives)
        return c

    def absorb(self, other: "_Cluster") -> None:
        self.members.extend(other.members)
        self.dobs.update(other.dobs)
        self.ages.update(other.ages)
        self.genders.update(other.genders)
        self.villages.update(other.villages)
        self.districts.update(other.districts)
        self.pins.update(other.pins)
        self.hospitals.update(other.hospitals)
        for t, vals in other.singleton_ids.items():
            self.singleton_ids[t].update(vals)
        self.phones.update(other.phones)
        self.mrns.update(other.mrns)
        self.full_names.update(other.full_names)
        self.single_names.update(other.single_names)
        self.relatives.extend(other.relatives)
        self.village_age_pairs.extend(other.village_age_pairs)


def _parse_gender(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip().upper()
    if v in {"M", "MALE"}:
        return "M"
    if v in {"F", "FEMALE"}:
        return "F"
    return None


def _parse_dob(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip()
    return v if _DOB_RE.match(v) else None


def _parse_pin(val: str | None) -> str | None:
    if not val:
        return None
    d = ascii_digits(val)
    return d if len(d) == 6 else None


def _parse_record(idx: int, ev: Evidence) -> _RecordInfo:
    single_ids: dict[str, set[str]] = defaultdict(set)
    phones: set[str] = set()
    mrns: set[str] = set()
    for im in ev.get("ids") or []:
        normed = normalize_strong_id(im)
        if not normed:
            continue
        id_type, id_val = normed
        if id_type == "PHONE":
            phones.add(id_val)
        elif id_type == "MRN":
            mrns.add(id_val)
        elif id_type in _SINGLETON_ID_TYPES:
            single_ids[id_type].add(id_val)

    full_names: list[tuple[str, ...]] = []
    single_names: list[tuple[str, ...]] = []
    ordered_singles: list[str] = []
    relatives: list[_RelativeMention] = []

    for nm in ev.get("names") or []:
        toks = normalize_name_mention(nm)
        if not toks:
            continue
        role = nm.get("role")
        if role == "relative":
            relatives.append(_RelativeMention(relation=nm.get("relation"), tokens=toks))
        else:
            if len(toks) >= 2:
                full_names.append(toks)
            else:
                single_names.append(toks)
                if toks[0] not in ordered_singles:
                    ordered_singles.append(toks[0])

    # Split first/last name columns (e.g. legacy CSV / JSON) produce two single-token patient mentions.
    if not full_names and len(ordered_singles) >= 2:
        full_names.append(tuple(ordered_singles))

    age_raw = ev.get("age")
    age = age_raw if isinstance(age_raw, int) and not isinstance(age_raw, bool) and 0 <= age_raw <= 125 else None

    v_raw = ev.get("village")
    village = normalize_tokens(v_raw, strip_honorifics=False) if v_raw else ()

    d_raw = ev.get("district")
    district = " ".join(normalize_tokens(d_raw, strip_honorifics=False)) if d_raw else None
    district = district or None

    h_raw = ev.get("hospital")
    hospital = h_raw.strip().casefold() if isinstance(h_raw, str) and h_raw.strip() else None

    return _RecordInfo(
        idx=idx,
        record_id=ev["record_id"],
        hospital=hospital,
        dob=_parse_dob(ev.get("dob")),
        age=age,
        gender=_parse_gender(ev.get("gender")),
        village=village,
        district=district,
        pin=_parse_pin(ev.get("pin")),
        singleton_ids={t: tuple(sorted(v)) for t, v in single_ids.items()},
        phones=tuple(sorted(phones)),
        mrns=tuple(sorted(mrns)),
        full_names=tuple(sorted(set(full_names))),
        single_names=tuple(sorted(set(single_names))),
        relatives=tuple(relatives),
    )


def _cluster_names_match(c1: _Cluster, c2: _Cluster, *, allow_single: bool = True) -> bool:
    """Return True if patient names in c1 and c2 are compatible and match."""
    if c1.full_names and c2.full_names:
        return any(full_names_match(a, b) for a in c1.full_names for b in c2.full_names)
    if not allow_single:
        return False
    if c1.full_names and c2.single_names:
        return any(single_matches_full(s[0], fn) for s in c2.single_names for fn in c1.full_names)
    if c2.full_names and c1.single_names:
        return any(single_matches_full(s[0], fn) for s in c1.single_names for fn in c2.full_names)
    if c1.single_names and c2.single_names:
        for a in c1.single_names:
            for b in c2.single_names:
                if a[0] in GENERIC_SURNAME_TOKENS or b[0] in GENERIC_SURNAME_TOKENS:
                    continue
                if tokens_similar(a[0], b[0]):
                    return True
    return False


def _relatives_compatible(r1: _RelativeMention, r2: _RelativeMention) -> bool:
    if r1.relation in {"S/o", "D/o", "W/o"} and r2.relation in {"S/o", "D/o", "W/o"}:
        if r1.relation != r2.relation:
            return False
    if len(r1.tokens) >= 2 and len(r2.tokens) >= 2:
        return full_names_match(r1.tokens, r2.tokens)
    if len(r1.tokens) >= 2 and len(r2.tokens) == 1:
        return single_matches_full(r2.tokens[0], r1.tokens)
    if len(r2.tokens) >= 2 and len(r1.tokens) == 1:
        return single_matches_full(r1.tokens[0], r2.tokens)
    return (
        r1.tokens[0] not in GENERIC_SURNAME_TOKENS
        and r2.tokens[0] not in GENERIC_SURNAME_TOKENS
        and tokens_similar(r1.tokens[0], r2.tokens[0])
    )


def _cluster_relatives_match(c1: _Cluster, c2: _Cluster) -> bool:
    return any(_relatives_compatible(r1, r2) for r1 in c1.relatives for r2 in c2.relatives)


def _cluster_village_age_match(c1: _Cluster, c2: _Cluster) -> bool:
    for v1, a1 in c1.village_age_pairs:
        for v2, a2 in c2.village_age_pairs:
            if abs(a1 - a2) <= 1 and villages_match(v1, v2):
                return True
    return False


def _clusters_compatible(
    c1: _Cluster,
    c2: _Cluster,
    *,
    strict_phone: bool,
    strict_loc: bool = False,
    max_age_diff: int | None = None,
    require_name_if_both_full: bool = True,
) -> bool:
    """Check hard demographic and strong-ID invariants before merging two clusters."""
    if len(c1.dobs | c2.dobs) > 1:
        return False
    if len(c1.genders | c2.genders) > 1:
        return False
    for id_type in _SINGLETON_ID_TYPES:
        if len(c1.singleton_ids[id_type] | c2.singleton_ids[id_type]) > 1:
            return False
    if strict_phone and c1.phones and c2.phones and not (c1.phones & c2.phones):
        return False
    if require_name_if_both_full and c1.full_names and c2.full_names:
        if not any(full_names_match(a, b) for a in c1.full_names for b in c2.full_names):
            return False
    if strict_loc:
        if c1.districts and c2.districts and not (c1.districts & c2.districts):
            return False
        if c1.pins and c2.pins and not (c1.pins & c2.pins):
            return False
        if c1.villages and c2.villages:
            if not any(villages_match(v1, v2) for v1 in c1.villages for v2 in c2.villages):
                return False
    if max_age_diff is not None and c1.ages and c2.ages:
        if not any(abs(a1 - a2) <= max_age_diff for a1 in c1.ages for a2 in c2.ages):
            return False
    return True


def _mrn_edge_allowed(c1: _Cluster, c2: _Cluster, mrn: str) -> bool:
    """Guard bare-digit MRNs against cross-hospital collisions."""
    if mrn.isdigit():
        if c1.hospitals and c2.hospitals and not (c1.hospitals & c2.hospitals):
            return False
        if len(mrn) < 6 and not _cluster_names_match(c1, c2):
            return False
    return True


class _ClusterManager:
    """Disjoint-set cluster manager with deterministic ordering."""

    def __init__(self, records: list[_RecordInfo]) -> None:
        self.parent = list(range(len(records)))
        self.clusters: dict[int, _Cluster] = {r.idx: _Cluster.from_record(r) for r in records}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def cluster_of(self, x: int) -> _Cluster:
        return self.clusters[self.find(x)]

    def active_roots(self) -> list[int]:
        return sorted(self.clusters)

    def union(self, a: int, b: int) -> int:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if ra > rb:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.clusters[ra].absorb(self.clusters.pop(rb))
        return ra


def _merge_strong_ids(cm: _ClusterManager, records: list[_RecordInfo]) -> None:
    """Phase 1a: link records sharing a strong identifier."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    uhid_digit_buckets: dict[str, list[int]] = defaultdict(list)
    bare_digit_mrns: list[tuple[int, str]] = []

    for r in records:
        for id_type, vals in r.singleton_ids.items():
            for v in vals:
                buckets[(id_type, v)].append(r.idx)
        for p in r.phones:
            buckets[("PHONE", p)].append(r.idx)
        for m in r.mrns:
            buckets[("MRN", m)].append(r.idx)
            match = _MRN_PREFIX_RE.match(m)
            if match and match.group(1) == "uhid" and len(match.group(2)) >= 5:
                uhid_digit_buckets[match.group(2)].append(r.idx)
            elif m.isdigit() and len(m) >= 5:
                bare_digit_mrns.append((r.idx, m))

    # Deterministic priority: national/singleton IDs -> MRN -> PHONE
    type_priority = {t: 0 for t in _SINGLETON_ID_TYPES}
    type_priority["MRN"] = 1
    type_priority["PHONE"] = 2

    for (id_type, id_val), idxs in sorted(buckets.items(), key=lambda kv: (type_priority[kv[0][0]], kv[0][0], kv[0][1])):
        if len(idxs) < 2 or len(idxs) > 500:
            continue
        anchor = idxs[0]
        for other in idxs[1:]:
            c1, c2 = cm.cluster_of(anchor), cm.cluster_of(other)
            if c1.root == c2.root:
                continue
            if id_type == "MRN" and not _mrn_edge_allowed(c1, c2, id_val):
                continue
            if _clusters_compatible(c1, c2, strict_phone=False):
                cm.union(c1.root, c2.root)

    # Link bare-digit MRN (e.g. "010607") to "uhid010607" when hospital and name match
    for r_idx, digits in bare_digit_mrns:
        for u_idx in uhid_digit_buckets.get(digits, ()):
            c1, c2 = cm.cluster_of(r_idx), cm.cluster_of(u_idx)
            if c1.root == c2.root:
                continue
            if c1.hospitals and c2.hospitals and not (c1.hospitals & c2.hospitals):
                continue
            if _cluster_names_match(c1, c2) and _clusters_compatible(c1, c2, strict_phone=False):
                cm.union(c1.root, c2.root)


def _merge_name_and_dob(cm: _ClusterManager) -> None:
    """Phase 1b: link clusters sharing name + exact DOB (if unique in dataset)."""
    dob_buckets: dict[str, list[int]] = defaultdict(list)
    for root in cm.active_roots():
        c = cm.clusters[root]
        if len(c.dobs) == 1:
            dob_buckets[next(iter(c.dobs))].append(root)

    for dob in sorted(dob_buckets):
        roots = dob_buckets[dob]
        if len(roots) < 2:
            continue
        # Only merge pairs whose name match inside this DOB bucket is unambiguous
        adj: dict[int, list[int]] = defaultdict(list)
        for i, r1 in enumerate(roots):
            c1 = cm.cluster_of(r1)
            for r2 in roots[i + 1 :]:
                c2 = cm.cluster_of(r2)
                if c1.root == c2.root:
                    continue
                if _cluster_names_match(c1, c2) and _clusters_compatible(c1, c2, strict_phone=True, strict_loc=False):
                    adj[r1].append(r2)
                    adj[r2].append(r1)
        _apply_unique_merges(cm, adj, strict_loc=False, max_age_diff=None)


def _collect_name_clue_candidates(
    cm: _ClusterManager,
    *,
    allow_single: bool,
) -> dict[int, list[int]]:
    """Index clusters by phonetic patient-name keys and collect Name + Relative / Village+Age+/-1 edges."""
    by_token: dict[str, list[int]] = defaultdict(list)
    for root in cm.active_roots():
        c = cm.clusters[root]
        keys: set[str] = set()
        for fn in c.full_names:
            for tok in fn:
                if len(tok) >= 2:
                    keys.add(phonetic_block_key(tok))
        if allow_single and not c.full_names:
            for sn in c.single_names:
                if len(sn[0]) >= 2 and sn[0] not in GENERIC_SURNAME_TOKENS:
                    keys.add(phonetic_block_key(sn[0]))
        for k in sorted(keys):
            if k:
                by_token[k].append(root)

    seen_pairs: set[tuple[int, int]] = set()
    adj: dict[int, list[int]] = defaultdict(list)

    for k in sorted(by_token):
        roots = by_token[k]
        if len(roots) < 2 or len(roots) > 500:
            continue
        for i, r1 in enumerate(roots):
            for r2 in roots[i + 1 :]:
                pair = (r1, r2) if r1 < r2 else (r2, r1)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                c1, c2 = cm.cluster_of(pair[0]), cm.cluster_of(pair[1])
                if c1.root == c2.root:
                    continue
                if not _cluster_names_match(c1, c2, allow_single=allow_single):
                    continue
                by_rel = (
                    bool(c1.relatives and c2.relatives)
                    and _cluster_relatives_match(c1, c2)
                    and _clusters_compatible(c1, c2, strict_phone=True, strict_loc=True, max_age_diff=5)
                )
                by_vil = (
                    bool(c1.village_age_pairs and c2.village_age_pairs)
                    and _cluster_village_age_match(c1, c2)
                    and _clusters_compatible(c1, c2, strict_phone=True, strict_loc=True, max_age_diff=None)
                )
                if by_rel or by_vil:
                    adj[pair[0]].append(pair[1])
                    adj[pair[1]].append(pair[0])
    return adj


def _apply_unique_merges(
    cm: _ClusterManager,
    adj: dict[int, list[int]],
    *,
    strict_loc: bool,
    max_age_diff: int | None,
) -> None:
    """Merge edges only when both endpoints have mutually compatible targets (no ambiguity)."""
    unambiguous: set[int] = set()
    for u in sorted(adj):
        cu = cm.cluster_of(u)
        targets = sorted(set(cm.cluster_of(v).root for v in adj[u]) - {cu.root})
        if not targets:
            continue
        ambiguous = False
        for i, t1 in enumerate(targets):
            c1 = cm.clusters[t1]
            for t2 in targets[i + 1 :]:
                c2 = cm.clusters[t2]
                if not _clusters_compatible(c1, c2, strict_phone=True, strict_loc=strict_loc, max_age_diff=max_age_diff):
                    ambiguous = True
                    break
            if ambiguous:
                break
        if not ambiguous:
            unambiguous.add(u)

    approved_edges: list[tuple[int, int]] = []
    for u in sorted(unambiguous):
        for v in sorted(set(adj[u])):
            if v in unambiguous and u < v:
                approved_edges.append((u, v))

    for u, v in approved_edges:
        c1, c2 = cm.cluster_of(u), cm.cluster_of(v)
        if c1.root == c2.root:
            continue
        if _clusters_compatible(c1, c2, strict_phone=True, strict_loc=strict_loc, max_age_diff=max_age_diff):
            cm.union(c1.root, c2.root)


def _canonical_patient_key(record_ids: list[str]) -> str:
    """Opaque, deterministic patient key containing zero raw PII."""
    joined = "\n".join(sorted(record_ids)).encode("utf-8")
    return "k:" + hashlib.sha256(joined).hexdigest()[:12]


def resolve(evidence: list[Evidence]) -> dict[str, str | None]:
    """Resolve patient record clusters across scripts, files, and hospitals."""
    secret()  # Raises RuntimeError("secret_missing") when RAKSHA_SECRET is unset/empty.
    if not evidence:
        return {}

    ordered = sorted(evidence, key=lambda e: e["record_id"])
    records = [_parse_record(i, ev) for i, ev in enumerate(ordered)]
    cm = _ClusterManager(records)

    # Phase 1: strong identifiers and exact DOB + name
    _merge_strong_ids(cm, records)
    _merge_name_and_dob(cm)

    # Phase 2a: full name + second clue (relative, or village + age +/- 1)
    adj_full = _collect_name_clue_candidates(cm, allow_single=False)
    _apply_unique_merges(cm, adj_full, strict_loc=True, max_age_diff=5)

    # Phase 2b: single-token name + second clue (fragmented notes)
    adj_single = _collect_name_clue_candidates(cm, allow_single=True)
    _apply_unique_merges(cm, adj_single, strict_loc=True, max_age_diff=5)

    out: dict[str, str | None] = {}
    for root in cm.active_roots():
        members = cm.clusters[root].members
        rids = [records[idx].record_id for idx in members]
        key = _canonical_patient_key(rids) if len(rids) >= 2 else None
        for rid in rids:
            out[rid] = key

    # Return in caller's input order (deterministically keyed by record_id)
    return {ev["record_id"]: out[ev["record_id"]] for ev in evidence}
