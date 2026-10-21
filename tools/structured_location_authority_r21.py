"""SCENE_ENVIRONMENT_STRUCTURED_LOCATION_AUTHORITY_R21 (shadow only; imported by no live path).

Positive scene location comes ONLY from a structured tag (scene / chapter metadata or explicit user
direction) whose BEAT_TEXT_SHA256 matches the current beat text and whose LOCATION_ID resolves to a governed
Studio Bible location of the SAME novel. There is no prose fallback. The R20 parser is suppression-only and is
loaded lazily, only after a tag has validated. Authority: text canon > structured metadata > Studio Bible
identity > parser consistency check > prompt prose.

Resolution order (Phase 16): hash -> novel -> resolve id -> same novel -> SceneEnvironmentSpec -> parser
(optional) -> final LOCATION_ROLE handed to R12.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional

MODULE_VERSION = "R21.4"
SHADOW_MODE = True
PRODUCTION_CUTOVER = False
PARSER_MODE = "SUPPRESSION_ONLY"
PARSER_CREATES_POSITIVE_BIND = False
ALLOWED_SOURCES = frozenset({"SCENE_METADATA", "CHAPTER_METADATA", "EXPLICIT_USER_DIRECTION"})
REASONS = ("STRUCTURED_BIND", "MISSING_METADATA", "HASH_MISMATCH", "UNRESOLVED_ID", "NOVEL_MISMATCH", "CONTRADICTORY")
PARSER_RESULTS = ("CONSISTENT", "CONTRADICTORY", "AMBIGUOUS", "UNKNOWN")
AUTHORITY_ORDER = ("TEXT_CANON", "STRUCTURED_SCENE_CHAPTER_METADATA", "STUDIO_BIBLE_LOCATION_IDENTITY",
                   "PARSER_CONSISTENCY_CHECK", "PROMPT_PROSE")
DEFAULT_LOCATIONS_YAML = os.path.join(os.path.expanduser("~"), "Documents", "Inkblade Author Studio", "scripts",
                                      "aivsb", "locations", "locations.yaml")
STATS = {"PARSER_CALLS": 0, "DECISIONS": 0, "PARSER_LOADS": 0}

_LEAVE_ROLES = frozenset({"SOURCE", "DEPARTED"})
_FAIL_ROLES = frozenset({"FAILED_DESTINATION"})
_CURRENT_ROLES = frozenset({"CURRENT_SITE", "SUCCESSFUL_DESTINATION"})
_STATIVE = frozenset("at on in inside within by beside near".split())
_STOP = frozenset("the a an of and + one room one-room".split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _file_sha(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------- governed Studio Bible locations (read-only)
def load_governed_locations(path: str = DEFAULT_LOCATIONS_YAML) -> Dict[str, Dict[str, Any]]:
    import yaml  # read-only load
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    items = data.get("locations", data) if isinstance(data, dict) else data
    out: Dict[str, Dict[str, Any]] = {}
    for loc in items or []:
        if isinstance(loc, dict) and loc.get("id"):
            out[str(loc["id"])] = {"id": str(loc["id"]), "novel": str(loc.get("novel") or "").upper(),
                                   "name": str(loc.get("name") or ""), "record": loc}
    return out


def location_terms(name: str) -> Dict[str, Any]:
    """Identity terms for a GOVERNED location name (used only to recognise mentions of an already-structured
    or governed location for the consistency check; never to create a location)."""
    base = re.sub(r"\([^)]*\)", " ", name.lower())
    heads, phrases = set(), set()
    for seg in re.split(r"\+|,", base):
        words = [w for w in re.findall(r"[a-z][a-z\-]*", seg) if w not in _STOP and not w.endswith("'s")]
        if words:
            heads.add(words[-1])
            phrases.add(" ".join(words))
    return {"heads": heads, "phrases": phrases}


def _mentions(rec: Dict[str, Any], terms: Dict[str, Any]) -> bool:
    head = str(rec.get("HEAD") or "").lower()
    canon = str(rec.get("CANONICAL_LOCATION") or rec.get("LOCATION_MENTION") or "").lower()
    return head in terms["heads"] or any(p and p in canon for p in terms["phrases"])


# ---------------------------------------------------------------- authority flags
SHADOW_PENDING_LOCATION_AUTHORITY = "NO"   # pending allowlist removed; locations.yaml is the only authority
STUDIO_BIBLE_LOCATION_AUTHORITY = "YES"
BEAT_HASH_BINDING = "YES"                  # BEAT_TEXT_SHA256 is the bind key; SOURCE_SHA256 is provenance only
NOT_EVALUATED = "NOT_EVALUATED_NO_CHARACTER_CONTEXT"
# R21 CORE vs deferred suppression layer (David, Option 2). The core resolve path never runs the parser.
PARSER_SUPPRESSION_PRODUCTION_ENABLED = "NO"
PARSER_SUPPRESSION_QUALIFIED = "NO"
PARSER_SUPPRESSION_BLOCK_REASON = "NO_GOVERNED_PER_BEAT_DEPICTED_CHARACTER_SOURCE"
# Tags whose provenance names a parser/model/prose producer are not structured metadata.
_PARSER_TAGGERS = frozenset({"PARSER", "SPACY", "PROSE", "MODEL", "R15", "R16", "R17", "R18", "R19", "R20", "AUTO"})
# R12 single bind decision point (tools/location_relation_r6.py _BIND_ROLES, read-only reference).
R12_BIND_ROLES = frozenset({"CURRENT_SITE", "SUCCESSFUL_DESTINATION"})
# Governed depicted-character context sources (never spaCy / parser / name guessing / location tags).
ALLOWED_DEPICTED_SOURCES = frozenset({"IDENTITY_PRESERVATION_STRUCTURED_CONTEXT",
                                      "VISUAL_DIRECTOR_UPSTREAM_DEPICTED_CHARACTERS", "EXPLICIT_USER_DIRECTION"})


_CAST_CACHE: Dict[str, Any] = {}
STATS.setdefault("CAST_LOADS", 0)


def _governed_cast(nov: str) -> Dict[str, Any]:
    """Governed identity cast for a novel, loaded ONCE per process/job (tools.identity_preservation, read-only)."""
    if "IP" not in _CAST_CACHE:
        from tools import identity_preservation as IP  # no spaCy
        STATS["CAST_LOADS"] += 1
        alias = dict(getattr(IP, "_ALIAS_INDEX", {}) or {})
        cast = {k: tuple(v) for k, v in (getattr(IP, "GOVERNED_NOVEL_CAST", {}) or {}).items()}
        keys = {n: set(IP.governed_character_keys_for_novel(n)) for n in cast}
        _CAST_CACHE["IP"] = (cast, keys, alias)
    cast, keys, alias = _CAST_CACHE["IP"]
    return {"names": {str(x).casefold(): str(x) for x in cast.get(nov, ())}, "keys": keys.get(nov, set()), "alias": alias}


def validate_depicted_context(novel_id: str, ids: Optional[Iterable[Any]], source: str) -> Dict[str, Any]:
    """Validate depicted ids against the governed identity cast of the SAME novel. Ids must be canonical governed
    keys or exact governed cast names (no aliases, no pronouns, no cross-novel mapping); any invalid id is OMITTED.
    Subject matching inside the parse uses only identity authority's own explicit alias index for valid keys."""
    out = {"VALID": False, "KEYS": [], "SURFACE": [], "OMITTED": [], "REASON": ""}
    raw = [str(x or "").strip() for x in (ids or []) if str(x or "").strip()]
    if str(source or "") not in ALLOWED_DEPICTED_SOURCES:
        out["REASON"] = "UNGOVERNED_DEPICTED_SOURCE"; return out
    g = _governed_cast(novel_id.lower())
    keys, surface = [], set()
    for r in raw:
        if r in g["keys"]:
            keys.append(r); surface.add(r.replace("_", " "))
            surface.update(a for a, v in g["alias"].items() if v == r)
        else:
            out["OMITTED"].append(r)
    if not keys:
        out["REASON"] = "NO_VALID_GOVERNED_DEPICTED_ID"; return out
    out.update(VALID=True, KEYS=sorted(set(keys)), SURFACE=sorted({x.casefold() for x in surface}))
    return out


