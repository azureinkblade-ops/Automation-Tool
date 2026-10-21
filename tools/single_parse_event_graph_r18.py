"""SCENE_ENVIRONMENT_SINGLE_PARSE_EVENT_GRAPH_R18 (shadow only).

Exactly ONE spaCy parse per input text (each sentence parsed once).  The event graph is built from the
ORIGINAL Doc's token dependencies; no clause, conjunct or fragment is ever handed back to the spaCy pipeline.
R16 (frozen) extraction runs on that same Doc.  Composition is keyed by SUBJECT_CHARACTER_ID +
CANONICAL_LOCATION within one sentence.  The only bind decision is R16._new_bind -> R12 (r6) bind roles.
Boundary-device ontology (tools/boundary_device_ontology_r18.json) is SUPPRESSION_ONLY.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tools import semantic_event_parser_r16 as R16

PARSER_VERSION = "R18.0"
R18_SHADOW_MODE = True
PRODUCTION_CUTOVER = False
SINGLE_PARSE_EVENT_GRAPH = True
EVENT_COMPOSITION_KEY = "SUBJECT_PLUS_LOCATION"
UNKNOWN_SEMANTICS_DEFAULT = "NEUTRAL"
UNRESOLVED_PRONOUN_POLICY = "FAIL_NEUTRAL"
BIND_ROLES_SENTINEL = ("CURRENT_SITE", "SUCCESSFUL_DESTINATION")

# ---- the single auditable semantic resource (suppression only)
_ONTO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boundary_device_ontology_r18.json")
with open(_ONTO_PATH, encoding="utf-8-sig") as _f:
    _ONTO = json.load(_f)
assert _ONTO["MODE"] == "SUPPRESSION_ONLY"
BOUNDARY_DEVICE_ONTOLOGY_MODE = _ONTO["MODE"]
_BOUNDARY_DEVICE = frozenset(_ONTO["BOUNDARY_DEVICE"])


def is_boundary_device(tok) -> bool:
    """Only consumer of the ontology. Returns True => suppression only."""
    return tok is not None and tok.lemma_.lower() in _BOUNDARY_DEVICE


# ---- instrumentation (every nlp invocation made by this module)
STATS = {"NLP_CALLS": 0, "SENTENCES_PARSED": 0, "CLAUSE_REPARSE_COUNT": 0}

# closed-class grammar only
CLAUSE_DEPS = frozenset("ROOT conj advcl ccomp parataxis relcl dep".split())
DIRECTIONAL_PARTICLES = frozenset("in inside through indoors within aboard".split())
CROSSING_PREPS = frozenset("into inside through".split())
CONTAINMENT_PREPS = frozenset("in inside within aboard on".split())
OBJ_CONTAINMENT_PREPS = frozenset("in inside within aboard".split())
TARGET_PREPS = frozenset("at toward towards".split())
APPROACH_PARTICLES = frozenset("in down up".split())
DISPLACEMENT_PARTICLES = frozenset("away back off out".split())
WAY_CONSTRUCTION_NOUN = "way"  # English 'X's way into' construction (grammatical, single item)
MARK_EDGE = {"if": "CONDITION", "unless": "CONDITION", "whether": "COMPLEMENT_OF", "that": "COMPLEMENT_OF",
             "because": "SUBORDINATE_TO", "since": "SUBORDINATE_TO", "although": "CONTRAST_WITH", "though": "CONTRAST_WITH",
             "while": "SUBORDINATE_TO", "when": "SUBORDINATE_TO", "as": "SUBORDINATE_TO", "after": "TEMPORAL_AFTER",
             "once": "TEMPORAL_AFTER", "before": "TEMPORAL_BEFORE", "until": "TEMPORAL_BEFORE"}
CC_EDGE = {"and": "CONJUNCT_OF", "but": "CONTRAST_WITH", "yet": "CONTRAST_WITH", "or": "CONDITION", "then": "TEMPORAL_AFTER",
           "so": "CONJUNCT_OF"}
NONREALIS_EDGES = frozenset("CONDITION COMPLEMENT_OF CONTROLLED_BY RELATIVE_TO PURPOSE".split())


def _new_bind(role: str) -> bool:
    return R16._new_bind(role)  # single R12 decision point


def _has_to(v) -> bool:
    return any(c.dep_ == "aux" and c.tag_ == "TO" for c in v.children)


# ---------------------------------------------------------------- clause structure (original tokens)
def _clause_head(tok):
    cur, g = tok, 0
    while cur.dep_ not in CLAUSE_DEPS and cur.head.i != cur.i and g < 40:
        cur, g = cur.head, g + 1
    return cur


def _edge_type(head) -> str:
    d = head.dep_
    if d == "ROOT":
        return "ROOT"
    if d in ("ccomp", "parataxis"):
        gov = head.head
        if head.i < gov.i and not any(c.dep_ == "mark" for c in head.children) and \
                any(t.lower_ in CC_EDGE for t in head.doc[head.right_edge.i + 1:gov.i]):
            return "CONJUNCT_OF"  # left-attached 'ccomp' of a non-reporting verb: tagger reading of 'X then Y'
        return "COMPLEMENT_OF"
    if d == "relcl":
        return "RELATIVE_TO"
    if d == "xcomp":
        return "CONTROLLED_BY"
    if d == "advcl":
        if _has_to(head):
            return "PURPOSE"
        for c in head.children:
            if c.dep_ == "mark" and c.lower_ in MARK_EDGE:
                return MARK_EDGE[c.lower_]
        return "SUBORDINATE_TO"
    if d == "conj":
        ccs = [c.lower_ for c in head.children if c.dep_ in ("cc", "advmod") and c.i < head.i] + \
              [c.lower_ for c in head.head.children if c.dep_ == "cc" and head.head.i < c.i < head.i]
        for c in ccs:
            if c in CC_EDGE:
                return CC_EDGE[c]
        return "CONJUNCT_OF"
    return "SUBORDINATE_TO"


def _context_realis(head) -> Tuple[bool, List[str]]:
    path, cur, g = [], head, 0
    while g < 12:
        g += 1
        e = _edge_type(cur)
        path.append(e)
        if e == "ROOT" or cur.head.i == cur.i:
            break
        par = _clause_head(cur.head)
        if e in ("CONJUNCT_OF", "CONTRAST_WITH", "TEMPORAL_AFTER") and cur.tag_ in ("VBD", "VBZ", "VBP") and \
                _has_to(par) and par.head.i != par.i:
            par = _clause_head(par.head)  # finite conjunct escapes the infinitive's scope
        cur = par
    return not any(e in NONREALIS_EDGES for e in path), path


# ---------------------------------------------------------------- subjects
def _subject_for(head, ctx):
    s = R16._subject_of(head)
    if s is None or s.dep_ == "expl":
        s = R16._dep_subject([head])
    cur, g = head, 0
    while s is None and g < 8 and cur.head.i != cur.i:
        cur, g = cur.head, g + 1
        if R16._is_verbal(cur) or any(c.dep_ in ("nsubj", "nsubjpass") for c in cur.children):
            s = R16._subject_of(cur)
    if s is None:
        return None, None, False
    if s.lower_ in R16.PERSONAL_PRON:
        return s, R16._resolve_pronoun(s, ctx), True
    return s, s, False


def _char_key(tok, ctx) -> str:
    if tok is None:
        return ""
    txt = R16._subject_text(tok)
    cid = ctx.char_id(txt)
    if not cid and tok.pos_ == "PROPN" and not ctx.name_to_id:
        cid = txt
    return cid


def _subject_key(v, ctx) -> str:
    s, r, pron = _subject_for(v, ctx)
    if s is None:
        return ""
    if pron and r is None:
        return R16.UNRESOLVED.lower()
    return _char_key(r, ctx).lower()


# ---------------------------------------------------------------- predicate realis along a verb chain
def _chain_realis(v) -> bool:
    """v and every verbal governor up to its clause head: no TO-infinitive (unless success control), modal or negation."""
    cur, g = v, 0
    while cur is not None and g < 6:
        g += 1
        if _has_to(cur):
            gov = cur.head
            if not (cur.dep_ == "xcomp" and gov.lemma_.lower() in R16.SUCCESS_CONTROL):
                return False
        auxes = R16._aux(cur)
        if any(a.tag_ == "MD" or a.lemma_.lower() in R16.MODAL_LEMMAS for a in auxes):
            return False
        if R16._has_neg(cur):
            return False
        if any(c.dep_ == "advmod" and c.lower_ == "longer" and any(g.lower_ == "no" for g in c.children) for c in cur.children):
            return False  # 'no longer'
        if cur is not v and cur.lemma_.lower() in R16.CESSATION_CONTROL:
            return False  # gerund complement of a cessation verb
        if cur.dep_ in ("xcomp", "advcl", "dep", "pcomp", "dobj") and cur.tag_ in ("VBG", "VB") and cur.head.i != cur.i:
            cur = cur.head
            continue
        break
    return True


def _serial(v) -> bool:
    """'came racing into X': a finite non-auxiliary verb tagged as aux of a gerund (serial motion construction)."""
    return v.tag_ == "VBG" and any(a.dep_ == "aux" and a.lemma_.lower() not in ("be", "have", "do") and a.tag_ not in ("MD", "TO")
                                   for a in v.children)


def _subj(v):
    for c in v.children:
        if c.dep_ in ("nsubj", "nsubjpass"):
            return c
    for c in v.children:  # subject attached to a serial 'aux' ('Marta went racing')
        if c.dep_ == "aux":
            for g in c.children:
                if g.dep_ in ("nsubj", "nsubjpass"):
                    return g
    s = R16._subject_of(v) or R16._dep_subject([v])
    cur, g = v, 0
    while s is None and g < 4 and cur.head.i != cur.i:
        cur, g = cur.head, g + 1
        s = next((c for c in cur.children if c.dep_ in ("nsubj", "nsubjpass")), None) or R16._subject_of(cur)
    return s


def _predicate_of(loc):
    prep, nominal, verb, path = R16._governing(loc)
    if verb is not None:
        return verb
    cur, g = loc, 0
    while cur.head.i != cur.i and g < 12:
        cur, g = cur.head, g + 1
        if any(c.dep_ in ("nsubj", "nsubjpass") for c in cur.children) and cur.pos_ not in ("PROPN", "PRON"):
            return cur
    return None


def _excluded_class(v) -> bool:
    lf = R16._lemma_forms(v)
    return bool(lf & (R16.PERCEPTION_LEMMAS | R16.COMMUNICATION_LEMMAS | R16.COGNITION_LEMMAS | R16.DIRECTED_AT_LEMMAS)) \
        or R16._speech_like(v)


# ---------------------------------------------------------------- per-location revision on ORIGINAL tokens
def _revise(loc, rec: Dict[str, Any], ctx) -> Dict[str, Any]:
    out = dict(rec)
    out["R18_RULE"] = ""
    role = rec["LOCATION_ROLE"]
    et = rec.get("EVENT_TYPE") or ""

    def setr(rule, state, result, newrole, **kw):
        out.update(EVENT_STATE=state, EVENT_RESULT=result, LOCATION_ROLE=newrole, R18_RULE=rule, **kw)

    pp = loc.head if loc.dep_ == "pobj" else None
    fp = pp.lower_ if pp is not None else ""
    pred = _predicate_of(loc)
    if pred is None:
        return out
    obj = next((c for c in pred.children if c.dep_ == "dobj"), None)
    if obj is None:  # object of a particle-preposition ('dusted off the trophies')
        for c in pred.children:
            if c.dep_ in ("prt", "prep") and (pp is None or c.i != pp.i) and c.i < loc.i:
                obj = next((g for g in c.children if g.dep_ == "pobj"), None)
                if obj is not None:
                    break
    pp_on_pred = pp is not None and pp.head.i == pred.i
    pp_on_obj = pp is not None and obj is not None and pp.head.i == obj.i
    host = pp.head if pp is not None else None  # token the location PP modifies

    # (13) controlled infinitive: an infinitive between location and clause head (not success-controlled)
    a = loc
    for _g in range(14):
        if a.head.i == a.i:
            break
        a = a.head
        bare_inf = a.dep_ == "pobj" and a.head.lower_ == "to" and a.tag_ in ("NN", "VB") and \
            not any(c.dep_ in ("det", "poss", "amod", "compound") for c in a.children)  # tagger: 'to dart' read as noun
        if _has_to(a) or bare_inf:
            if not (a.dep_ == "xcomp" and a.head.lemma_.lower() in R16.SUCCESS_CONTROL):
                if role in BIND_ROLES_SENTINEL:
                    setr("CONTROLLED_INFINITIVE", "ATTEMPTED", "UNKNOWN", "DESTINATION",
                         COMPLETED_TRAVERSAL_EVIDENCE=False, CURRENT_OCCUPANCY_EVIDENCE=False)
                else:
                    out["R18_RULE"] = "CONTROLLED_INFINITIVE"
                return out  # an unrealized infinitive is never upgraded
            break
        if a.dep_ in CLAUSE_DEPS and a.dep_ not in ("ROOT", "conj"):
            break

    # (8) boundary device / boundary contact: SUPPRESSION ONLY
    boundary = False
    if host is not None and host.pos_ in ("NOUN", "PROPN") and (is_boundary_device(host) or host.lemma_.lower() in R16.BOUNDARY_NOUNS):
        boundary = True  # 'door of X', '<device> at X'
    if fp in ("at", "of", "by", "outside") and pp_on_pred:
        for c in pred.children:
            if c.dep_ == "dobj" and is_boundary_device(c):
                boundary = True
            if c.dep_ == "prep" and c.i != pp.i and any(g.dep_ == "pobj" and is_boundary_device(g) for g in c.children):
                boundary = True
    if boundary:
        if role in BIND_ROLES_SENTINEL or role in ("UNKNOWN", "DESTINATION"):
            setr("BOUNDARY_INTERACTION", "UNKNOWN", "UNKNOWN", "BOUNDARY_SITE", BOUNDARY_RELATION="BOUNDARY_INTERACTION",
                 CURRENT_OCCUPANCY_EVIDENCE=False, COMPLETED_TRAVERSAL_EVIDENCE=False)
        return out

    # (11) perception / deictic target: decided by the location phrase's dependency role
    if fp in TARGET_PREPS and (pp_on_pred or pp_on_obj):
        if _excluded_class(pred) or (obj is None and et.startswith("ACTIVITY")) or \
                (obj is not None and (R16._lemma_forms(obj) & (R16.PERCEPTION_LEMMAS | R16.DIRECTED_AT_LEMMAS)
                                      or any(c.dep_ == "poss" for c in obj.children))):
            if role in BIND_ROLES_SENTINEL or role == "UNKNOWN":
                setr("DEICTIC_TARGET", "UNKNOWN", "UNKNOWN", "UNKNOWN", CURRENT_OCCUPANCY_EVIDENCE=False)
            return out
    if fp in ("toward", "towards") and role == "CURRENT_SITE":
        setr("DEICTIC_TARGET", "UNKNOWN", "UNKNOWN", "UNKNOWN", CURRENT_OCCUPANCY_EVIDENCE=False)
        return out
    # approach: particle + on/at ('homing in on X')
    if fp in ("on", "at") and obj is None and pp_on_pred and any(
            c.dep_ in ("prt", "advmod") and c.lower_ in APPROACH_PARTICLES and c.i < pp.i for c in pred.children):
        setr("APPROACH_TARGET", "IN_PROGRESS", "UNKNOWN", "DESTINATION", CURRENT_OCCUPANCY_EVIDENCE=False)
        return out
    # (10) object reference: PP modifies an object with a non-containment relation, or transfer/placement + object
    if pp_on_obj and fp not in OBJ_CONTAINMENT_PREPS and fp != "at" and obj.lemma_.lower() != WAY_CONSTRUCTION_NOUN \
            and not et.startswith("ACCESS"):
        if role in BIND_ROLES_SENTINEL or role == "UNKNOWN":
            # an object's destination PP ('a pass for X') stays open to later same-subject completion
            setr("OBJECT_REFERENCE_DEST" if fp in R16.DEST_PREPS else "OBJECT_REFERENCE", "UNKNOWN", "UNKNOWN", "UNKNOWN",
                 CURRENT_OCCUPANCY_EVIDENCE=False)
        return out
    if obj is not None and fp == "on" and role == "CURRENT_SITE" and et.startswith("ACTIVITY"):
        setr("OBJECT_REFERENCE", "UNKNOWN", "UNKNOWN", "UNKNOWN", CURRENT_OCCUPANCY_EVIDENCE=False)
        return out
    if obj is not None and pred.lemma_.lower() in (R16.LIGHT_LEMMAS | R16.PLACEMENT_LEMMAS) and et.startswith("ACTIVITY"):
        setr("OBJECT_REFERENCE", "UNKNOWN", "UNKNOWN", "UNKNOWN", CURRENT_OCCUPANCY_EVIDENCE=False)
        return out

    way = any(c.dep_ == "dobj" and c.lemma_.lower() == WAY_CONSTRUCTION_NOUN for c in pred.children)
    if not out.get("SUBJECT_CHARACTER_ID") and not (rec.get("SUBJECT_TEXT") or "").strip():
        s0 = _subj(pred)
        if s0 is not None and s0.lower_ not in R16.PERSONAL_PRON and R16._is_char_subject(s0, ctx):
            out["SUBJECT_CHARACTER_ID"] = _char_key(s0, ctx)
    if role in BIND_ROLES_SENTINEL:
        return out
    if way and fp in CROSSING_PREPS and not rec.get("NEGATED") and _chain_realis(pred) and \
            R16._is_char_subject(_subj(pred), ctx):  # 'fought/talked her way inside X' entails arrival
        setr("STRUCTURAL_MOTION_REALIZATION", "COMPLETED", "SUCCESS", "SUCCESSFUL_DESTINATION",
             COMPLETED_TRAVERSAL_EVIDENCE=True, EVENT_TYPE="TRAVERSAL")
        return out
    if rec.get("NEGATED") or rec.get("EVENT_STATE") in ("FAILED", "PLANNED", "PENDING", "ATTEMPTED", "IN_PROGRESS", "DEPARTED"):
        return out
    if et in ("DEPARTURE", "PROXIMITY", "MOTION_NONCHARACTER", "PERCEPTION_COMMUNICATION_MEMORY"):
        return out
    subj = _subj(pred)
    serial = _serial(pred)
    if not R16._is_char_subject(subj, ctx) or not _chain_realis(pred) or (_excluded_class(pred) and not serial):
        return out
    if subj is not None:  # the upgraded event belongs to its own structural subject
        if subj.lower_ in R16.PERSONAL_PRON:
            rr = R16._resolve_pronoun(subj, ctx)
            out["SUBJECT_CHARACTER_ID"] = _char_key(rr, ctx) if rr is not None else R16.UNRESOLVED
        else:
            k = _char_key(subj, ctx)
            if k:
                out["SUBJECT_CHARACTER_ID"] = k
    progressive = pred.tag_ == "VBG" and any(x.lemma_.lower() == "be" for x in R16._aux(pred))
    passive = any(c.dep_ in ("auxpass", "nsubjpass") for c in pred.children)
    # (12) structural motion realization
    if fp in CROSSING_PREPS and (pp_on_pred or (way and pp_on_obj)) and (obj is None or way) and not progressive and not passive:
        setr("STRUCTURAL_MOTION_REALIZATION", "COMPLETED", "SUCCESS", "SUCCESSFUL_DESTINATION",
             COMPLETED_TRAVERSAL_EVIDENCE=True, EVENT_TYPE="TRAVERSAL")
        return out
    # (9) activity locative: containment PP modifying the event (or containment PP on its object)
    if et in ("MOTION",) and fp == "on":
        return out
    if (fp in (CONTAINMENT_PREPS if (obj is None or (pred.tag_ == "VBG" and pred.dep_ != "ROOT")) else OBJ_CONTAINMENT_PREPS) and (pp_on_pred or (pp_on_obj and fp in OBJ_CONTAINMENT_PREPS))) or \
            (fp == "at" and (pp_on_pred or pp_on_obj) and obj is not None):
        if not progressive or pred.dep_ != "ROOT":
            setr("ACTIVITY_LOCATION_COMPOSITION", "CURRENT", "NONE", "CURRENT_SITE", CURRENT_OCCUPANCY_EVIDENCE=True,
                 EVENT_TYPE="ACTIVITY_OCCUPANCY")
            return out
    return out


# ---------------------------------------------------------------- location-less events for composition
def _directional_completion(v, ctx) -> bool:
    if not (R16._is_verbal(v) or v.dep_ in ("ROOT", "conj")):
        return False
    if not _chain_realis(v):
        return False
    if v.tag_ == "VBG" and v.dep_ not in ("pcomp", "advcl", "xcomp", "dep") and not _serial(v):
        return False
    for c in v.children:
        if c.dep_ == "dobj" and not c.lower_.endswith(("self", "selves")):
            return False
    for c in v.children:  # small clause 'let [herself inside]'
        if c.dep_ in ("ccomp", "xcomp", "oprd") and c.lower_ in DIRECTIONAL_PARTICLES and \
                any(g.dep_ == "nsubj" and g.lower_.endswith(("self", "selves")) for g in c.children) and \
                not any(g.dep_ == "pobj" for g in c.children):
            return True
    for c in v.children:
        if c.lower_ in DIRECTIONAL_PARTICLES and c.dep_ in ("prt", "advmod", "prep"):
            pobj = [g for g in c.children if g.dep_ == "pobj"]
            if not pobj:
                return True
            if c.lower_ in CROSSING_PREPS and all(g.lemma_.lower() in R16.BOUNDARY_NOUNS for g in pobj):
                return True
    return False


def _failure_events(sent, ctx) -> List[Tuple[Any, str]]:
    out = []
    seen = set()
    for fv, fs in R16._failure_events(sent):
        if fs is not None:
            rr = R16._resolve_pronoun(fs, ctx) if fs.lower_ in R16.PERSONAL_PRON else fs
            k = _char_key(rr, ctx).lower() if rr is not None else R16.UNRESOLVED.lower()
        else:
            k = _subject_key(fv, ctx)
        out.append((fv, k))
        seen.add(fv.i)
    for t in sent:  # passive displacement ('was shooed away', 'was marched back out')
        if t.i not in seen and any(c.dep_ == "auxpass" for c in t.children) and \
                any(c.dep_ in ("advmod", "prt") and c.lower_ in DISPLACEMENT_PARTICLES for c in t.children):
            out.append((t, _subject_key(t, ctx)))
    return out


# ---------------------------------------------------------------- graph from original dependencies
def _build_graph(sent, ctx, srecs) -> Dict[str, Any]:
    heads = [t for t in sent if t.dep_ in CLAUSE_DEPS and (R16._is_verbal(t) or any(c.dep_ in ("nsubj", "nsubjpass") for c in t.children))]
    nodes, edges = [], []
    keys = {}
    for h in heads:
        nodes.append(("CLAUSE", h.i))
        nodes.append(("EVENT", h.i))
        s = R16._subject_of(h)
        if s is not None:
            nodes.append(("SUBJECT", s.i))
            edges.append((s.i, h.i, "SUBJECT_OF"))
        keys[h.i] = _subject_key(h, ctx)
        if h.dep_ != "ROOT":
            p = _clause_head(h.head)
            et = _edge_type(h)
            edges.append((h.i, p.i, et))
        for c in h.children:
            if c.dep_ == "xcomp":
                edges.append((c.i, h.i, "CONTROLLED_BY"))
    by_key: Dict[str, List[int]] = {}
    for h in heads:
        if keys[h.i]:
            by_key.setdefault(keys[h.i], []).append(h.i)
    for k, hs in by_key.items():  # chain, not all pairs
        for x, y in zip(hs, hs[1:]):
            edges.append((x, y, "SAME_SUBJECT"))
    by_loc: Dict[str, List[int]] = {}
    for r in srecs:
        nodes.append(("LOCATION", r["_loc_i"]))
        edges.append((r["_loc_i"], r["_head_i"], "LOCATION_OF"))
        by_loc.setdefault(r["CANONICAL_LOCATION"], []).append(r["_loc_i"])
    for k, ls in by_loc.items():
        for x, y in zip(ls, ls[1:]):
            edges.append((x, y, "SAME_LOCATION"))
    return {"NODES": nodes, "EDGES": edges}


def _ungate(r, loc, ctx):
    """Undo R16's depiction gate (R18 re-applies it after composition) and take a non-character R16 subject
    from the event's own structural subject."""
    r = dict(r)
    if r["LOCATION_ROLE"] in ("UNRESOLVED_SUBJECT_SITE", "NONDEPICTED_SUBJECT_SITE") and r.get("SUBJECT_CHARACTER_ID") != R16.UNRESOLVED:
        if r.get("EVENT_STATE") == "COMPLETED":
            r["LOCATION_ROLE"] = "SUCCESSFUL_DESTINATION"
        elif r.get("EVENT_STATE") == "CURRENT":
            r["LOCATION_ROLE"] = "CURRENT_SITE"
    return r


