"""SCENE_ENVIRONMENT_POSITIVE_SETTING_ONTOLOGY_R20 (shadow only).

Place detection layered over the FROZEN R19 relation layer and R18 single-parse graph. The one spaCy Doc that
R18 parsed is re-used (never re-parsed). Place mentions are classed NAMED_SETTING, POSITIVE_SETTING_NOUN,
LOCAL_SPOT, AMBIGUOUS or UNKNOWN; only the first two may set SETTING_CANDIDATE=YES. Candidacy never decides a
bind: event state, subject and depiction gates apply, and the final decision is R16._new_bind (R12 bind roles).
The single positive resource is tools/resources/setting_nouns_r20.json (capped, auditable).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, Optional

from tools import semantic_event_parser_r16 as R16
from tools import single_parse_event_graph_r18 as R18
from tools import semantic_relation_layer_r19 as R19

PARSER_VERSION = "R20.0"
R20_SHADOW_MODE = True
PRODUCTION_CUTOVER = False
MENTION_CLASSES = ("NAMED_SETTING", "POSITIVE_SETTING_NOUN", "LOCAL_SPOT", "AMBIGUOUS", "UNKNOWN")
CANDIDATE_CLASSES = ("NAMED_SETTING", "POSITIVE_SETTING_NOUN")
BIND_ROLES_SENTINEL = R18.BIND_ROLES_SENTINEL

_ONTO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "setting_nouns_r20.json")
with open(_ONTO_PATH, encoding="utf-8") as _f:
    _ONTO = json.load(_f)
assert _ONTO["MODE"] == "POSITIVE_SETTING_CANDIDATE_ONLY"
assert len(_ONTO["ENTRIES"]) <= _ONTO["CAP"] <= 100
SETTING_ONTOLOGY_ENTRY_COUNT = len(_ONTO["ENTRIES"])
_SETTING = frozenset(e["LEMMA"] for e in _ONTO["ENTRIES"])
_AMBIGUOUS = frozenset(_ONTO["AMBIGUOUS_EXCLUDED"])

# closed-class grammar (capped): locative prepositions
STATIVE_PREPS = frozenset("at on in inside within by beside near against before beneath under atop upon along across".split())
CROSSING_PREPS = frozenset("into onto through inside across".split())
HALT_LEMMAS = frozenset("stop halt pause".split())
ENTRY_DEVICE = frozenset("door doors gate gates".split())  # boundary owners stay boundary-only (David's rule)
STATS = {"R20_NLP_CALLS": 0}


def _new_bind(role: str) -> bool:
    return R16._new_bind(role)  # single R12 decision point


def _is_person(tok, ctx) -> bool:
    return tok.ent_type_ in ("PERSON", "NORP") or bool(ctx.char_id(tok.text)) or tok.lower_ in (ctx.depicted or set()) \
        or tok.lower_ in R16.PERSONAL_PRON


def mention_class(tok, ctx) -> str:
    if tok is None:
        return "UNKNOWN"
    if tok.pos_ == "PROPN":
        if R16._is_place_tok(tok):
            return "NAMED_SETTING"
        if _is_person(tok, ctx):
            return "LOCAL_SPOT"  # person-relative position
        named = tok.ent_type_ in ("GPE", "LOC", "FAC") or any(c.dep_ == "det" and c.lower_ == "the" for c in tok.children)
        return "NAMED_SETTING" if named else "UNKNOWN"
    if tok.pos_ in ("PRON", "ADV"):
        return "LOCAL_SPOT"
    if tok.pos_ != "NOUN":
        return "UNKNOWN"
    lem, low = tok.lemma_.lower(), tok.lower_
    if lem in _AMBIGUOUS or low in _AMBIGUOUS:
        return "AMBIGUOUS"
    if lem in _SETTING or low in _SETTING or R16._is_place_tok(tok):
        return "POSITIVE_SETTING_NOUN"
    return "UNKNOWN"


def _perception_scope(loc, pred) -> bool:
    """A perception/communication verb governs this location, including coordinated or elliptical 'then at X'."""
    cur, g = loc, 0
    while cur.head.i != cur.i and g < 10:
        cur, g = cur.head, g + 1
        if R16._is_verbal(cur) or cur.pos_ == "VERB":
            if R18._excluded_class(cur):
                return True
            if any(c.dep_ == "xcomp" and R18._excluded_class(c) and c.i < loc.i for c in cur.children):
                return True
            pp = loc.head if loc.dep_ == "pobj" else None
            if pp is not None:  # elliptical 'V at A, then at X': X repeats the preposition of an earlier complement verb
                for c in cur.children:
                    if c.dep_ == "xcomp" and c.i < pp.i and any(g.dep_ == "prep" and g.lower_ == pp.lower_ for g in c.children) and \
                            (R18._excluded_class(c) or (pp.lower_ in R18.TARGET_PREPS and not any(g.dep_ == "dobj" for g in c.children))):
                        return True
            if cur.dep_ not in ("xcomp", "pcomp", "conj"):
                break
    return False


def _subject(pred, ctx):
    s, r, pron = R18._subject_for(pred, ctx)
    if s is None:
        return None, ""
    if pron and r is None:
        return s, R16.UNRESOLVED
    if not pron and not R16._is_char_subject(s, ctx):
        dk = _depicted_phrase_key(s, ctx)  # the subject phrase IS a depicted id ('the solitary one' -> solitary_one)
        return s, dk
    return s, R18._char_key(r, ctx)


def _depicted_phrase_key(s, ctx) -> str:
    if ctx.depicted is None:
        return ""
    words = [t.lower_ for t in s.subtree if t.i <= s.i and t.dep_ not in ("det", "punct", "poss", "nummod") and t.is_alpha]
    for k in range(len(words)):
        key = "_".join(words[k:])
        if key in ctx.depicted:
            return key
    return ""


def _blocked(pred, loc) -> str:
    """Event-state gates the ontology can never bypass."""
    chain = R19._chain(pred)
    if not R18._chain_realis(pred):
        return "NONREALIS_PREDICATE"
    if not R18._context_realis(R18._clause_head(loc))[0]:
        return "NONREALIS_CONTEXT"
    if any(R18._has_to(v) for v in chain):
        return "ATTEMPT_OR_PLAN"
    if any(v.lemma_.lower() in R16.PERMISSION_LEMMAS | R16.ATTEMPT_CONTROL_LEMMAS | R16.PLAN_CONTROL_LEMMAS for v in chain):
        return "PERMISSION_ATTEMPT_PLAN"
    if any(any(c.dep_ in ("auxpass", "nsubjpass") for c in v.children) and R19._idiom_hit(v, R19._DENIAL) for v in chain):
        return "DENIAL"
    if pred.lemma_.lower() not in HALT_LEMMAS and R19._is_cessation(pred):
        return "CESSATION"
    if R19._is_transaction(pred, R19._obj_of(pred, loc.head if loc.dep_ == "pobj" else None)):
        return "TRANSACTION"
    if _perception_scope(loc, pred) or R18._excluded_class(pred):
        return "PERCEPTION"
    if pred.tag_ == "VBG" and any(a.lemma_.lower() == "be" for a in R16._aux(pred)):
        return "IN_PROGRESS"
    if pred.lemma_.lower() in R16.INCHOATIVE_LEMMAS or pred.lemma_.lower() in R16.REQUEST_LEMMAS:
        return "APPROACH_OR_REQUEST"
    return ""


def _motion(pred) -> bool:
    lf = R16._lemma_forms(pred)
    return bool(lf & (R16.MOTION_LEMMAS | R16.TRAVERSE_INTO_LEMMAS | R16.SOURCE_MOTION_LEMMAS)) or R18._serial(pred) is not None if hasattr(R18, "_serial") else False


def _role_for(loc, pred, prep):
    """Structural relation of a realised event to its location phrase."""
    motion = _motion(pred)
    if prep in ("into", "onto", "through") or (prep in ("inside", "across") and motion):
        return "SUCCESSFUL_DESTINATION", "COMPLETED_TRAVERSAL"
    if prep == "to":
        if motion and pred.tag_ == "VBD":
            return "SUCCESSFUL_DESTINATION", "COMPLETED_TRAVERSAL"
        return None, "UNKNOWN"
    if prep in STATIVE_PREPS:
        if motion and pred.lemma_.lower() not in HALT_LEMMAS and prep not in ("at", "in", "on", "along", "within"):
            return None, "UNKNOWN"
        return "CURRENT_SITE", "PHYSICAL_OCCUPANCY"
    return None, "UNKNOWN"


def _site_token(t):
    """Partitive 'edge/top/center/mouth of X': the place is X unless the part is an entry device."""
    for c in t.children:
        if c.dep_ == "prep" and c.lower_ == "of":
            x = next((g for g in c.children if g.dep_ == "pobj" and g.pos_ in ("NOUN", "PROPN")), None)
            if x is not None and t.lemma_.lower() not in ENTRY_DEVICE:
                return x
    return t


def analyze(text: str, *, depicted_characters: Optional[Iterable[str]] = None,
            character_context: Optional[Any] = None, timing: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    tm: Dict[str, float] = {}
    out = R19.analyze(text, depicted_characters=depicted_characters, character_context=character_context, timing=tm)
    t0 = time.perf_counter()
    if not out.get("PARSER_AVAILABLE"):
        return out
    doc = R16._DOC_CACHE.get(text)  # the same Doc; never re-parsed
    dep = list(depicted_characters) if depicted_characters is not None else None
    ctx = R16._Ctx(dep, character_context)
    recs = out["records"]
    covered = set()
    for r in recs:
        sp = doc.char_span(r["START_CHAR"], r["END_CHAR"], alignment_mode="expand")
        loc = next((t for t in sp if t.lower_ == r["HEAD"]), sp.root) if sp is not None else None
        r["_tok"] = loc
        if sp is not None:
            covered.update(range(sp.start, sp.end))
    # ---- pass A: revise existing records structurally
    for r in recs:
        loc = r["_tok"]
        r["R20_RULE"] = ""
        r["MENTION_CLASS"] = mention_class(loc, ctx) if loc is not None else "UNKNOWN"
        r["SETTING_CANDIDATE"] = r["MENTION_CLASS"] in CANDIDATE_CLASSES
        if loc is None:
            continue
        pred = R18._predicate_of(loc)
        if pred is None:
            continue
        pp = loc.head if loc.dep_ == "pobj" else None
        role = r["LOCATION_ROLE"]
        if role in BIND_ROLES_SENTINEL and (_perception_scope(loc, pred)):
            r.update(LOCATION_ROLE="UNKNOWN", SEMANTIC_RELATION="PERCEPTION_TARGET", R20_RULE="PERCEPTION_CARRYOVER")
            continue
        if role in BIND_ROLES_SENTINEL or not r["SETTING_CANDIDATE"] or r.get("NEGATED"):
            continue
        if r.get("SEMANTIC_RELATION") in ("DENIAL", "PERMISSION", "TRANSACTION_REFERENCE", "ATTEMPTED_TRAVERSAL", "IN_PROGRESS_MOTION") \
                or role in ("FAILED_DESTINATION", "PLANNED_SITE", "PENDING_SITE", "DEPARTED", "SOURCE"):
            if not (pred.lemma_.lower() in HALT_LEMMAS and pp is not None and pp.head.i == pred.i):
                continue
        # partitive 'stood at the center/edge/mouth of X' -> X; entry devices keep David's boundary rule
        site_pp = pp
        if pp is not None and pp.lower_ == "of" and pp.dep_ == "prep" and pp.head.pos_ == "NOUN" and pp.head.lemma_.lower() not in ENTRY_DEVICE \
                and pp.head.dep_ == "pobj":
            site_pp = pp.head.head
        if site_pp is None or site_pp.lower_ not in STATIVE_PREPS | CROSSING_PREPS | {"to"}:
            continue
        if site_pp.head.i != pred.i and not (site_pp is not pp):
            continue
        why = _blocked(pred, loc)
        if why and not (why == "CESSATION" and pred.lemma_.lower() in HALT_LEMMAS):
            continue
        _s, key = _subject(pred, ctx)
        if not key:
            continue
        newrole, rel = _role_for(loc, pred, site_pp.lower_)
        if newrole is None:
            continue
        r.update(LOCATION_ROLE=newrole, SEMANTIC_RELATION=rel, SUBJECT_CHARACTER_ID=key,
                 EVENT_STATE="CURRENT" if newrole == "CURRENT_SITE" else "COMPLETED",
                 R20_RULE="HALTED_MOTION" if pred.lemma_.lower() in HALT_LEMMAS else ("PARTITIVE_SITE" if site_pp is not pp else "STRUCTURAL_SETTING_EVENT"))
    # ---- pass B: new place mentions the legacy detector never produced
    cands = 0
    for t in doc:
        if t.i in covered or t.pos_ not in ("NOUN", "PROPN") or t.dep_ not in ("pobj", "dobj"):
            continue
        if t.dep_ == "pobj" and t.head.lower_ == "of":
            if t.head.dep_ != "prep":
                continue
            part = t.head.head
            if part.dep_ != "pobj" or part.lemma_.lower() in ENTRY_DEVICE or part.head.lower_ not in STATIVE_PREPS | CROSSING_PREPS | {"to"}:
                continue
            pp = part.head
        elif t.dep_ == "pobj":
            if t.head.lower_ not in STATIVE_PREPS | CROSSING_PREPS | {"to"}:
                continue
            pp = t.head
        else:
            if t.head.lemma_.lower() not in R16.TRAVERSE_OBJ_LEMMAS:
                continue
            pp = None
        if t.dep_ == "pobj" and t.head.lower_ != "of" and any(c.dep_ == "prep" and c.lower_ == "of" for c in t.children):
            continue  # its 'of' object is the site
        mc = mention_class(t, ctx)
        if t.dep_ == "pobj" and t.head.lower_ != "of":
            x = _site_token(t)
            if x is not t:
                continue
        cands += 1
        rec = {"HEAD": t.lower_, "START_CHAR": t.left_edge.idx if t.left_edge.i >= (pp.i + 1 if pp is not None else 0) else t.idx,
               "END_CHAR": t.idx + len(t.text), "CANONICAL_LOCATION": doc[(pp.i + 1 if pp is not None else t.left_edge.i):t.i + 1].text,
               "LOCATION_ROLE": "UNKNOWN", "EVENT_STATE": "UNKNOWN", "EVENT_RESULT": "UNKNOWN", "SEMANTIC_RELATION": "UNKNOWN",
               "SUBJECT_CHARACTER_ID": "", "MENTION_CLASS": mc, "SETTING_CANDIDATE": mc in CANDIDATE_CLASSES,
               "R20_RULE": "NEW_MENTION", "R20_NEW_RECORD": True, "_tok": t}
        recs.append(rec)
        if not rec["SETTING_CANDIDATE"]:
            continue
        pred = R18._predicate_of(t) if pp is not None else t.head
        if pred is not None and pp is not None and pp.head.dep_ in ("advmod", "prt") and pp.head.head.i == pred.i:
            pp_host = pred  # 'came back to X'
        else:
            pp_host = pp.head if pp is not None else None
        if pred is None or (pp is not None and pp_host.i != pred.i and not (t.head.lower_ == "of")):
            rec["R20_RULE"] = "NOT_EVENT_LOCATIVE"
            continue
        if t.head.lower_ == "of" and pp.head.i != pred.i:
            rec["R20_RULE"] = "NOT_EVENT_LOCATIVE"
            continue
        why = _blocked(pred, t)
        if why and not (why == "CESSATION" and pred.lemma_.lower() in HALT_LEMMAS):
            rec["R20_RULE"] = "GATED:" + why
            rec["SEMANTIC_RELATION"] = {"PERCEPTION": "PERCEPTION_TARGET", "DENIAL": "DENIAL", "CESSATION": "CESSATION",
                                        "TRANSACTION": "TRANSACTION_REFERENCE", "IN_PROGRESS": "IN_PROGRESS_MOTION"}.get(why, "ATTEMPTED_TRAVERSAL" if "ATTEMPT" in why else "UNKNOWN")
            continue
        if R16._has_neg(pred):
            rec["R20_RULE"] = "GATED:NEGATED"
            continue
        _s, key = _subject(pred, ctx)
        rec["SUBJECT_CHARACTER_ID"] = key
        if not key:
            rec["R20_RULE"] = "NO_CHARACTER_SUBJECT"
            continue
        if pp is None:
            newrole, rel = "SUCCESSFUL_DESTINATION", "COMPLETED_TRAVERSAL"
        else:
            newrole, rel = _role_for(t, pred, pp.lower_)
        if newrole is None:
            continue
        if any(v.i > t.i and k == key.lower() for v, k in R19._denial_events(t.sent, ctx)):
            rec.update(LOCATION_ROLE="FAILED_DESTINATION", SEMANTIC_RELATION="DENIAL", EVENT_STATE="FAILED", EVENT_RESULT="FAILURE",
                       R20_RULE="DENIAL_COMPOSITION")
            continue
        rec.update(LOCATION_ROLE=newrole, SEMANTIC_RELATION=rel, EVENT_STATE="CURRENT" if newrole == "CURRENT_SITE" else "COMPLETED",
                   EVENT_RESULT="NONE" if newrole == "CURRENT_SITE" else "SUCCESS",
                   R20_RULE="HALTED_MOTION" if pred.lemma_.lower() in HALT_LEMMAS else "STRUCTURAL_SETTING_EVENT")
    # ---- depiction gate, then the single R12 decision point
    for r in recs:
        r.pop("_tok", None)
        if r.get("R20_NEW_RECORD") or r.get("R20_RULE"):
            role = r["LOCATION_ROLE"]
            if role in BIND_ROLES_SENTINEL:
                sid = (r.get("SUBJECT_CHARACTER_ID") or "").lower()
                if r.get("SUBJECT_CHARACTER_ID") == R16.UNRESOLVED or not sid:
                    r["LOCATION_ROLE"] = "UNRESOLVED_SUBJECT_SITE"
                elif ctx.depicted is not None and sid not in ctx.depicted:
                    r["LOCATION_ROLE"] = "NONDEPICTED_SUBJECT_SITE"
        r["FINAL_BIND_ALLOWED"] = _new_bind(r["LOCATION_ROLE"])
        r["FINAL_BIND_REASON"] = "LOCATION_ROLE=" + r["LOCATION_ROLE"]
    t1 = time.perf_counter()
    if timing is not None:
        for k, v in tm.items():
            timing[k] = timing.get(k, 0.0) + v
        timing["PLACE_DETECTION_MS"] = timing.get("PLACE_DETECTION_MS", 0.0) + (t1 - t0) * 1000
        timing["LOCATION_CANDIDATES"] = timing.get("LOCATION_CANDIDATES", 0) + cands + len([r for r in recs if not r.get("R20_NEW_RECORD")])
    out["R20_SHADOW_MODE"] = True
    return out