def load_character_context_store(path: Optional[str]) -> List[Dict[str, Any]]:
    """Hash-bound per-beat depicted-character context rows: NOVEL_ID, CHAPTER_ID, BEAT_INDEX, BEAT_TEXT_SHA256,
    DEPICTED_CHARACTER_IDS (list), DEPICTED_CHARACTER_SOURCE. Shadow only."""
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("contexts", []) if isinstance(data, dict) else data
    return [r for r in rows or [] if isinstance(r, dict)]


def character_context_for(beat: Dict[str, Any], contexts: List[Dict[str, Any]], cur_sha: str) -> Dict[str, Any]:
    nov, ch, bi = str(beat.get("novel_id") or "").upper(), str(beat.get("chapter_id") or ""), int(beat.get("beat_index", 0) or 0)
    rows = [r for r in contexts if str(r.get("NOVEL_ID", "")).upper() == nov and str(r.get("CHAPTER_ID")) == ch
            and str(r.get("BEAT_INDEX")) == str(bi)]
    if not rows:
        return {"FOUND": False, "STALE": False}
    r = rows[0]
    if str(r.get("BEAT_TEXT_SHA256") or "") != cur_sha:
        return {"FOUND": True, "STALE": True}
    return {"FOUND": True, "STALE": False, "IDS": list(r.get("DEPICTED_CHARACTER_IDS") or []),
            "SOURCE": str(r.get("DEPICTED_CHARACTER_SOURCE") or "")}


