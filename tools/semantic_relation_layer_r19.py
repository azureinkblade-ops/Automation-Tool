"""SCENE_ENVIRONMENT_SEMANTIC_RELATION_LAYER_R19 (shadow only).

A semantic relation classification layer over the FROZEN R18 single-parse event graph.  R18 parses each
text once (spaCy) and builds the graph; R19 reads the SAME cached Doc (no second parse, no second model,
no embeddings) and classifies each subject-predicate-location relation into one of RELATION_CLASSES.
Classification may move a LOCATION_ROLE; the bind decision stays R16._new_bind -> R12 (r6) bind roles.
Lexical resources live only in tools/semantic_relation_resources_r19.json (classification/suppression only).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, Optional

from tools import semantic_event_parser_r16 as R16
from tools import single_parse_event_graph_r18 as R18

PARSER_VERSION = "R19.0"
R19_SHADOW_MODE = True
PRODUCTION_CUTOVER = False
SEMANTIC_RELATION_LAYER = True
UNKNOWN_SEMANTICS_DEFAULT = "NEUTRAL"
RELATION_CLASSES = ("PHYSICAL_OCCUPANCY", "COMPLETED_TRAVERSAL", "IN_PROGRESS_MOTION", "ATTEMPTED_TRAVERSAL", "BOUNDARY_INTERACTION",
                    "PERCEPTION_TARGET", "COMMUNICATION_REFERENCE", "MEMORY_REFERENCE", "OBJECT_REFERENCE", "TRANSACTION_REFERENCE",
                    "CESSATION", "PERMISSION", "DENIAL", "UNKNOWN")
BIND_ROLES_SENTINEL = R18.BIND_ROLES_SENTINEL

_RES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semantic_relation_resources_r19.json")
with open(_RES_PATH, encoding="utf-8-sig") as _f:
    _RES = json.load(_f)
assert _RES["MODE"] == "CLASSIFICATION_AND_SUPPRESSION_ONLY"
_TRANS_PRED = frozenset(_RES["TRANSACTION_PREDICATE"])
_TRANS_OBJ = frozenset(_RES["TRANSACTION_OBJECT"])
_CESS_PRED = frozenset(_RES["CESSATION_PREDICATE"])
_DENIAL = tuple((a, b) for a, b in _RES["DENIAL_IDIOM_NONCOMPOSITIONAL"])
_CESS_IDIOM = tuple((a, b) for a, b in _RES["CESSATION_IDIOM_NONCOMPOSITIONAL"])
SEMANTIC_RESOURCE_ENTRY_COUNT = sum(len(v) for v in _RES.values() if isinstance(v, list))
assert SEMANTIC_RESOURCE_ENTRY_COUNT <= _RES["CAP_TOTAL_ENTRIES_ALL_R19_RESOURCES"]

STATS = {"SEMANTIC_LAYER_NLP_CALLS": 0}
CROSSING = frozenset("into through inside".split())


def _new_bind(role: str) -> bool:
    return R16._new_bind(role)  # single R12 decision point


def _lem(t) -> str:
    return t.lemma_.lower()


def _idiom_hit(v, pairs) -> bool:
    lv = _lem(v)
    for a, b in pairs:
        if lv != a:
            continue
        if not b:
            return True
        if any(_lem(c) == b or c.lower_ == b for c in v.children):
            return True
        if any(_lem(g) == b for c in v.children if c.dep_ == "dobj" for g in [c]):
            return True
    return False


def _chain(pred, limit=6):
    cur, g = pred, 0
    out = [pred]
    while g < limit and cur.head.i != cur.i and cur.dep_ in ("xcomp", "dobj", "pcomp", "advcl", "acomp", "pobj", "prep", "dep"):
        cur, g = cur.head, g + 1
        out.append(cur)
        if cur.dep_ in ("ROOT", "conj", "ccomp", "relcl", "parataxis"):
            break
    return out


def _is_cessation(pred) -> bool:
    for v in _chain(pred):
        if _lem(v) in _CESS_PRED or _idiom_hit(v, _CESS_IDIOM):
            return True
        if any(c.dep_ == "advmod" and c.lower_ == "longer" and any(g.lower_ == "no" for g in c.children) for c in v.children):
            return True
    return False


def _obj_of(pred, pp):
    o = next((c for c in pred.children if c.dep_ == "dobj"), None)
    if o is None and pp is not None and pp.head.pos_ in ("NOUN", "PROPN") and pp.head.i != pred.i:
        o = pp.head
    return o


def _is_transaction(pred, obj) -> bool:
    if any(_lem(v) in _TRANS_PRED for v in _chain(pred)):
        return True
    return obj is not None and _lem(obj) in _TRANS_OBJ


def _boundary_owner(loc):
    """X is the owner of a boundary noun: 'the gate of X' / "X's gate"; returns the boundary token or None."""
    bnd = R16.BOUNDARY_NOUNS
    if loc.dep_ == "poss" and _lem(loc.head) in bnd:
        return loc.head
    if loc.dep_ == "pobj" and loc.head.lower_ == "of" and _lem(loc.head.head) in bnd:
        return loc.head.head
    return None


def _crossed(tok) -> bool:
    return tok.dep_ == "pobj" and tok.head.lower_ in CROSSING


def _base_relation(r) -> str:
    role, rule, et, st = r["LOCATION_ROLE"], r.get("R18_RULE") or "", r.get("EVENT_TYPE") or "", r.get("EVENT_STATE") or ""
    if role == "CURRENT_SITE":
        return "PHYSICAL_OCCUPANCY"
    if role == "SUCCESSFUL_DESTINATION":
        return "COMPLETED_TRAVERSAL"
    if role == "FAILED_DESTINATION":
        return "DENIAL"
    if role == "BOUNDARY_SITE" or rule == "BOUNDARY_INTERACTION":
        return "BOUNDARY_INTERACTION"
    if rule == "DEICTIC_TARGET":
        return "PERCEPTION_TARGET"
    if rule.startswith("OBJECT_REFERENCE"):
        return "OBJECT_REFERENCE"
    if et == "PERCEPTION_COMMUNICATION_MEMORY":
        return "PERCEPTION_TARGET"
    if st == "ATTEMPTED" or rule == "CONTROLLED_INFINITIVE":
        return "ATTEMPTED_TRAVERSAL"
    if st == "IN_PROGRESS":
        return "IN_PROGRESS_MOTION"
    if st == "PENDING" or et.startswith("ACCESS"):
        return "PERMISSION"
    if et == "REFERENCE" or role == "REFERENCE_SITE":
        return "OBJECT_REFERENCE"
    return "UNKNOWN"


def _refine_communication(r, pred) -> str:
    lf = R16._lemma_forms(pred) if pred is not None else set()
    if lf & R16.COMMUNICATION_LEMMAS or (pred is not None and R16._speech_like(pred)):
        return "COMMUNICATION_REFERENCE"
    if lf & R16.COGNITION_LEMMAS:
        return "MEMORY_REFERENCE"
    return "PERCEPTION_TARGET"


def _classify(r, loc, ctx):
    """Returns (relation, new_role_or_None, rule)."""
    rel = _base_relation(r)
    role = r["LOCATION_ROLE"]
    pred = R18._predicate_of(loc)
    pp = loc.head if loc.dep_ == "pobj" else None
    fp = pp.lower_ if pp is not None else ""
    if rel == "PERCEPTION_TARGET":
        rel = _refine_communication(r, pred)
    # (B) boundary ownership: the location owns the boundary noun the event touches
    owned = _boundary_owner(loc)
    if owned is not None and not _crossed(owned):
        return "BOUNDARY_INTERACTION", "BOUNDARY_SITE", "BOUNDARY_OWNERSHIP"
    if _lem(loc) in R16.BOUNDARY_NOUNS and not _crossed(loc) and any(
            (c.dep_ == "prep" and c.lower_ == "of" and any(R16._is_place_tok(g) for g in c.children if g.dep_ == "pobj"))
            or (c.dep_ == "poss" and R16._is_place_tok(c)) for c in loc.children):
        return "BOUNDARY_INTERACTION", "BOUNDARY_SITE", "BOUNDARY_OWNED_PART"
    if pred is None:
        return rel, None, ""
    obj = _obj_of(pred, pp)
    chain = _chain(pred)
    # (9) denial governing the event ('was barred from entering X')
    for v in chain:
        if any(c.dep_ in ("auxpass", "nsubjpass") for c in v.children) and _idiom_hit(v, _DENIAL):
            return "DENIAL", ("FAILED_DESTINATION" if role in set(BIND_ROLES_SENTINEL) | {"DESTINATION", "UNKNOWN"} else None), "DENIAL_GOVERNOR:" + _lem(v)
    # perception / communication / memory predicate: a target, never occupancy
    if role not in BIND_ROLES_SENTINEL and R18._excluded_class(pred):
        rel = _refine_communication(r, pred)
    # (8) permission (classification only; bind stays with R18 composition)
    if rel in ("ATTEMPTED_TRAVERSAL", "UNKNOWN", "PERMISSION", "IN_PROGRESS_MOTION") and role not in BIND_ROLES_SENTINEL and (
            any(_lem(v) in R16.PERMISSION_LEMMAS for v in chain) or
            any(_lem(c) in R16.REQUEST_NOUNS for v in chain for c in v.children if c.dep_ in ("dobj", "attr"))):
        rel = "PERMISSION"
    # (6) cessation
    if _is_cessation(pred):
        return "CESSATION", ("UNKNOWN" if role in BIND_ROLES_SENTINEL else None), "CESSATION"
    # (4) transaction / ownership reference
    if _is_transaction(pred, obj) and rel in ("PHYSICAL_OCCUPANCY", "UNKNOWN", "OBJECT_REFERENCE"):
        return "TRANSACTION_REFERENCE", ("UNKNOWN" if role in BIND_ROLES_SENTINEL else None), "TRANSACTION_REFERENCE"
    # attempt: 'rushed to barrel into X' read by the tagger as 'to' + noun
    for c in pred.children:
        if c.dep_ == "prep" and c.lower_ == "to":
            n = next((g for g in c.children if g.dep_ == "pobj"), None)
            if n is not None and not any(g.dep_ in ("det", "poss", "amod", "compound", "nummod") for g in n.children) and \
                    n.tag_ in ("NN", "VB") and n.i < loc.i and fp in CROSSING | {"in", "onto", "to"} and \
                    (pp is not None and (pp.head.i == n.i or (pp.head.i == pred.i and pp.i == n.i + 1))):
                return "ATTEMPTED_TRAVERSAL", ("DESTINATION" if role in BIND_ROLES_SENTINEL else None), "ATTEMPT_BARE_INFINITIVE"
    # (3) occupancy with an object on a surface: 'repaired the fuses on X' (not transaction, not a reference object)
    if role not in BIND_ROLES_SENTINEL and fp in ("on", "at") and obj is not None and \
            (r.get("R18_RULE") in ("OBJECT_REFERENCE", "") ) and not r.get("NEGATED") and \
            _lem(obj) not in R16.REF_NOUNS and r.get("EVENT_STATE") not in ("FAILED", "PLANNED", "PENDING", "ATTEMPTED", "IN_PROGRESS", "DEPARTED") \
            and (r.get("EVENT_TYPE") or "") in ("", "UNKNOWN", "UNATTACHED", "ACTIVITY_OCCUPANCY", "ACTIVITY_OCCUPANCY_RECOVERED", "OCCUPANCY") \
            and (pp.head.i == pred.i or pp.head.i == obj.i):
        s = R18._subj(pred)
        if R16._is_char_subject(s, ctx) and R18._chain_realis(pred) and not R18._excluded_class(pred) and \
                pred.lemma_.lower() not in (R16.LIGHT_LEMMAS | R16.PLACEMENT_LEMMAS) and \
                not any(g.dep_ == "poss" for g in obj.children) and R18._context_realis(R18._clause_head(loc))[0]:
            return "PHYSICAL_OCCUPANCY", "CURRENT_SITE", "SURFACE_ACTIVITY_LOCATIVE"
    return rel, None, ""


def _denial_events(sent, ctx):
    out = []
    for t in sent:
        if t.pos_ not in ("VERB", "AUX") and not R16._is_verbal(t):
            continue
        if not any(c.dep_ in ("auxpass", "nsubjpass") for c in t.children):
            continue  # the character is the undergoer of the denial
        if _idiom_hit(t, _DENIAL):
            out.append((t, R18._subject_key(t, ctx)))
    return out


def analyze(text: str, *, depicted_characters: Optional[Iterable[str]] = None,
            character_context: Optional[Any] = None, timing: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    tm: Dict[str, float] = {}
    out = R18.analyze(text, depicted_characters=depicted_characters, character_context=character_context, timing=tm)
    t0 = time.perf_counter()
    if not out.get("PARSER_AVAILABLE"):
        return out
    doc = R16._DOC_CACHE.get(text)  # the same Doc R18 parsed; never re-parsed here
    dep = list(depicted_characters) if depicted_characters is not None else None
    ctx = R16._Ctx(dep, character_context)
    recs = out["records"]
    sents = list(doc.sents)
    locs = []
    for r in recs:
        sp = doc.char_span(r["START_CHAR"], r["END_CHAR"], alignment_mode="expand")
        loc = None
        if sp is not None:
            loc = next((t for t in sp if t.lower_ == r["HEAD"]), sp.root)
        locs.append(loc)
    for r, loc in zip(recs, locs):
        r["R19_RULE"] = ""
        if loc is None:
            r["SEMANTIC_RELATION"] = _base_relation(r)
            continue
        rel, newrole, rule = _classify(r, loc, ctx)
        r["SEMANTIC_RELATION"] = rel
        if newrole is not None and newrole != r["LOCATION_ROLE"]:
            r["R19_PRIOR_ROLE"] = r["LOCATION_ROLE"]
            r["LOCATION_ROLE"] = newrole
            r["R19_RULE"] = rule
            if newrole == "CURRENT_SITE":
                r.update(EVENT_STATE="CURRENT", CURRENT_OCCUPANCY_EVIDENCE=True)
            elif newrole in ("UNKNOWN", "BOUNDARY_SITE"):
                r.update(CURRENT_OCCUPANCY_EVIDENCE=False, COMPLETED_TRAVERSAL_EVIDENCE=False)
            elif newrole == "DESTINATION":
                r.update(EVENT_STATE="ATTEMPTED", COMPLETED_TRAVERSAL_EVIDENCE=False)
        elif rule:
            r["R19_RULE"] = rule
    # denial composition: same subject, same sentence, later passive denial event
    for s in sents:
        idx = [(r, l) for r, l in zip(recs, locs) if l is not None and s.start <= l.i < s.end]
        for v, k in _denial_events(s, ctx):
            if not k or k == R16.UNRESOLVED.lower():
                continue
            cands = [(r, l) for r, l in idx if l.i < v.i and (r.get("SUBJECT_CHARACTER_ID") or "").lower() == k]
            if not cands:
                continue
            r, l = max(cands, key=lambda x: x[1].i)
            between = doc[l.i + 1:v.i]
            if any(b.dep_ in ("nsubj", "nsubjpass") and b.i != v.i and (b.pos_ == "PROPN" or b.lower_ in R16.PERSONAL_PRON) and
                   R18._subject_key(b.head, ctx) != k for b in between):
                continue
            if r["LOCATION_ROLE"] in ("DESTINATION", "UNKNOWN", "BOUNDARY_SITE", "SUCCESSFUL_DESTINATION", "NONDEPICTED_SUBJECT_SITE",
                                      "UNRESOLVED_SUBJECT_SITE", "CURRENT_SITE"):
                r["R19_PRIOR_ROLE"] = r["LOCATION_ROLE"]
                r.update(LOCATION_ROLE="FAILED_DESTINATION", EVENT_STATE="FAILED", EVENT_RESULT="FAILURE", SEMANTIC_RELATION="DENIAL",
                         R19_RULE="DENIAL_COMPOSITION:" + _lem(v))
    # depiction gate on R19-upgraded roles, then the single R12 decision point
    for r in recs:
        role = r["LOCATION_ROLE"]
        if role in BIND_ROLES_SENTINEL:
            sid = (r.get("SUBJECT_CHARACTER_ID") or "").lower()
            if r.get("SUBJECT_CHARACTER_ID") == R16.UNRESOLVED:
                r["LOCATION_ROLE"] = "UNRESOLVED_SUBJECT_SITE"
            elif ctx.depicted is not None and not (sid and sid in ctx.depicted):
                r["LOCATION_ROLE"] = "NONDEPICTED_SUBJECT_SITE" if sid else "UNRESOLVED_SUBJECT_SITE"
        r["FINAL_BIND_ALLOWED"] = _new_bind(r["LOCATION_ROLE"])
        r["FINAL_BIND_REASON"] = "LOCATION_ROLE=" + r["LOCATION_ROLE"]
    t1 = time.perf_counter()
    if timing is not None:
        for k, v in tm.items():
            timing[k] = timing.get(k, 0.0) + v
        timing["SEMANTIC_LAYER_MS"] = timing.get("SEMANTIC_LAYER_MS", 0.0) + (t1 - t0) * 1000
    out["R19_SHADOW_MODE"] = True
    out["SEMANTIC_RELATION_LAYER"] = True
    return out
