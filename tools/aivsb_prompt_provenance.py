# -*- coding: utf-8 -*-
"""AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004 - durable, structured AIVSB prompt provenance.

Problem fixed: AIVSB-composed prompts strip character names and are persisted (campaign
metadata.json, TikTok pack metadata.json, deep-TikTok prompt sheets) and re-read by later requests /
processes. The in-process registry (tools.identity_preservation._AIVSB_COMPOSED_REGISTRY) is lost
across processes, so governance used to depend on a format regex. This module replaces that with a
versioned provenance record captured BEFORE AIVSB rewrites the prompt and persisted next to the
prompt / image, associated by prompt hash and asset id (never by wording).

Record hash: ``provenance_record_hash`` is a deterministic, UNKEYED sha256 over the canonical JSON
of the record. It is an INTEGRITY_CHECK (detects accidental corruption / naive edits); it is NOT an
authenticated signature (anyone able to write the file can recompute it). Authority therefore never
flows from a record towards LESS restriction except the documented, narrow case of a valid
``aivsb_composed=false`` record (see DECISION_TABLE.md); records can only upgrade governance.

Flag OFF (ENABLE_IDENTITY_PRESERVATION unset): nothing in app.py calls into this module (every call
site is guarded), and the identity gate returns BYPASS before any provenance logic runs.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "AIVSB_PROMPT_PROVENANCE/1"
SUPPORTED_SCHEMA_VERSIONS: Tuple[str, ...] = (SCHEMA_VERSION,)
RECORD_HASH_KIND = "INTEGRITY_CHECK_SHA256_UNKEYED_NOT_A_SIGNATURE"
METADATA_KEY = "aivsb_prompt_provenance"
FOLDER_SIDECAR_NAME = "aivsb_prompt_provenance.json"
IMAGE_SIDECAR_SUFFIX = ".aivsb_provenance.json"
IMAGE_BINDING_KIND = "AIVSB_IMAGE_PROVENANCE_BINDING/1"

REQUIRED_FIELDS: Tuple[str, ...] = (
    "schema_version", "provenance_id", "source_run_id", "source_asset_id", "aivsb_composed", "novel_id",
    "character_ids", "depicted_character_ids", "scene_subject_ids", "pre_aivsb_image_intent",
    "governed_context_present", "identity_contract_id", "source_prompt_hash", "composed_prompt_hash",
    "provenance_record_hash", "parent_provenance_id", "transform", "origin", "record_hash_kind",
)
_LIST_FIELDS = ("character_ids", "depicted_character_ids", "scene_subject_ids")
_STR_FIELDS = ("schema_version", "provenance_id", "source_run_id", "source_asset_id", "novel_id",
               "identity_contract_id", "source_prompt_hash", "composed_prompt_hash", "provenance_record_hash",
               "parent_provenance_id", "transform", "origin", "record_hash_kind")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_APPENDED_GUIDANCE_PREFIX = "Learned image feedback guidance:"


def _ip():
    from tools import identity_preservation as ip  # lazy: identity_preservation imports us lazily too
    return ip


# ---------------------------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------------------------
def prompt_norm(prompt: Any) -> str:
    """Whitespace-collapse only (same normalisation as the legacy in-process registry)."""
    return re.sub(r"\s+", " ", str(prompt or "")).strip()


def prompt_hash(prompt: Any) -> str:
    n = prompt_norm(prompt)
    return hashlib.sha256(n.encode("utf-8")).hexdigest() if n else ""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_record_hash(rec: Mapping[str, Any]) -> str:
    body = {k: rec.get(k) for k in REQUIRED_FIELDS if k != "provenance_record_hash"}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def compute_provenance_id(rec: Mapping[str, Any]) -> str:
    body = {k: rec.get(k) for k in REQUIRED_FIELDS if k not in ("provenance_record_hash", "provenance_id")}
    return "aivsbprov_" + hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()[:32]


def candidate_prompt_hashes(*texts: Any) -> List[str]:
    """Hashes a gate call can be associated by: each text, and each text with the app's appended
    'Learned image feedback guidance:' suffix split off. Association is exact (by hash), never
    by wording similarity."""
    out: List[str] = []
    for t in texts:
        raw = str(t or "")
        for c in ([raw, raw.split(_APPENDED_GUIDANCE_PREFIX, 1)[0]] if _APPENDED_GUIDANCE_PREFIX in raw else [raw]):
            h = prompt_hash(c)
            if h and h not in out:
                out.append(h)
    return out


# ---------------------------------------------------------------------------------------------
# record construction
# ---------------------------------------------------------------------------------------------
def _ordered_keys(keys: Iterable[str]) -> List[str]:
    ip = _ip()
    s = set(k for k in keys if k)
    return [k for k in ip.GOVERNED_IDENTITY_CONTRACTS if k in s]


def _intent_snapshot(intent: Any) -> Optional[Dict[str, Any]]:
    ip = _ip()
    req = ip.coerce_image_intent_request(intent) if intent is not None else None
    if req is None:
        return None
    return {
        "depicted_characters": [str(x) for x in (req.depicted_characters or ())],
        "scene_subject": str(req.scene_subject or ""),
        "asset_role": str(req.asset_role or ""),
        "background_only": req.background_only,
        "requested_asset_type": str(req.requested_asset_type or ""),
        "origin": str(req.origin or ""),
    }


def _finalize(rec: Dict[str, Any]) -> Dict[str, Any]:
    rec["record_hash_kind"] = RECORD_HASH_KIND
    rec["provenance_id"] = compute_provenance_id(rec)
    rec["provenance_record_hash"] = compute_record_hash(rec)
    return {k: rec[k] for k in REQUIRED_FIELDS}


def build_record(
    prompt: Any,
    *,
    source_prompt: Any,
    source_text: Any,
    novel_id: Any,
    aivsb_composed: bool,
    source_run_id: str,
    source_asset_id: str = "",
    pre_aivsb_image_intent: Any = None,
    origin: str = "",
) -> Dict[str, Any]:
    """Original record for a newly produced prompt. ``source_text`` is the pre-AIVSB source
    (title / chapter / phrases / beat) whose governed names are captured BEFORE AIVSB strips them;
    ``source_prompt`` is the pre-AIVSB (legacy) prompt string."""
    ip = _ip()
    nid = ip.resolve_production_novel_alias(novel_id) or ""
    novel_chars = list(ip.governed_character_keys_for_novel(nid)) if nid else []
    depicted = _ordered_keys(ip.governed_characters_in_text(source_text))
    snap = _intent_snapshot(pre_aivsb_image_intent)
    subj: List[str] = []
    if snap:
        for c in list(snap["depicted_characters"]) + [snap["scene_subject"]]:
            k = ip.normalize_identity_character_key(c)
            if k:
                subj.append(k)
    subj = _ordered_keys(subj)
    chars = _ordered_keys(novel_chars + depicted + subj)
    contract = ip.GOVERNED_IDENTITY_CONTRACTS[chars[0]].contract_id if len(chars) == 1 else ""
    rec = {
        "schema_version": SCHEMA_VERSION,
        "provenance_id": "",
        "source_run_id": str(source_run_id or ""),
        "source_asset_id": str(source_asset_id or ""),
        "aivsb_composed": bool(aivsb_composed),
        "novel_id": nid,
        "character_ids": chars,
        "depicted_character_ids": depicted,
        "scene_subject_ids": subj,
        "pre_aivsb_image_intent": snap,
        "governed_context_present": bool(chars),
        "identity_contract_id": contract,
        "source_prompt_hash": prompt_hash(source_prompt),
        "composed_prompt_hash": prompt_hash(prompt),
        "provenance_record_hash": "",
        "parent_provenance_id": "",
        "transform": "",
        "origin": str(origin or ""),
    }
    return _finalize(rec)


def derive_record(parent: Mapping[str, Any], new_prompt: Any, *, transform: str, source_asset_id: str = "",
                  origin: str = "", source_run_id: str = "") -> Dict[str, Any]:
    """Derived record for a deliberate prompt transform (wrap / enhance / sheet). Governance fields
    are copied unchanged (never reduced); the parent's hashes are never overwritten; the link is
    ``parent_provenance_id``. ``source_prompt_hash`` = the PARENT's composed prompt hash (the
    transform input)."""
    if not transform:
        raise ValueError("derived provenance requires a transform name")
    rec = {k: parent.get(k) for k in REQUIRED_FIELDS}
    rec.update({
        "provenance_id": "",
        "source_run_id": str(source_run_id or parent.get("source_run_id") or ""),
        "source_asset_id": str(source_asset_id or parent.get("source_asset_id") or ""),
        "source_prompt_hash": str(parent.get("composed_prompt_hash") or ""),
        "composed_prompt_hash": prompt_hash(new_prompt),
        "provenance_record_hash": "",
        "parent_provenance_id": str(parent.get("provenance_id") or ""),
        "transform": str(transform),
        "origin": str(origin or parent.get("origin") or ""),
        "character_ids": list(parent.get("character_ids") or []),
        "depicted_character_ids": list(parent.get("depicted_character_ids") or []),
        "scene_subject_ids": list(parent.get("scene_subject_ids") or []),
    })
    return _finalize(rec)


# ---------------------------------------------------------------------------------------------
# validation (Phase 3)
# ---------------------------------------------------------------------------------------------
def validate_record(rec: Any, *, parents: Optional[Mapping[str, Mapping[str, Any]]] = None,
                    _depth: int = 0) -> Tuple[bool, str]:
    """(True, "") or (False, reason). Checks schema version, required fields / types, record hash
    (integrity check), provenance id, canonical novel, character <-> novel <-> contract
    association, and for derived records the parent link (when ``parents`` is supplied) and that
    governance was not reduced."""
    ip = _ip()
    if not isinstance(rec, Mapping):
        return False, "MALFORMED_RECORD_NOT_A_MAPPING"
    sv = rec.get("schema_version")
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        return False, f"UNSUPPORTED_SCHEMA_VERSION:{sv!r}"
    for k in REQUIRED_FIELDS:
        if k not in rec:
            return False, f"MISSING_FIELD:{k}"
    for k in _STR_FIELDS:
        if not isinstance(rec.get(k), str):
            return False, f"MALFORMED_FIELD:{k}"
    for k in _LIST_FIELDS:
        v = rec.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return False, f"MALFORMED_FIELD:{k}"
    if not isinstance(rec.get("aivsb_composed"), bool) or not isinstance(rec.get("governed_context_present"), bool):
        return False, "MALFORMED_FIELD:boolean"
    if rec.get("pre_aivsb_image_intent") is not None and not isinstance(rec.get("pre_aivsb_image_intent"), Mapping):
        return False, "MALFORMED_FIELD:pre_aivsb_image_intent"
    if rec.get("record_hash_kind") != RECORD_HASH_KIND:
        return False, "MALFORMED_FIELD:record_hash_kind"
    if not _HEX64.match(rec["composed_prompt_hash"]):
        return False, "MALFORMED_FIELD:composed_prompt_hash"
    if rec["source_prompt_hash"] and not _HEX64.match(rec["source_prompt_hash"]):
        return False, "MALFORMED_FIELD:source_prompt_hash"
    if compute_record_hash(rec) != rec["provenance_record_hash"]:
        return False, "RECORD_HASH_MISMATCH"
    if compute_provenance_id(rec) != rec["provenance_id"]:
        return False, "PROVENANCE_ID_MISMATCH"
    nid = rec["novel_id"]
    if nid and ip.resolve_production_novel_alias(nid) != nid:
        return False, f"NON_CANONICAL_NOVEL:{nid}"
    chars = rec["character_ids"]
    for k in chars + rec["depicted_character_ids"] + rec["scene_subject_ids"]:
        c = ip.GOVERNED_IDENTITY_CONTRACTS.get(k)
        if c is None:
            return False, f"UNKNOWN_CHARACTER_ID:{k}"
        if nid and c.novel_id != nid:
            return False, f"CHARACTER_NOVEL_MISMATCH:{k}:{nid}"
    if nid and not set(ip.governed_character_keys_for_novel(nid)) <= set(chars):
        return False, f"GOVERNED_CONTEXT_REDUCED:{nid}"
    if not (set(rec["depicted_character_ids"]) | set(rec["scene_subject_ids"])) <= set(chars):
        return False, "DEPICTED_NOT_SUBSET_OF_CHARACTER_IDS"
    if rec["governed_context_present"] != bool(chars):
        return False, "GOVERNED_CONTEXT_FLAG_INCONSISTENT"
    expect_contract = ip.GOVERNED_IDENTITY_CONTRACTS[chars[0]].contract_id if len(chars) == 1 else ""
    if rec["identity_contract_id"] != expect_contract:
        return False, f"CONTRACT_MISMATCH:{rec['identity_contract_id']}!={expect_contract}"
    pid = rec["parent_provenance_id"]
    if bool(pid) != bool(rec["transform"]):
        return False, "DERIVED_LINK_INCONSISTENT"
    if pid and parents is not None:
        par = parents.get(pid)
        if par is None:
            return False, f"PARENT_MISSING:{pid}"
        if _depth > 16:
            return False, "PARENT_CHAIN_TOO_DEEP"
        ok, why = validate_record(par, parents=parents, _depth=_depth + 1)
        if not ok:
            return False, f"PARENT_INVALID:{why}"
        if (par.get("novel_id") != nid or not set(par.get("character_ids") or []) <= set(chars)
                or (par.get("aivsb_composed") and not rec["aivsb_composed"])
                or par.get("identity_contract_id") != rec["identity_contract_id"]
                or not set(par.get("depicted_character_ids") or []) <= set(rec["depicted_character_ids"])):
            return False, "DERIVED_GOVERNANCE_REDUCED"
        if rec["source_prompt_hash"] != par.get("composed_prompt_hash"):
            return False, "DERIVED_SOURCE_HASH_NOT_PARENT"
    return True, ""


# ---------------------------------------------------------------------------------------------
# advisory format detector (Phase 5) - NEVER an acceptance authority
# ---------------------------------------------------------------------------------------------
_STRICT_SIGNATURE = re.compile(
    r"(?<![A-Za-z0-9_])(?:en|ha|hp|sf), (?:expressing [^,]{1,120}, )?[A-Za-z0-9_]+ shot\b")
_TOLERANT_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("HEADER", re.compile(r"(?<![a-z0-9_])(?:en|ha|hp|sf)\s*,\s*(?:expressing\b|[a-z0-9_\-]+(?:\s+[a-z0-9_\-]+){0,3}\s+shot\b)", re.I)),
    ("FULLNAME_HEADER", re.compile(r"(?:eternal\s+nexus|heavenly\s+ascension\s+system|hundredfold\s+path|soul\s*forge\s+era)\s*,\s*expressing\b", re.I)),
    ("EXPRESSING_CAMERA", re.compile(r"\bexpressing\s+[^\n]{1,200}?,\s*[a-z0-9_\-]+(?:[\s_\-]+[a-z0-9]+){0,3}\s+shot\s+with\s+\d{1,3}\s*mm\b", re.I)),
    ("SNAKE_CAMERA_LENS", re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\s+shot\s+with\s+\d{1,3}\s*mm\s+lens\b", re.I)),
    ("WORLD_POWER_MARKERS", re.compile(r"\bworld:\s.{0,400}?\bpower visuals:", re.I | re.S)),
)


def detect_aivsb_format(*texts: Any) -> Tuple[str, str]:
    """('STRICT_MATCH'|'TOLERANT_MATCH'|'NO_MATCH', pattern). Advisory only: a match may trigger
    review (upgrade); a non-match NEVER establishes NOT_AIVSB / SCENERY_ONLY / auto-accept."""
    norms = [prompt_norm(t) for t in texts if prompt_norm(t)]
    if not norms:
        return "NO_MATCH", ""
    if any(_STRICT_SIGNATURE.search(n) for n in norms):
        return "STRICT_MATCH", "STRICT_SIGNATURE"
    for name, pat in _TOLERANT_PATTERNS:
        if any(pat.search(n) for n in norms):
            return "TOLERANT_MATCH", name
    return "NO_MATCH", ""


# ---------------------------------------------------------------------------------------------
# stores, persistence (metadata block, folder sidecar, image-bound sidecar), process cache
# ---------------------------------------------------------------------------------------------
@dataclass
class ProvenanceStore:
    records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    raw_invalid: List[Any] = field(default_factory=list)
    by_prompt_hash: Dict[str, List[str]] = field(default_factory=dict)
    by_asset: Dict[str, str] = field(default_factory=dict)
    persisted: bool = False
    source: str = ""
    load_problems: List[str] = field(default_factory=list)

    def add(self, rec: Mapping[str, Any], asset: str = "") -> None:
        r = dict(rec)
        pid = str(r.get("provenance_id") or "")
        if not pid:
            self.raw_invalid.append(r)
            return
        self.records[pid] = r
        h = str(r.get("composed_prompt_hash") or "")
        if h:
            ids = self.by_prompt_hash.setdefault(h, [])
            if pid not in ids:
                ids.append(pid)
        if asset:
            self.by_asset[str(asset)] = pid

    def is_empty(self) -> bool:
        return not self.records and not self.raw_invalid

    def to_block(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_hash_kind": RECORD_HASH_KIND,
            "records": [self.records[k] for k in sorted(self.records)],
            "by_prompt_hash": {k: list(v) for k, v in sorted(self.by_prompt_hash.items())},
            "by_asset": dict(sorted(self.by_asset.items())),
        }


def store_from_block(block: Any, *, source: str, persisted: bool = True) -> ProvenanceStore:
    st = ProvenanceStore(persisted=persisted, source=source)
    if block is None:
        return st
    if not isinstance(block, Mapping):
        st.load_problems.append("BLOCK_NOT_A_MAPPING")
        return st
    if block.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        st.load_problems.append(f"UNSUPPORTED_BLOCK_SCHEMA:{block.get('schema_version')!r}")
    recs = block.get("records")
    if not isinstance(recs, list):
        st.load_problems.append("BLOCK_RECORDS_NOT_A_LIST")
        recs = []
    for r in recs:
        if isinstance(r, Mapping) and isinstance(r.get("provenance_id"), str) and r.get("provenance_id"):
            st.add(r)
        else:
            st.raw_invalid.append(r)
    bph = block.get("by_prompt_hash")
    if isinstance(bph, Mapping):
        for h, ids in bph.items():
            if isinstance(ids, list):
                cur = st.by_prompt_hash.setdefault(str(h), [])
                for i in ids:
                    if str(i) not in cur:
                        cur.append(str(i))
    ba = block.get("by_asset")
    if isinstance(ba, Mapping):
        for a, i in ba.items():
            st.by_asset[str(a)] = str(i)
    return st


def merge_stores(*stores: Optional[ProvenanceStore], source: str = "") -> ProvenanceStore:
    out = ProvenanceStore(source=source)
    for s in stores:
        if s is None:
            continue
        out.persisted = out.persisted or s.persisted
        out.load_problems.extend(s.load_problems)
        out.raw_invalid.extend(s.raw_invalid)
        for pid, r in s.records.items():
            prev = out.records.get(pid)
            if prev is not None and _canon(prev) != _canon(r):
                out.load_problems.append(f"CONFLICTING_COPIES:{pid}")
                out.raw_invalid.append(r)
                continue
            out.records[pid] = r
        for h, ids in s.by_prompt_hash.items():
            cur = out.by_prompt_hash.setdefault(h, [])
            for i in ids:
                if i not in cur:
                    cur.append(i)
        for a, i in s.by_asset.items():
            if a in out.by_asset and out.by_asset[a] != i:
                out.load_problems.append(f"CONFLICTING_ASSET_MAPPING:{a}")
            out.by_asset[a] = i
    return out


def load_folder_store(folder: Any, metadata: Optional[Mapping[str, Any]] = None) -> ProvenanceStore:
    """Persisted-reader store for a pack folder: metadata.json block + folder sidecar. The store is
    always marked ``persisted`` (even when empty): prompts read back from disk without provenance
    are legacy and must never be treated as non-AIVSB."""
    stores: List[ProvenanceStore] = []
    srcs: List[str] = []
    p = Path(str(folder or ""))
    meta = metadata
    if meta is None:
        try:
            mp = p / "metadata.json"
            meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        except Exception as exc:  # noqa: BLE001
            meta = {}
            stores.append(ProvenanceStore(persisted=True, source="METADATA", load_problems=[f"METADATA_UNREADABLE:{type(exc).__name__}"]))
    if isinstance(meta, Mapping) and METADATA_KEY in meta:
        stores.append(store_from_block(meta.get(METADATA_KEY), source="METADATA"))
        srcs.append("METADATA")
    side = p / FOLDER_SIDECAR_NAME
    if side.exists():
        try:
            stores.append(store_from_block(json.loads(side.read_text(encoding="utf-8")), source="FOLDER_SIDECAR"))
        except Exception as exc:  # noqa: BLE001
            stores.append(ProvenanceStore(persisted=True, source="FOLDER_SIDECAR", load_problems=[f"SIDECAR_UNREADABLE:{type(exc).__name__}"]))
        srcs.append("FOLDER_SIDECAR")
    st = merge_stores(*stores, source="+".join(srcs) or "PERSISTED_READER_NO_PROVENANCE")
    st.persisted = True
    return st


def write_folder_sidecar(folder: Any, store: ProvenanceStore) -> Path:
    p = Path(str(folder)) / FOLDER_SIDECAR_NAME
    p.write_text(json.dumps(store.to_block(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_sidecar_path(image_path: Any) -> Path:
    p = Path(str(image_path))
    return p.with_name(p.name + IMAGE_SIDECAR_SUFFIX)


def _binding_hash(body: Mapping[str, Any]) -> str:
    keys = ("kind", "image_sha256", "provenance_record") + (("provenance_chain",) if "provenance_chain" in body else ())
    return hashlib.sha256(_canon({k: body.get(k) for k in keys}).encode("utf-8")).hexdigest()


def _ancestor_chain(record: Mapping[str, Any], parents: Optional[Mapping[str, Mapping[str, Any]]] = None) -> List[Dict[str, Any]]:
    pool: Dict[str, Mapping[str, Any]] = dict(index_parent_map())
    if parents:
        pool.update(parents)
    out: List[Dict[str, Any]] = []
    pid, n = str(record.get("parent_provenance_id") or ""), 0
    while pid and n < 17:
        par = pool.get(pid)
        if par is None:
            break
        out.append(dict(par))
        pid, n = str(par.get("parent_provenance_id") or ""), n + 1
    return out


def write_image_provenance(image_path: Any, record: Mapping[str, Any],
                           parents: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Optional[Path]:
    """Bind a provenance record (and, for a derived record, its ancestor chain) to the exact image
    bytes (image sha256). Returns the sidecar path (None when the image does not exist)."""
    p = Path(str(image_path))
    if not p.exists() or not p.is_file():
        return None
    sha = _sha256_file(p)
    body = {"kind": IMAGE_BINDING_KIND, "schema_version": SCHEMA_VERSION, "image_name": p.name,
            "image_sha256": sha, "provenance_record": dict(record)}
    if record.get("parent_provenance_id"):
        body["provenance_chain"] = _ancestor_chain(record, parents)
    body["binding_hash"] = _binding_hash(body)
    side = image_sidecar_path(p)
    side.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return side


def read_image_provenance(image_path: Any, image_sha256: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    """(record, status): ABSENT | VALID_BINDING | STALE_IMAGE_SHA | MALFORMED | BINDING_HASH_MISMATCH."""
    if not image_path:
        return None, "ABSENT"
    p = Path(str(image_path))
    cands = [image_sidecar_path(p)]
    ip = _ip()
    try:
        base = p.with_name(ip._QUARANTINE_TAG_RE.sub("", p.name, count=1))
        if base != p:
            cands.append(image_sidecar_path(base))
    except Exception:  # noqa: BLE001
        pass
    side = next((c for c in cands if c.exists()), None)
    if side is None:
        return None, "ABSENT"
    try:
        body = json.loads(side.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, "MALFORMED"
    if not isinstance(body, Mapping) or body.get("kind") != IMAGE_BINDING_KIND or not isinstance(body.get("provenance_record"), Mapping):
        return None, "MALFORMED"
    expect = _binding_hash(body)
    rec = dict(body["provenance_record"])
    if expect != body.get("binding_hash"):
        return rec, "BINDING_HASH_MISMATCH"
    sha = image_sha256 or (_sha256_file(p) if p.exists() else "")
    if sha and body.get("image_sha256") != sha:
        return rec, "STALE_IMAGE_SHA"
    return rec, "VALID_BINDING"


def read_image_provenance_chain(image_path: Any) -> Dict[str, Dict[str, Any]]:
    """Ancestor records bound in an image sidecar (only meaningful after read_image_provenance
    returned VALID_BINDING / STALE_IMAGE_SHA, which already verified the binding hash)."""
    try:
        p = Path(str(image_path))
        cands = [image_sidecar_path(p)]
        base = p.with_name(_ip()._QUARANTINE_TAG_RE.sub("", p.name, count=1))
        if base != p:
            cands.append(image_sidecar_path(base))
        side = next((c for c in cands if c.exists()), None)
        if side is None:
            return {}
        body = json.loads(side.read_text(encoding="utf-8"))
        return {str(r.get("provenance_id")): dict(r) for r in (body.get("provenance_chain") or [])
                if isinstance(r, Mapping) and r.get("provenance_id")}
    except Exception:  # noqa: BLE001
        return {}


def copy_image_provenance(src: Any, dst: Any) -> bool:
    """Copy an image-bound provenance sidecar alongside a copied image (bytes identical -> the
    binding stays valid; the record is unchanged)."""
    s = image_sidecar_path(src)
    if not s.exists():
        return False
    d = image_sidecar_path(dst)
    d.write_bytes(s.read_bytes())
    return True


# process cache (NOT authority by itself: it only lets a same-process consumer find the record that
# was just written; durable association is the persisted metadata / sidecars)
_INDEX: Dict[str, List[Dict[str, Any]]] = {}
_INDEX_BY_ID: Dict[str, Dict[str, Any]] = {}
_INDEX_ORDER: List[str] = []
_INDEX_MAX = 65536


_INDEX_OWNER: List[Any] = [None]


def _sync_index_lifetime() -> None:
    """The process cache shares the lifetime of the in-process AIVSB registry
    (tools.identity_preservation._AIVSB_COMPOSED_REGISTRY): when that registry object is replaced
    (process restart semantics / per-test reset) the cache is cleared with it. Production never
    replaces the registry object, so this is a no-op there."""
    try:
        reg = _ip()._AIVSB_COMPOSED_REGISTRY
    except Exception:  # noqa: BLE001
        return
    if _INDEX_OWNER[0] is not reg:
        clear_index()
        _INDEX_OWNER[0] = reg


def register_record(rec: Mapping[str, Any]) -> None:
    _sync_index_lifetime()
    r = dict(rec)
    h = str(r.get("composed_prompt_hash") or "")
    pid = str(r.get("provenance_id") or "")
    if not h or not pid:
        return
    lst = _INDEX.setdefault(h, [])
    if all(x.get("provenance_id") != pid for x in lst):
        lst.append(r)
        _INDEX_ORDER.append(pid)
    _INDEX_BY_ID[pid] = r
    while len(_INDEX_ORDER) > _INDEX_MAX:
        old = _INDEX_ORDER.pop(0)
        o = _INDEX_BY_ID.pop(old, None)
        if o is not None:
            lst2 = _INDEX.get(str(o.get("composed_prompt_hash") or ""), [])
            lst2[:] = [x for x in lst2 if x.get("provenance_id") != old]


def lookup_index(prompt: Any) -> Optional[Dict[str, Any]]:
    """Most recent record for exactly this prompt (hash), or None."""
    _sync_index_lifetime()
    for h in candidate_prompt_hashes(prompt):
        lst = _INDEX.get(h)
        if lst:
            return dict(lst[-1])
    return None


def index_parent_map() -> Dict[str, Dict[str, Any]]:
    _sync_index_lifetime()
    return dict(_INDEX_BY_ID)


def clear_index() -> None:
    _INDEX.clear()
    _INDEX_BY_ID.clear()
    _INDEX_ORDER.clear()


_SCOPE: "contextvars.ContextVar[Optional[ProvenanceStore]]" = contextvars.ContextVar("aivsb_provenance_scope", default=None)


def current_scope() -> Optional[ProvenanceStore]:
    return _SCOPE.get()


class provenance_scope:  # noqa: N801 - context manager
    """Ambient persisted-reader provenance for the duration of a reader call (regeneration, reuse,
    prompt-sheet). Nested scopes merge (union = stricter)."""

    def __init__(self, store: Optional[ProvenanceStore]):
        self._store = store
        self._token = None

    def __enter__(self) -> Optional[ProvenanceStore]:
        outer = _SCOPE.get()
        st = self._store
        if outer is not None and st is not None:
            st = merge_stores(outer, st, source=f"{outer.source}+{st.source}")
        elif st is None:
            st = outer
        self._token = _SCOPE.set(st)
        return st

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _SCOPE.reset(self._token)
            self._token = None


def coerce_store(value: Any, *, source: str = "EXPLICIT") -> Optional[ProvenanceStore]:
    """Explicit gate argument: a record, a list of records, a metadata block, a full metadata dict
    (with the block under METADATA_KEY) or a ProvenanceStore."""
    if value is None:
        return None
    if isinstance(value, ProvenanceStore):
        return value
    if isinstance(value, Mapping):
        if METADATA_KEY in value:
            return store_from_block(value.get(METADATA_KEY), source=source)
        if "records" in value and "schema_version" in value and "provenance_id" not in value:
            return store_from_block(value, source=source)
        st = ProvenanceStore(persisted=True, source=source)
        st.add(value)
        return st
    if isinstance(value, (list, tuple)):
        st = ProvenanceStore(persisted=True, source=source)
        for r in value:
            if isinstance(r, Mapping):
                st.add(r)
            else:
                st.raw_invalid.append(r)
        return st
    st = ProvenanceStore(persisted=True, source=source)
    st.raw_invalid.append(value)
    st.load_problems.append("EXPLICIT_PROVENANCE_UNSUPPORTED_TYPE")
    return st


# ---------------------------------------------------------------------------------------------
# gate assessment (Phases 3 / 4 / 5)
# ---------------------------------------------------------------------------------------------
@dataclass
class ProvenanceAssessment:
    status: str = "ABSENT"              # VALID | ABSENT | INVALID | MISMATCH | CONFLICT
    required: bool = False              # provenance-required context (PRC)
    records: List[Dict[str, Any]] = field(default_factory=list)
    recovered_from: str = "NONE"
    integrity_valid: str = "NOT_APPLICABLE"
    association_valid: str = "NOT_APPLICABLE"
    association_method: str = ""
    mismatch_reason: str = ""
    detector: str = "NO_MATCH"
    detector_pattern: str = ""
    drift: bool = False
    aivsb_composed: Optional[bool] = None
    novel_ids: List[str] = field(default_factory=list)
    character_ids: List[str] = field(default_factory=list)
    depicted_character_ids: List[str] = field(default_factory=list)
    image_binding: str = "ABSENT"
    notes: List[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.records) or self.status in ("INVALID", "MISMATCH", "CONFLICT")


def _linked(a: Mapping[str, Any], b: Mapping[str, Any], parents: Mapping[str, Mapping[str, Any]]) -> bool:
    """True when a and b are the same record or one is an ancestor of the other."""
    def chain(r: Mapping[str, Any]) -> List[str]:
        out, cur, n = [], r, 0
        while cur is not None and n < 20:
            out.append(str(cur.get("provenance_id") or ""))
            pid = str(cur.get("parent_provenance_id") or "")
            cur = parents.get(pid) if pid else None
            n += 1
        return out
    ia, ib = str(a.get("provenance_id") or ""), str(b.get("provenance_id") or "")
    return ia == ib or ia in chain(b) or ib in chain(a)


def assess(
    *,
    prompt: str,
    scene_text: str,
    image_path: Optional[Path],
    image_sha256: str,
    is_fallback: bool,
    explicit: Any,
    aivsb_env_enabled: bool,
    request_novel: str,
    structured_keys: Sequence[str],
    ctx_contract_id: str,
) -> ProvenanceAssessment:
    pa = ProvenanceAssessment()
    pa.detector, pa.detector_pattern = detect_aivsb_format(prompt, scene_text)
    hashes = candidate_prompt_hashes(prompt, scene_text)
    have_text = bool(hashes)
    explicit_store = coerce_store(explicit) if explicit is not None else None
    scope = current_scope()
    img_rec, img_status = (read_image_provenance(image_path, image_sha256) if (is_fallback and image_path is not None)
                           else (None, "ABSENT"))
    pa.image_binding = img_status
    pa.required = bool(aivsb_env_enabled or scope is not None or explicit_store is not None or img_status != "ABSENT")

    parents: Dict[str, Dict[str, Any]] = dict(index_parent_map())
    for st in (scope, explicit_store):
        if st is not None:
            parents.update(st.records)
    if img_rec is not None and isinstance(img_rec.get("provenance_id"), str):
        parents.setdefault(img_rec["provenance_id"], img_rec)
        if img_status in ("VALID_BINDING", "STALE_IMAGE_SHA"):
            for _pid, _pr in read_image_provenance_chain(image_path).items():
                parents.setdefault(_pid, _pr)

    cands: List[Tuple[str, Dict[str, Any], str]] = []   # (source, record, association_method)
    problems: List[str] = []
    img_name = Path(str(image_path)).name if image_path is not None else ""
    try:
        img_base = _ip()._QUARANTINE_TAG_RE.sub("", img_name, count=1) if img_name else ""
    except Exception:  # noqa: BLE001
        img_base = img_name

    def from_store(st: ProvenanceStore, src: str) -> None:
        if st.load_problems:
            problems.extend(f"{src}:{p}" for p in st.load_problems if p.startswith(("CONFLICTING", "UNSUPPORTED", "BLOCK_")))
        matched_ids: List[str] = []
        for h in hashes:
            for pid in st.by_prompt_hash.get(h, []):
                if pid in st.records and pid not in matched_ids:
                    matched_ids.append(pid)
            for pid, r in st.records.items():
                if r.get("composed_prompt_hash") == h and pid not in matched_ids:
                    matched_ids.append(pid)
        for r in st.raw_invalid:
            if isinstance(r, Mapping) and r.get("composed_prompt_hash") in hashes:
                problems.append(f"{src}:INVALID_RECORD_ASSOCIATED")
        for pid in matched_ids:
            cands.append((src, st.records[pid], "PROMPT_HASH"))
        asset_pid = st.by_asset.get(img_name) or (st.by_asset.get(img_base) if img_base else None)
        if asset_pid:
            ar = st.records.get(asset_pid)
            if ar is None:
                problems.append(f"{src}:ASSET_MAPPING_TO_MISSING_RECORD:{img_base or img_name}")
            elif have_text and not any(_linked(ar, st.records[m], parents) for m in matched_ids):
                problems.append(f"{src}:PROMPT_ASSOCIATION_MISMATCH:asset={img_base or img_name}")
            elif not have_text:
                cands.append((src, ar, "ASSET_ID"))
        if not matched_ids and not asset_pid and len(st.records) and not have_text and explicit_store is st:
            # explicit provenance handed to a prompt-less call: associate by the caller's own act
            for r in st.records.values():
                cands.append((src, r, "EXPLICIT_ARGUMENT"))
        if explicit_store is st and have_text and st.records and not matched_ids and not asset_pid:
            problems.append(f"{src}:PROMPT_ASSOCIATION_MISMATCH:explicit_record_not_for_this_prompt")

    if explicit_store is not None:
        from_store(explicit_store, "EXPLICIT")
    if scope is not None:
        from_store(scope, "SCOPE_" + (scope.source or "PERSISTED"))
    if img_status != "ABSENT":
        if img_status in ("MALFORMED", "BINDING_HASH_MISMATCH"):
            problems.append(f"IMAGE_SIDECAR:{img_status}")
        elif img_status == "STALE_IMAGE_SHA":
            # bytes changed since binding: the record may only upgrade (composed -> review)
            if img_rec is not None and img_rec.get("aivsb_composed") is True:
                cands.append(("IMAGE_SIDECAR_STALE", img_rec, "IMAGE_BINDING_STALE_UPGRADE_ONLY"))
            pa.notes.append("IMAGE_SIDECAR_STALE_IMAGE_SHA")
        elif img_rec is not None:
            cands.append(("IMAGE_SIDECAR", img_rec, "IMAGE_SHA256_BINDING"))
    if not cands and not problems:
        for h in hashes:
            for r in _INDEX.get(h, []):
                cands.append(("PROCESS_INDEX", dict(r), "PROMPT_HASH"))

    # validate every associated record (integrity / schema / association / parent link)
    valid: List[Tuple[str, Dict[str, Any], str]] = []
    for src, r, how in cands:
        ok, why = validate_record(r, parents=parents)
        if not ok:
            problems.append(f"{src}:INVALID:{why}")
            continue
        valid.append((src, r, how))
    if problems:
        pa.status = "INVALID" if any(":INVALID" in p or "IMAGE_SIDECAR:" in p or "UNSUPPORTED" in p or "BLOCK_" in p
                                     for p in problems) else "MISMATCH"
        pa.mismatch_reason = ";".join(sorted(set(problems)))
        pa.integrity_valid = "NO" if pa.status == "INVALID" else ("YES" if valid else "NOT_APPLICABLE")
        pa.association_valid = "NO"
        pa.recovered_from = ",".join(sorted({s for s, _r, _h in cands})) or "NONE"
        return pa
    if not valid:
        pa.status = "ABSENT"
        return pa
    # consistency vs structured context (Phase 3: source identity / novel / character / contract)
    novels = sorted({str(r.get("novel_id") or "") for _s, r, _h in valid if r.get("novel_id")})
    strict_sources = [v for v in valid if v[0] != "PROCESS_INDEX"]
    if request_novel:
        bad_strict = [v for v in strict_sources if str(v[1].get("novel_id") or "") != request_novel]
        keep = [v for v in valid if str(v[1].get("novel_id") or "") == request_novel]
        if bad_strict or not keep:
            pa.status = "MISMATCH"
            pa.mismatch_reason = (f"NOVEL_MISMATCH:provenance={','.join(novels) or '<non-governed>'}"
                                  f":request={request_novel}")
            pa.integrity_valid, pa.association_valid = "YES", "NO"
            pa.recovered_from = ",".join(sorted({s for s, _r, _h in valid}))
            return pa
        dropped = len(valid) - len(keep)
        if dropped:
            pa.notes.append(f"COLLISION_PROCESS_INDEX_RECORDS_OTHER_NOVEL_IGNORED={dropped}")
        valid = keep
    elif len(novels) > 1:
        pa.status = "CONFLICT"
        pa.mismatch_reason = f"CONFLICTING_PROVENANCE_NOVELS:{','.join(novels)}"
        pa.integrity_valid, pa.association_valid = "YES", "NO"
        pa.recovered_from = ",".join(sorted({s for s, _r, _h in valid}))
        return pa
    chars = _ordered_keys(k for _s, r, _h in valid for k in (r.get("character_ids") or []))
    if structured_keys and chars and not set(structured_keys) <= set(chars):
        pa.status = "MISMATCH"
        pa.mismatch_reason = f"CHARACTER_MISMATCH:provenance={','.join(chars)}:structured={','.join(structured_keys)}"
        pa.integrity_valid, pa.association_valid = "YES", "NO"
        pa.recovered_from = ",".join(sorted({s for s, _r, _h in valid}))
        return pa
    contracts = sorted({str(r.get("identity_contract_id") or "") for _s, r, _h in valid if r.get("identity_contract_id")})
    if ctx_contract_id and contracts and ctx_contract_id not in contracts:
        pa.status = "MISMATCH"
        pa.mismatch_reason = f"CONTRACT_MISMATCH:provenance={','.join(contracts)}:context={ctx_contract_id}"
        pa.integrity_valid, pa.association_valid = "YES", "NO"
        pa.recovered_from = ",".join(sorted({s for s, _r, _h in valid}))
        return pa
    pa.status = "VALID"
    pa.records = [r for _s, r, _h in valid]
    pa.recovered_from = ",".join(sorted({s for s, _r, _h in valid}))
    pa.association_method = ",".join(sorted({h for _s, _r, h in valid}))
    pa.integrity_valid = "YES"
    pa.association_valid = "YES"
    pa.aivsb_composed = any(bool(r.get("aivsb_composed")) for r in pa.records)
    pa.novel_ids = sorted({str(r.get("novel_id") or "") for r in pa.records if r.get("novel_id")})
    pa.character_ids = chars
    pa.depicted_character_ids = _ordered_keys(k for r in pa.records for k in (r.get("depicted_character_ids") or []))
    pa.drift = bool(pa.aivsb_composed and pa.detector != "STRICT_MATCH")
    return pa


# ---------------------------------------------------------------------------------------------
# publish eligibility (Phase 8). Prompt provenance NEVER counts as image approval: it can only block.
# Approval is the identity record / prior human review bound to the image bytes + character +
# contract version (tools.identity_preservation).
# ---------------------------------------------------------------------------------------------
_PUBLISH_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def _load_publish_metadata(folder: Any = None, metadata: Any = None, image_path: Any = None) -> Dict[str, Any]:
    """Best-effort metadata for a publish slot (explicit dict, folder/metadata.json, or image parent)."""
    if isinstance(metadata, Mapping):
        return dict(metadata)
    candidates: List[Path] = []
    if folder:
        candidates.append(Path(str(folder)))
    if image_path:
        try:
            candidates.append(Path(str(image_path)).resolve().parent)
        except Exception:  # noqa: BLE001
            candidates.append(Path(str(image_path)).parent)
    for base in candidates:
        meta_path = base / "metadata.json"
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, Mapping):
                return dict(data)
    return {}


def _publish_slot_governed_keys(
    *,
    metadata: Mapping[str, Any],
    novel_id: Any = None,
    character_ids: Any = None,
    image_path: Any = None,
    provenance: Any = None,
) -> Tuple[List[str], Optional[str], bool]:
    """Return (character_keys, novel_id, scenery_qualified).

    scenery_qualified=True only when structured/non-character intent is explicit and no
    governed character keys are present (existing qualified scenery policy).
    """
    ip = _ip()
    meta_novel = novel_id or metadata.get("abbr") or metadata.get("novel") or metadata.get("novel_id") or ""
    nid = ip.resolve_production_novel_alias(meta_novel) or (
        str(meta_novel).strip().casefold() if str(meta_novel).strip() else None
    )
    keys: List[str] = []
    for raw in list(character_ids or []) + list(metadata.get("character_ids") or []) + list(
        metadata.get("depicted_character_ids") or []
    ):
        k = ip.normalize_identity_character_key(raw)
        if k and k not in keys:
            keys.append(k)
    if provenance and isinstance(provenance, Mapping):
        for raw in list(provenance.get("character_ids") or []) + list(provenance.get("depicted_character_ids") or []):
            k = ip.normalize_identity_character_key(raw)
            if k and k not in keys:
                keys.append(k)
        if provenance.get("novel_id") and not nid:
            nid = ip.resolve_production_novel_alias(provenance.get("novel_id")) or str(provenance.get("novel_id") or "").casefold()
    # Folder / filename cues for governed packs (hp-7, en-25-monday, HA_7_1.png, promo under campaigns).
    if not keys and not nid and image_path is not None:
        try:
            p = Path(str(image_path))
            stem = p.stem
            parent = p.parent.name
            m = re.match(r"^([A-Za-z]{2,3})[_-](\d+)", stem)
            if m:
                nid = ip.resolve_production_novel_alias(m.group(1)) or nid
            m2 = re.match(r"^([A-Za-z]{2,3})[_-](\d+)", parent)
            if m2:
                nid = ip.resolve_production_novel_alias(m2.group(1)) or nid
        except Exception:  # noqa: BLE001
            pass
    intent = str(metadata.get("image_intent") or metadata.get("intent_class") or "").strip().upper()
    scenery_classes = {"SCENERY_ONLY", "ENVIRONMENT_ONLY", "OBJECT_ONLY", "ABSTRACT"}
    scenery_qualified = intent in scenery_classes and not keys
    if provenance and isinstance(provenance, Mapping):
        if provenance.get("aivsb_composed") or provenance.get("governed_context_present") or list(provenance.get("character_ids") or []):
            scenery_qualified = False
    if scenery_qualified:
        return [], nid, True
    if not keys and nid and nid in getattr(ip, "GOVERNED_NOVEL_IDS", ()):
        # Governed novel slot with no explicit character: treat novel protagonists as required
        # approval targets (publish must not auto-accept a blank legacy image in that slot).
        keys = list(ip.governed_character_keys_for_novel(nid))
    return keys, nid, False


def _prior_ok_for_chars(ip: Any, prior_list: List[Dict[str, Any]], sha: str, chars: List[str]) -> bool:
    if not chars:
        return False
    return all(
        any(ip.prior_review_record_compatibility(r, image_sha256=sha, character_id=k)[0] for r in prior_list)
        for k in chars
    )


def publish_identity_check(
    path: Any,
    *,
    folder: Any = None,
    metadata: Any = None,
    novel_id: Any = None,
    character_ids: Any = None,
) -> Tuple[bool, str]:
    """(ok, reason) for one publish candidate under identity enforcement (flag ON callers only).

    Mandatory final publish authorization boundary:
    - Quarantined review images are rejected.
    - Identity records for THESE bytes that did not allow auto-accept are rejected.
    - Unreadable / tampered image provenance is rejected.
    - Governed or AIVSB-composed provenance without identity acceptance (or approved prior
      human review bound to exact image SHA-256 + character ID + contract) is rejected.
    - Governed-character publish slots (novel/character context from kwargs, folder metadata,
      or provenance) with missing / ambiguous provenance or review FAIL CLOSED — never
      auto-accept because a sidecar is missing (LEGACY_MISSING_RECORD_AUTOACCEPT=NO).
    - Prompt provenance alone is NEVER image approval.
    - Verified non-character scenery may follow the existing qualified intent policy.
    """
    ip = _ip()
    p = Path(str(path))
    if p.suffix.lower() not in _PUBLISH_IMAGE_SUFFIXES:
        return True, ""
    if ip._QUARANTINE_TAG_RE.search(p.name):
        return False, "QUARANTINED_IDENTITY_REVIEW_IMAGE"
    if not p.exists():
        return False, "PUBLISH_IMAGE_MISSING"
    sha = _sha256_file(p)
    accepted_for_bytes = False
    side = p.with_name(p.name + ".identity_preservation.json")
    if side.exists():
        try:
            rec = json.loads(side.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return False, "IDENTITY_RECORD_UNREADABLE"
        if isinstance(rec, Mapping) and str(rec.get("IMAGE_SHA256") or "") == sha:
            if str(rec.get("AUTO_ACCEPT_ALLOWED")) != "YES":
                return False, "IDENTITY_RECORD_FOR_THESE_BYTES_NOT_ACCEPTED"
            accepted_for_bytes = True
        elif isinstance(rec, Mapping) and str(rec.get("IMAGE_SHA256") or "") and str(rec.get("IMAGE_SHA256") or "") != sha:
            return False, "IDENTITY_RECORD_SHA256_MISMATCH"
    prior_list: List[Dict[str, Any]] = []
    try:
        prior_list = ip.load_prior_review_records(None, p)
    except Exception:  # noqa: BLE001
        prior_list = []
    prec, st = read_image_provenance(p, sha)
    if st in ("MALFORMED", "BINDING_HASH_MISMATCH", "STALE_IMAGE_SHA"):
        return False, f"IMAGE_PROVENANCE_{st}"
    meta = _load_publish_metadata(folder=folder, metadata=metadata, image_path=p)
    slot_chars, slot_novel, scenery_qualified = _publish_slot_governed_keys(
        metadata=meta, novel_id=novel_id, character_ids=character_ids, image_path=p, provenance=prec
    )
    if prec is not None:
        ok, why = validate_record(prec)
        if not ok:
            return False, f"IMAGE_PROVENANCE_INVALID:{why}"
        chars = [str(k) for k in (prec.get("character_ids") or [])] or list(slot_chars)
        prior_ok = _prior_ok_for_chars(ip, prior_list, sha, chars)
        if (prec.get("aivsb_composed") or prec.get("governed_context_present") or bool(chars)) and not (
            accepted_for_bytes or prior_ok
        ):
            return False, "GOVERNED_PROVENANCE_WITHOUT_IDENTITY_APPROVAL_FOR_THESE_BYTES"
        if accepted_for_bytes or prior_ok:
            return True, ""
        if scenery_qualified:
            return True, ""
        if slot_chars or (slot_novel and slot_novel in getattr(ip, "GOVERNED_NOVEL_IDS", ())):
            return False, "GOVERNED_PUBLISH_SLOT_WITHOUT_IDENTITY_APPROVAL_FOR_THESE_BYTES"
        return True, ""
    # No image provenance sidecar/record.
    prior_ok = _prior_ok_for_chars(ip, prior_list, sha, slot_chars)
    if accepted_for_bytes or prior_ok:
        return True, ""
    if scenery_qualified:
        return True, ""
    if slot_chars or (slot_novel and slot_novel in getattr(ip, "GOVERNED_NOVEL_IDS", ())):
        # LEGACY_MISSING_RECORD_AUTOACCEPT=NO: missing sidecar/record in a governed slot => review.
        return False, "GOVERNED_PUBLISH_SLOT_MISSING_IDENTITY_APPROVAL"
    # No governed context resolvable from path/metadata: not a governed publish slot.
    return True, ""