# ---------------------------------------------------------------- tagged-location contradiction check (single parse)
_LEAVE = frozenset({"leave"})
_EXIT_VERBS = frozenset({"exit", "depart", "abandon", "vacate", "flee", "evacuate", "quit"})
_OUT_MOTION = frozenset({"walk", "run", "step", "go", "come", "move", "flee", "hurry", "rush", "stagger", "limp", "slip",
                         "burst", "storm", "march", "crawl", "emerge", "escape", "retreat", "back", "stumble", "drive", "ride"})
_REACH = frozenset({"reach", "arrive", "enter", "get", "make"})
_RETURN = frozenset({"return"})
_PRESENT = frozenset({"be", "stay", "remain", "stand", "sit", "wait", "live"})
_STATIVE_PP = frozenset({"at", "in", "inside", "within"})
_MODAL = frozenset({"will", "would", "might", "may", "could", "should", "must", "can", "shall", "'ll", "wo"})
_IRREALIS_HEADS = frozenset({"try", "want", "plan", "intend", "hope", "decide", "need", "wish", "mean", "refuse", "prepare", "agree", "begin", "start"})


def _neg(v) -> bool:
    return any(c.dep_ == "neg" for c in v.children)


def _subject_text(v) -> str:
    cur = v
    for _ in range(4):
        subj = [c for c in cur.children if c.dep_ in ("nsubj", "nsubjpass")]
        if subj:
            s = subj[0]
            comp = [c.text for c in s.children if c.dep_ == "compound"]
            return " ".join(comp + [s.text]).casefold()
        if cur.dep_ in ("conj", "xcomp", "advcl") and cur.head is not cur:
            cur = cur.head
        else:
            break
    return ""


def _irrealis(v) -> bool:
    if any(c.dep_ in ("aux", "auxpass") and c.lower_ in _MODAL for c in v.children):
        return True
    if any(c.dep_ == "mark" and c.lower_ in ("if", "unless", "before") for c in v.children):
        return True
    if v.dep_ == "xcomp" and v.head.lemma_.lower() in _IRREALIS_HEADS:
        return True
    return False


def _is_x(tok, heads) -> bool:
    return tok.pos_ in ("NOUN", "PROPN") and tok.lemma_.lower() in heads or tok.lower_ in heads