def _reflexive_subject(r, sent, ctx):
    """A reflexive object ('let herself in') denotes its clause's own subject (grammatical binding, not coreference)."""
    st = (r.get("SUBJECT_TEXT") or "").lower()
    if r.get("SUBJECT_CHARACTER_ID") != R16.UNRESOLVED or not st.endswith(("self", "selves")):
        return r
    for t in sent:
        if t.lower_ == st and t.idx < r["START_CHAR"]:
            s = _subj(t.head)
            if s is not None and s.lower_ not in R16.PERSONAL_PRON:
                k = _char_key(s, ctx)
                if k:
                    r = dict(r)
                    r["SUBJECT_CHARACTER_ID"] = k
                    r["SUBJECT_REFLEXIVE_BOUND"] = True
                    if r.get("LOCATION_ROLE") == "UNRESOLVED_SUBJECT_SITE" and r.get("EVENT_STATE") == "COMPLETED":
                        r["LOCATION_ROLE"] = "SUCCESSFUL_DESTINATION"
                    elif r.get("LOCATION_ROLE") == "UNRESOLVED_SUBJECT_SITE" and r.get("EVENT_STATE") == "CURRENT":
                        r["LOCATION_ROLE"] = "CURRENT_SITE"
            break
    return r


# ---------------------------------------------------------------- main entry
def analyze(text: str, *, depicted_characters: Optional[Iterable[str]] = None,
            character_context: Optional[Any] = None, timing: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    cached = text in R16._DOC_CACHE
    doc = R16.parse(text)  # the ONE parse
    t1 = time.perf_counter()
    if doc is None:
        return {"PARSER_AVAILABLE": False, "records": [], "graph": []}
    if not cached:
        STATS["NLP_CALLS"] += 1
        STATS["SENTENCES_PARSED"] += sum(1 for _ in doc.sents)
    dep = list(depicted_characters) if depicted_characters is not None else None
    ctx = R16._Ctx(dep, character_context)
    full = R16.analyze_doc(doc, depicted_characters=dep, character_context=character_context)
    by_end = {r["END_CHAR"]: r for r in full}
    final: List[Dict[str, Any]] = []
    sents = list(doc.sents)
    for s_i, sent in enumerate(sents):
        for tok in sent:
            r = by_end.get(tok.idx + len(tok.text))
            if r is None or r["HEAD"] != tok.lower_:
                continue
            head = _clause_head(tok)
            realis, path = _context_realis(head)
            r = _ungate(r, tok, ctx)
            r = _reflexive_subject(r, sent, ctx)
            rec = _revise(tok, r, ctx)
            rec["CLAUSE_EDGE_PATH"] = path
            rec["CLAUSE_REALIS"] = realis
            if not realis and rec["LOCATION_ROLE"] in BIND_ROLES_SENTINEL:
                rec.update(LOCATION_ROLE="DESTINATION" if rec["LOCATION_ROLE"] == "SUCCESSFUL_DESTINATION" else "UNKNOWN",
                           EVENT_STATE="UNKNOWN", EVENT_RESULT="UNKNOWN", R18_RULE="NONREALIS_CONTEXT")
            rec.update(_loc_i=tok.i, _head_i=head.i, _sent=s_i, SUPERSEDED_BY="")
            final.append(rec)
    graphs = []
    for s_i, sent in enumerate(sents):
        srecs = [r for r in final if r["_sent"] == s_i]
        graphs.append(_build_graph(sent, ctx, srecs))
    t2 = time.perf_counter()
    # ---- composition (per sentence, keyed by subject + canonical location)
    key = lambda r: (r.get("SUBJECT_CHARACTER_ID") or "").lower()
    for s_i, sent in enumerate(sents):
        srecs = [r for r in final if r["_sent"] == s_i]
        if not srecs:
            continue
        by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for r in srecs:
            by_key.setdefault((key(r), r["CANONICAL_LOCATION"]), []).append(r)
        for (k, _loc), grp in by_key.items():  # succession inside one key only
            if not k or k == R16.UNRESOLVED.lower() or len(grp) < 2:
                continue
            for r in grp:
                if r["LOCATION_ROLE"] in ("DESTINATION", "UNKNOWN", "BOUNDARY_SITE") and not r.get("NEGATED") and \
                        r.get("R18_RULE") not in ("DEICTIC_TARGET", "OBJECT_REFERENCE", "NONREALIS_CONTEXT", "BOUNDARY_INTERACTION") and \
                        any(o["_loc_i"] > r["_loc_i"] and o["LOCATION_ROLE"] == "SUCCESSFUL_DESTINATION" for o in grp):
                    r.update(EVENT_STATE="COMPLETED", EVENT_RESULT="SUCCESS", LOCATION_ROLE="SUCCESSFUL_DESTINATION",
                             COMPLETED_TRAVERSAL_EVIDENCE=True, SUPERSEDED_BY="SUCCESSION", R18_RULE="SUCCESSION_COMPOSITION")
        events = []
        for t in sent:
            if t.dep_ in CLAUSE_DEPS | {"pcomp", "xcomp"} and _directional_completion(t, ctx):
                if _context_realis(_clause_head(t))[0] and not any(r["_head_i"] == _clause_head(t).i and
                                                                 t.left_edge.i <= r["_loc_i"] <= t.right_edge.i for r in srecs):
                    events.append(("COMPLETION", t, _subject_key(t, ctx)))
        for fv, k in _failure_events(sent, ctx):
            events.append(("FAILURE", fv, k))
        events.sort(key=lambda x: x[1].i)
        for kind, v, k in events:
            if not k or k == R16.UNRESOLVED.lower():
                continue
            cands = sorted((r for r in srecs if r["_loc_i"] < v.i and key(r) == k), key=lambda r: r["_loc_i"])
            if not cands:
                continue
            tgt = cands[-1]
            between = doc[tgt["_loc_i"] + 1:v.i]
            if any((ctx.char_id(b.text) and ctx.char_id(b.text).lower() != k) or
                   (b.pos_ == "PROPN" and not ctx.char_id(b.text) and b.dep_ in ("conj", "nsubj", "nsubjpass")) or
                   (b.lower_ in R16.PERSONAL_PRON and b.dep_ in ("nsubj", "nsubjpass") and
                    (R16._resolve_pronoun(b, ctx) is None or _char_key(R16._resolve_pronoun(b, ctx), ctx).lower() != k))
                   for b in between):
                continue  # ambiguous clause boundary / competing subject
            if kind == "COMPLETION":
                if tgt["LOCATION_ROLE"] in ("DESTINATION", "UNKNOWN") and not tgt.get("NEGATED") \
                        and tgt.get("EVENT_STATE") not in ("FAILED", "PLANNED", "DEPARTED") \
                        and tgt.get("EVENT_TYPE") not in ("REFERENCE", "DEPARTURE", "PERCEPTION_COMMUNICATION_MEMORY", "PROXIMITY",
                                                          "MOTION_NONCHARACTER") \
                        and tgt.get("R18_RULE") not in ("DEICTIC_TARGET", "OBJECT_REFERENCE", "NONREALIS_CONTEXT", "BOUNDARY_INTERACTION"):
                    tgt.update(EVENT_STATE="COMPLETED", EVENT_RESULT="SUCCESS", LOCATION_ROLE="SUCCESSFUL_DESTINATION",
                               COMPLETED_TRAVERSAL_EVIDENCE=True, SUPERSEDED_BY="COMPLETION:" + v.lemma_.lower(),
                               R18_RULE="DIRECTIONAL_LOCATION_INHERITANCE")
            else:
                if tgt["LOCATION_ROLE"] in ("DESTINATION", "UNKNOWN", "BOUNDARY_SITE", "SUCCESSFUL_DESTINATION") \
                        and tgt.get("R18_RULE") not in ("DEICTIC_TARGET", "OBJECT_REFERENCE", "NONREALIS_CONTEXT"):
                    tgt.update(EVENT_STATE="FAILED", EVENT_RESULT="FAILURE", LOCATION_ROLE="FAILED_DESTINATION",
                               SUPERSEDED_BY="FAILURE:" + v.lemma_.lower(), R18_RULE="FAILURE_COMPOSITION",
                               ACCESS_RELATION=tgt.get("ACCESS_RELATION") or "DENIED")
    # ---- depicted-subject gate, then the single R12 bind decision
    for r in final:
        role = r["LOCATION_ROLE"]
        if r.get("SUBJECT_CHARACTER_ID") == R16.UNRESOLVED:
            r["SUBJECT_IS_DEPICTED"] = "UNKNOWN"
            if role in BIND_ROLES_SENTINEL:
                r["LOCATION_ROLE"] = "UNRESOLVED_SUBJECT_SITE"
        elif ctx.depicted is not None:
            sid = (r.get("SUBJECT_CHARACTER_ID") or "").lower()
            dd = bool(sid) and sid in ctx.depicted
            r["SUBJECT_IS_DEPICTED"] = dd
            if role in BIND_ROLES_SENTINEL and not dd:
                r["LOCATION_ROLE"] = "NONDEPICTED_SUBJECT_SITE" if sid else "UNRESOLVED_SUBJECT_SITE"
        r["FINAL_BIND_ALLOWED"] = _new_bind(r["LOCATION_ROLE"])
        r["FINAL_BIND_REASON"] = "LOCATION_ROLE=" + r["LOCATION_ROLE"]
        for k in ("_loc_i", "_head_i", "_sent"):
            r.pop(k, None)
    t3 = time.perf_counter()
    if timing is not None:
        timing["SPACY_PARSE_MS"] = timing.get("SPACY_PARSE_MS", 0.0) + (t1 - t0) * 1000
        timing["EVENT_GRAPH_BUILD_MS"] = timing.get("EVENT_GRAPH_BUILD_MS", 0.0) + (t2 - t1) * 1000
        timing["EVENT_GRAPH_COMPOSE_MS"] = timing.get("EVENT_GRAPH_COMPOSE_MS", 0.0) + (t3 - t2) * 1000
    return {"PARSER_AVAILABLE": True, "records": final, "graph": graphs, "R18_SHADOW_MODE": True, "PRODUCTION_CUTOVER": False,
            "SPACY_PARSE_COUNT": 0 if cached else 1, "CLAUSE_REPARSE_COUNT": 0}