def tagged_location_contradiction(doc, location_name: str, depicted_surface: Iterable[str]) -> Dict[str, Any]:
    """Explicit non-current relation of a DEPICTED character to the TAGGED location X, read from the existing parse.
    Never searches for or returns another location."""
    heads = location_terms(location_name)["heads"]
    dep = {d.casefold() for d in depicted_surface}
    hits: List[Dict[str, Any]] = []
    if doc is None or not heads or not dep:
        return {"CONTRADICTED": False, "HITS": hits, "CANCELLED_BY_RETURN": []}
    for t in doc:
        if not _is_x(t, heads):
            continue
        rel, v = None, None
        if t.dep_ == "dobj":
            v = t.head
            lem = v.lemma_.lower()
            if lem in _LEAVE and not _neg(v) and not any(c.dep_ in ("oprd", "acomp", "ccomp") or (c.dep_ == "xcomp" and c.pos_ == "ADJ")
                                                     for c in v.children):
                rel = "LEFT"
            elif lem in _EXIT_VERBS and not _neg(v):
                rel = "DEPARTED"
            elif lem in _REACH and _neg(v):
                rel = "FAILED_TO_REACH"
            elif lem in _REACH and v.dep_ == "xcomp" and v.head.lemma_.lower() == "fail":
                rel = "FAILED_TO_REACH"
        elif t.dep_ == "pobj":
            pp = t.head
            v = pp.head
            if pp.lower_ == "of" and v.lower_ == "out" and v.dep_ in ("prep", "prt", "advmod"):
                v = v.head
                if v.lemma_.lower() in _OUT_MOTION and not _neg(v):
                    rel = "DEPARTED"
            elif pp.lower_ == "from" and v.lemma_.lower() in _OUT_MOTION | _EXIT_VERBS and not _neg(v):
                rel = "DEPARTED"
            elif pp.lower_ in _STATIVE_PP and v.lemma_.lower() in _PRESENT:
                longer = [c for c in v.children if c.dep_ == "advmod" and c.lower_ == "longer"]
                if longer and (_neg(v) or any(c.lower_ == "no" for c in longer[0].children) or
                               any(c.lower_ == "no" and c.dep_ == "neg" for c in v.children)):
                    rel = "NO_LONGER_PRESENT"
                elif _neg(v):
                    rel = "EXPLICITLY_NOT_AT"
            elif pp.lower_ in ("at", "in", "into") and v.lemma_.lower() in _REACH and _neg(v):
                rel = "FAILED_TO_REACH"
        if not rel or v is None or _irrealis(v):
            continue
        subj = _subject_text(v)
        if not subj or subj not in dep and subj.split()[-1] not in dep:
            continue
        hits.append({"RELATION": rel, "VERB": v.lemma_, "SUBJECT": subj, "I": v.i, "LOCATION_TOKEN": t.text})
    cancelled = []
    for h in hits:
        for v in doc:
            if v.i <= h["I"] or v.pos_ not in ("VERB", "AUX") or _neg(v) or _irrealis(v):
                continue
            s2 = _subject_text(v)
            if s2 and s2 != h["SUBJECT"] and s2.split()[-1] not in dep:
                continue
            lem = v.lemma_.lower()
            back = any(c.lower_ == "back" for c in v.children)
            objs = [c for c in v.children if c.dep_ == "dobj"] + [g for c in v.children if c.dep_ == "prep" for g in c.children if g.dep_ == "pobj"]
            to_x = any(_is_x(o, heads) for o in objs)
            other_dest = any(c.dep_ == "prep" and c.lower_ in ("to", "into", "toward", "towards") and
                             any(not _is_x(g, heads) for g in c.children if g.dep_ == "pobj") for c in v.children)
            if (lem in _RETURN or back) and not other_dest or (lem in _REACH | {"enter"} and to_x) or                     (lem in _PRESENT and to_x and not _neg(v)):
                cancelled.append({**h, "CANCELLED_BY": v.lemma_, "AT": v.i}); break
    live = [h for h in hits if not any(c["I"] == h["I"] for c in cancelled)]
    return {"CONTRADICTED": bool(live), "HITS": live, "CANCELLED_BY_RETURN": cancelled}


# ---------------------------------------------------------------- tag store
def load_tag_store(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tags = data.get("tags", []) if isinstance(data, dict) else data
    return [t for t in tags or [] if isinstance(t, dict)]


def _tags_for(tags: List[Dict[str, Any]], novel_id: str, chapter_id: str, beat_index: int) -> List[Dict[str, Any]]:
    out = []
    for t in tags:
        if str(t.get("CHAPTER_ID", "")) != str(chapter_id):
            continue
        bi = t.get("BEAT_INDEX")
        if str(t.get("LOCATION_SOURCE", "")).upper() == "CHAPTER_METADATA" and bi in (None, "", "*"):
            out.append(t)
        elif bi not in (None, "", "*") and int(bi) == int(beat_index):
            out.append(t)
    return out


# ---------------------------------------------------------------- parser (lazy, suppression-only)
def _default_parser(text: str, depicted: Optional[List[str]]) -> Dict[str, Any]:
    STATS["PARSER_LOADS"] += 1
    from tools import place_detection_r20 as R20  # lazy: spaCy loads only here
    from tools import semantic_event_parser_r16 as R16
    out = R20.analyze(text, depicted_characters=depicted)
    out["_doc"] = R16._DOC_CACHE.get(text)  # the same Doc; never re-parsed
    return out


def parser_consistency(records: Iterable[Dict[str, Any]], location_id: str, governed: Dict[str, Dict[str, Any]],
                       novel_id: str, depicted: Optional[List[str]]) -> Dict[str, Any]:
    """Classify parser records against the structured location X. Never returns a location."""
    x_terms = location_terms(governed[location_id]["name"])
    others = {lid: location_terms(g["name"]) for lid, g in governed.items()
              if lid != location_id and g["novel"] == novel_id}
    dep = {d.lower() for d in depicted} if depicted is not None else None
    contra, consistent, ambiguous, ignored_cross_subject = [], [], [], []
    for r in records or []:
        hit_x = _mentions(r, x_terms)
        hit_y = [lid for lid, t in others.items() if _mentions(r, t)]
        if not hit_x and not hit_y:
            continue
        sid = str(r.get("SUBJECT_CHARACTER_ID") or "").lower()
        high = r.get("PARSER_CONFIDENCE_CLASS") == "STRUCTURAL_HIGH" and r.get("CLAUSE_REALIS", True) is not False
        depicted_subject = bool(dep is not None and sid and sid in dep and r.get("SUBJECT_IS_DEPICTED", True) is not False)
        role = str(r.get("LOCATION_ROLE") or "")
        cue = None
        if hit_x and (role in _LEAVE_ROLES or r.get("EVENT_STATE") == "DEPARTED"):
            cue = "LEFT_X"
        elif hit_x and (role in _FAIL_ROLES or r.get("EVENT_STATE") == "FAILED"):
            cue = "FAILED_TO_REACH_X"
        elif hit_x and r.get("NEGATED") and str(r.get("PREPOSITION") or "").lower() in _STATIVE:
            cue = "EXPLICITLY_NOT_AT_X"
        elif hit_y and not hit_x and role in _CURRENT_ROLES and r.get("FINAL_BIND_ALLOWED") is True:
            cue = "OTHER_GOVERNED_LOCATION_CURRENT:" + hit_y[0]
        ev = {"HEAD": r.get("HEAD"), "ROLE": role, "SUBJECT": sid, "CUE": cue}
        if cue:
            if high and depicted_subject:
                contra.append(ev)
            elif sid and dep is not None and sid not in dep:
                ignored_cross_subject.append(ev)  # no cross-subject leak
            else:
                ambiguous.append(ev)
        elif hit_x and role in _CURRENT_ROLES and depicted_subject:
            consistent.append(ev)
        else:
            ambiguous.append(ev)
    if contra and consistent:
        result = "AMBIGUOUS"  # conflicting evidence never suppresses
    elif contra:
        result = "CONTRADICTORY"
    elif consistent:
        result = "CONSISTENT"
    elif ambiguous or ignored_cross_subject:
        result = "AMBIGUOUS"
    else:
        result = "UNKNOWN"
    return {"PARSER_CONSISTENCY": result, "CONTRADICTION_EVIDENCE": contra, "CONSISTENT_EVIDENCE": consistent,
            "AMBIGUOUS_EVIDENCE": ambiguous, "CROSS_SUBJECT_IGNORED": ignored_cross_subject}


def _scene_spec(novel_id: str, loc: Dict[str, Any], beat_index: int) -> Dict[str, Any]:
    try:
        from tools.scene_environment import SceneEnvironmentSpec  # read-only use of the dataclass
        rec = loc["record"]
        spec = SceneEnvironmentSpec(novel=novel_id.lower(), location_id=loc["id"], location_name=loc["name"],
                                    authority="STRUCTURED_METADATA_R21", architecture=str(rec.get("architecture", "")),
                                    lighting=str(rec.get("lighting", "")), weather=str(rec.get("weather", "")),
                                    damage_state=str(rec.get("damage_state", "")), still_index=int(beat_index),
                                    unknown_location=False)
        return {"BUILT": True, "SPEC": spec.to_dict()}
    except Exception as exc:  # pragma: no cover - reported, never silently bound
        return {"BUILT": False, "ERROR": repr(exc)}


# ---------------------------------------------------------------- decision
def decide(beat: Dict[str, Any], tag_store_path: Optional[str] = None, *, governed: Optional[Dict[str, Dict[str, Any]]] = None,
           locations_yaml: str = DEFAULT_LOCATIONS_YAML, run_parser: bool = False,
           parser: Optional[Callable[[str, Optional[List[str]]], Dict[str, Any]]] = None,
           tags: Optional[List[Dict[str, Any]]] = None,
           character_contexts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    STATS["DECISIONS"] += 1
    novel_id = str(beat.get("novel_id") or beat.get("NOVEL_ID") or "").upper()
    chapter_id = str(beat.get("chapter_id") or beat.get("CHAPTER_ID") or "")
    beat_index = int(beat.get("beat_index", beat.get("still_index", beat.get("BEAT_INDEX", 0))) or 0)
    text = str(beat.get("beat_text") or beat.get("BEAT_TEXT") or "")
    depicted = None  # set only from validated governed context below
    if governed is None:
        governed = load_governed_locations(locations_yaml)
    if tags is None:
        tags = load_tag_store(tag_store_path)
    cur_sha = sha256_text(text)
    prov: Dict[str, Any] = {
        "DECISION_ID": uuid.uuid4().hex, "MODULE_VERSION": MODULE_VERSION, "SHADOW_MODE": True, "PRODUCTION_CUTOVER": False,
        "NOVEL_ID": novel_id, "CHAPTER_ID": chapter_id, "BEAT_INDEX": beat_index, "BEAT_TEXT_SHA256": cur_sha,
        "TAG_FOUND": False, "TAG_BEAT_TEXT_SHA256": "", "LOCATION_ID": "", "LOCATION_SOURCE": "", "TAGGED_BY": "",
        "SOURCE_RECORD_ID": "", "SOURCE_VERSION": "", "SOURCE_SHA256": "", "TAG_VALID": "NO",
        "STRUCTURED_LOCATION_TAG_VALID": "NO", "STUDIO_BIBLE_LOCATION_ID": "", "STUDIO_BIBLE_LOCATION_NAME": "",
        "STUDIO_BIBLE_LOCATION_NOVEL": "", "SCENE_ENVIRONMENT_SPEC_BUILT": False, "SUPPRESSION_PARSER_RUN": "NO",
        "PARSER_VERSION": "", "PARSER_CONSISTENCY": "NOT_RUN", "PARSER_EVIDENCE": {}, "SUPPRESSED_BY_PARSER": False,
        "FINAL_LOCATION_BIND": "NO", "FINAL_LOCATION_ID": "", "FINAL_LOCATION_REASON": "", "FINAL_LOCATION_ROLE": "UNKNOWN",
        "PROSE_FALLBACK_USED": False, "NOTE": "", "SOURCE_SHA256_MATCH": "", "SOURCE_SCOPE": "",
        "CHAPTER_SOURCE_SHA256": str(beat.get("chapter_text_sha256") or ""), "BEAT_HASH_BINDING": BEAT_HASH_BINDING,
        "SHADOW_PENDING_LOCATION_AUTHORITY": SHADOW_PENDING_LOCATION_AUTHORITY,
        "STUDIO_BIBLE_LOCATION_AUTHORITY": STUDIO_BIBLE_LOCATION_AUTHORITY, "LEGACY_PROSE_MATCH": None,
        "DEPICTED_CHARACTER_IDS": list(beat.get("depicted_character_ids") or []),
        "DEPICTED_CHARACTER_SOURCE": str(beat.get("depicted_character_source") or ""),
        "DEPICTED_CONTEXT_VALID": False, "DEPICTED_CONTEXT_REASON": "", "SUBJECT_GATE_RUN": False,
        "CHARACTER_CONTEXT_FOUND": False, "CHARACTER_CONTEXT_STALE": False, "DEPICTED_IDS_OMITTED": [],
        "SPACY_PARSE_COUNT": 0, "CLAUSE_REPARSE_COUNT": 0, "PARSER_CREATED_LOCATION": False, 
        "AUTHORITY_ORDER": list(AUTHORITY_ORDER), "LOCATIONS_YAML_SHA256": _file_sha(locations_yaml) if locations_yaml else "",
        "TAG_STORE_PATH": tag_store_path or "", "TAG_STORE_SHA256": _file_sha(tag_store_path) if tag_store_path else "",
        "TIMING_MS": {}}

    def finish(reason: str, bind: bool = False) -> Dict[str, Any]:
        prov["FINAL_LOCATION_REASON"] = reason
        prov["FINAL_LOCATION_BIND"] = "YES" if bind else "NO"
        prov["FINAL_LOCATION_ID"] = prov["STUDIO_BIBLE_LOCATION_ID"] if bind else ""
        prov["FINAL_LOCATION_ROLE"] = "CURRENT_SITE" if bind else "UNKNOWN"  # handed to R12
        prov["R12_BIND_ALLOWED"] = prov["FINAL_LOCATION_ROLE"] in R12_BIND_ROLES
        if bind and not prov["R12_BIND_ALLOWED"]:  # R12 is the single decision point; never bypassed
            prov["FINAL_LOCATION_BIND"], prov["FINAL_LOCATION_ID"] = "NO", ""
        prov["TIMING_MS"]["TOTAL_MS"] = (time.perf_counter() - t0) * 1000
        return prov

    cands = [t for t in _tags_for(tags, novel_id, chapter_id, beat_index)
             if str(t.get("LOCATION_SOURCE", "")).upper() in ALLOWED_SOURCES and str(t.get("LOCATION_ID") or "").strip()
             and str(t.get("TAGGED_BY") or "").upper() not in _PARSER_TAGGERS]
    if not cands:
        return finish("MISSING_METADATA")
    prov["TAG_FOUND"] = True
    if len({str(t["LOCATION_ID"]) for t in cands}) > 1:
        prov["LOCATION_ID"] = "|".join(sorted({str(t["LOCATION_ID"]) for t in cands}))
        return finish("CONTRADICTORY")  # authority conflict between structured sources: fail closed, never pick
    tag = sorted(cands, key=lambda t: 0 if str(t.get("LOCATION_SOURCE")).upper() != "CHAPTER_METADATA" else 1)[0]
    for k in ("LOCATION_ID", "LOCATION_SOURCE", "TAGGED_BY", "SOURCE_RECORD_ID", "SOURCE_VERSION", "SOURCE_SHA256"):
        prov[k] = str(tag.get(k) or "")
    prov["LOCATION_SOURCE"] = prov["LOCATION_SOURCE"].upper()
    prov["TAG_BEAT_TEXT_SHA256"] = str(tag.get("BEAT_TEXT_SHA256") or "")
    prov["NOTE"] = str(tag.get("NOTE") or "")  # carried for provenance only; never used for binding
    # 1 hash (never remap)
    if prov["LOCATION_SOURCE"] == "CHAPTER_METADATA" and tag.get("BEAT_INDEX") in (None, "", "*"):
        ok = bool(beat.get("chapter_text_sha256")) and str(tag.get("SOURCE_SHA256") or "") == str(beat.get("chapter_text_sha256"))
    else:
        ok = prov["TAG_BEAT_TEXT_SHA256"] == cur_sha
    if not ok:
        return finish("HASH_MISMATCH")
    # SOURCE_SHA256 is provenance only (never a rejection reason)
    ssha, ch_sha = prov["SOURCE_SHA256"], str(beat.get("chapter_text_sha256") or "")
    prov["SOURCE_SHA256_MATCH"] = "BEAT_TEXT" if ssha and ssha == cur_sha else ("CHAPTER_SOURCE" if ssha and ssha == ch_sha else "UNVERIFIED")
    prov["SOURCE_SCOPE"] = str(tag.get("SOURCE_SCOPE") or {"BEAT_TEXT": "BEAT", "CHAPTER_SOURCE": "CHAPTER"}.get(prov["SOURCE_SHA256_MATCH"], "UNSPECIFIED"))
    if not prov["SOURCE_RECORD_ID"]:
        prov["SOURCE_RECORD_ID"] = f"{chapter_id}#{beat_index}"
    # 2 novel
    if str(tag.get("NOVEL_ID") or "").upper() != novel_id:
        return finish("NOVEL_MISMATCH")
    # 3 resolve id
    loc = governed.get(prov["LOCATION_ID"]) if re.fullmatch(r"[a-z0-9_]+", prov["LOCATION_ID"]) else None
    if loc is None:
        return finish("UNRESOLVED_ID")
    # 4 same novel
    prov["STUDIO_BIBLE_LOCATION_NOVEL"] = loc["novel"]
    if loc["novel"] != novel_id:
        return finish("NOVEL_MISMATCH")
    prov["TAG_VALID"] = prov["STRUCTURED_LOCATION_TAG_VALID"] = "YES"
    prov["STUDIO_BIBLE_LOCATION_ID"], prov["STUDIO_BIBLE_LOCATION_NAME"] = loc["id"], loc["name"]
    prov["LEGACY_PROSE_MATCH"] = loc["record"].get("legacy_prose_match", True) is not False
    # 5 SceneEnvironmentSpec
    t1 = time.perf_counter()
    spec = _scene_spec(novel_id, loc, beat_index)
    prov["SCENE_ENVIRONMENT_SPEC_BUILT"] = spec["BUILT"]
    prov["SCENE_ENVIRONMENT_SPEC"] = spec.get("SPEC") or spec
    prov["TIMING_MS"]["STRUCTURED_MS"] = (time.perf_counter() - t0) * 1000
    # 6 optional suppression-only parser
    if run_parser:
        t_cl = time.perf_counter()
        cc = character_context_for(beat, character_contexts or [], cur_sha) if character_contexts is not None else \
            ({"FOUND": True, "STALE": str(beat.get("depicted_context_beat_sha256") or cur_sha) != cur_sha,
              "IDS": beat.get("depicted_character_ids"), "SOURCE": str(beat.get("depicted_character_source") or "")}
             if beat.get("depicted_character_ids") is not None else {"FOUND": False, "STALE": False})
        prov["CHARACTER_CONTEXT_FOUND"], prov["CHARACTER_CONTEXT_STALE"] = cc["FOUND"], cc["STALE"]
        if cc["FOUND"] and not cc["STALE"]:
            dc = validate_depicted_context(novel_id, cc.get("IDS"), cc.get("SOURCE", ""))
            prov["DEPICTED_CHARACTER_IDS"], prov["DEPICTED_CHARACTER_SOURCE"] = list(cc.get("IDS") or []), cc.get("SOURCE", "")
        else:
            dc = {"VALID": False, "REASON": "STALE_CHARACTER_CONTEXT" if cc["STALE"] else "NO_CHARACTER_CONTEXT", "OMITTED": []}
        prov["TIMING_MS"]["CHARACTER_LOOKUP_MS"] = (time.perf_counter() - t_cl) * 1000
        prov["DEPICTED_CONTEXT_VALID"], prov["DEPICTED_CONTEXT_REASON"] = dc["VALID"], dc["REASON"]
        prov["DEPICTED_IDS_OMITTED"] = dc.get("OMITTED", [])
        if not dc["VALID"]:
            prov["PARSER_CONSISTENCY"] = NOT_EVALUATED
            return finish("STRUCTURED_BIND", bind=spec["BUILT"]) if spec["BUILT"] else finish("UNRESOLVED_ID")
        depicted = dc["SURFACE"]
        prov["SUBJECT_GATE_RUN"] = True
        t2 = time.perf_counter()
        STATS["PARSER_CALLS"] += 1
        prov["SUPPRESSION_PARSER_RUN"] = "YES"
        out = (parser or _default_parser)(text, list(depicted) if depicted is not None else None)
        prov["PARSER_VERSION"] = "R20" if parser is None else getattr(parser, "__name__", "injected")
        if not out.get("PARSER_AVAILABLE", True):
            pc = {"PARSER_CONSISTENCY": "UNKNOWN"}
        else:
            pc = parser_consistency(out.get("records", []), loc["id"], governed, novel_id, list(depicted) if depicted is not None else None)
        t3 = time.perf_counter()
        tc = tagged_location_contradiction(out.get("_doc"), loc["name"], depicted or [])
        prov["TIMING_MS"]["TAGGED_CONTRADICTION_MS"] = (time.perf_counter() - t3) * 1000
        pc["TAGGED_LOCATION_CHECK"] = tc
        if tc["CONTRADICTED"] and pc["PARSER_CONSISTENCY"] != "CONTRADICTORY":
            pc["PARSER_CONSISTENCY"] = "CONTRADICTORY"
            pc.setdefault("CONTRADICTION_EVIDENCE", []).extend(tc["HITS"])
        prov["SPACY_PARSE_COUNT"] = out.get("SPACY_PARSE_COUNT")
        prov["CLAUSE_REPARSE_COUNT"] = out.get("CLAUSE_REPARSE_COUNT")
        prov["PARSER_CONSISTENCY"] = pc["PARSER_CONSISTENCY"]
        prov["PARSER_EVIDENCE"] = {k: v for k, v in pc.items()}
        prov["TIMING_MS"]["PARSER_MS"] = (time.perf_counter() - t2) * 1000
        if pc["PARSER_CONSISTENCY"] == "CONTRADICTORY":
            prov["SUPPRESSED_BY_PARSER"] = True
            return finish("CONTRADICTORY")
    if not spec["BUILT"]:
        return finish("UNRESOLVED_ID")
    _ = t1
    return finish("STRUCTURED_BIND", bind=True)
