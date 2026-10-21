# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_SEMANTIC_EVENT_PARSER_REDIRECT_R15.

Dependency-based semantic event parser for scene-location mentions.

Pipeline: text -> clause parse -> dependency structure -> per-location event
attachment -> event realization -> semantic role -> R12 LOCATION_ROLE.  The
LOCATION_ROLE produced here is consumed by the single existing bind decision in
tools.location_relation_r6.classify (bind_ok = role in _BIND_ROLES).  This
module never decides binding itself and never infers canon.

Core rule UNKNOWN_SEMANTICS_DEFAULT=NEUTRAL: a bindable role (CURRENT_SITE /
SUCCESSFUL_DESTINATION) is produced only on positive structural evidence of
current occupancy or completed traversal by a (depicted, when known) subject.

CPU only.  spaCy en_core_web_sm is loaded ONCE per process with NER disabled.
Model probabilities are never used as bind authority.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

UNKNOWN_SEMANTICS_DEFAULT = "NEUTRAL"
UNRESOLVED = "UNRESOLVED"
UNRESOLVED_PRONOUN_POLICY = "FAIL_NEUTRAL"
MODEL_NAME = "en_core_web_sm"
PARSER_VERSION = "R16.0"

# ---------------------------------------------------------------- model load
_NLP = None
_NLP_LOCK = threading.Lock()
_NLP_ERROR = ""
MODEL_LOAD_COUNT = 0
MODEL_LOAD_SECONDS = 0.0
_DOC_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_DOC_CACHE_MAX = 4096


def get_nlp():
    """Load spaCy once per process (CPU, NER disabled). Returns None if unavailable."""
    global _NLP, _NLP_ERROR, MODEL_LOAD_COUNT, MODEL_LOAD_SECONDS
    if _NLP is not None or _NLP_ERROR:
        return _NLP
    with _NLP_LOCK:
        if _NLP is not None or _NLP_ERROR:
            return _NLP
        try:
            import spacy  # noqa: WPS433
            t0 = time.perf_counter()
            _NLP = spacy.load(MODEL_NAME, disable=["ner"])
            MODEL_LOAD_SECONDS = time.perf_counter() - t0
            MODEL_LOAD_COUNT += 1
        except Exception as exc:  # pragma: no cover - environment dependent
            _NLP_ERROR = repr(exc)
            _NLP = None
    return _NLP


def parser_available() -> bool:
    return get_nlp() is not None


def _cache_put(text: str, doc: Any) -> None:
    _DOC_CACHE[text] = doc
    _DOC_CACHE.move_to_end(text)
    while len(_DOC_CACHE) > _DOC_CACHE_MAX:
        _DOC_CACHE.popitem(last=False)


def parse(text: str):
    nlp = get_nlp()
    if nlp is None:
        return None
    doc = _DOC_CACHE.get(text)
    if doc is None:
        doc = nlp(text)
        _cache_put(text, doc)
    else:
        _DOC_CACHE.move_to_end(text)
    return doc


def parse_batch(texts: Sequence[str], batch_size: int = 64) -> List[Any]:
    """Batch parse with nlp.pipe (cached); returns docs aligned with texts."""
    nlp = get_nlp()
    if nlp is None:
        return [None for _ in texts]
    todo = [t for t in dict.fromkeys(texts) if t not in _DOC_CACHE]
    for t, doc in zip(todo, nlp.pipe(todo, batch_size=batch_size)):
        _cache_put(t, doc)
    return [_DOC_CACHE.get(t) for t in texts]


# ---------------------------------------------------------------- lexicon
def _place_heads() -> frozenset:
    from tools.location_relation_r6 import PLACE_HEADS
    return PLACE_HEADS


OCC_LEMMAS = frozenset("""
station post base spend house lodge quarter trap imprison confine shelter
stand sit wait work remain stay sleep live pace seat lie kneel crouch hide rest linger
reside dwell train study meditate cook eat drink practice labor shelter huddle lounge
sprawl perch squat camp settle occupy patrol guard keep toil kneel lean
""".split())
OCC_PREPS = frozenset("in inside within at on aboard throughout".split())
PROXIMITY_PREPS = frozenset("near beside by nearby alongside".split())
ACTIVITY_PREPS = frozenset("in inside within at on aboard".split())
PERCEPTION_LEMMAS = frozenset("notice see watch glimpse spot observe look view admire gaze stare peer sight spy".split())
COMMUNICATION_LEMMAS = frozenset("say tell talk speak write shout whisper call announce explain".split())
COGNITION_LEMMAS = frozenset("remember recall imagine think dream picture consider wonder know believe".split())
_PLACE_HEADS_EXTRA = frozenset("bus train car ship boat carriage cart truck subway plane airship tram ferry wagon".split())
# (legacy activity list kept for reference only; no longer consulted)
# R15 tighten (3): explicit activity lexicon (non-motion activities performed at a site)
ACTIVITY_LEMMAS = frozenset("""
work collapse seal raise hammer forge smith fight spar duel train practice meditate pray cook eat drink
write study read_in watch observe kneel rest sleep brew craft repair mend clean sweep tend operate type
argue negotiate bargain trade sell shop sing play dance bathe wash dress collapse faint bleed weep cry
""".split())
BOUNDARY_PREPS = frozenset("outside before beside near by alongside beyond behind past around against".split())
DEST_PREPS = frozenset("to toward towards for onto".split())
SOURCE_PREPS = frozenset("from".split())
INTO_PREPS = frozenset("into inside in through within".split())
REF_PREPS = frozenset("about of".split())

TRAVERSE_OBJ_LEMMAS = frozenset("enter reach infiltrate breach".split())
TRAVERSE_INTO_LEMMAS = frozenset("""
enter cross pass step walk move go run slip climb stride stumble hurry burst come duck
march push squeeze crawl drift wander rush dash sprint return get make break limp file
""".split())
ARRIVE_LEMMAS = frozenset("arrive land".split())
RETURN_LEMMAS = frozenset("return".split())
CAUSED_TRAVERSE_LEMMAS = frozenset("admit escort usher lead guide bring let allow show take welcome wave pull drag carry".split())
GAIN_LEMMAS = frozenset("gain win secure obtain".split())
ACCESS_NOUNS = frozenset("entry access admission admittance passage entrance ingress way".split())
BOUNDARY_NOUNS = frozenset("gate gates door doors doorway entrance threshold boundary edge perimeter outskirts lip mouth front wall walls steps".split())
PART_NOUNS = frozenset("floor interior center centre corner depths middle heart inside back length rooms halls".split())
REF_NOUNS = frozenset("""
story stories tale tales legend legends memory memories rumor rumors account accounts report news vision dream
image thought thoughts history chronicle map maps picture photo painting book books description name mention
""".split())
PLAN_NOUNS = frozenset("objective goal assignment target destination plan mission aim task order orders intention purpose milestone mandate priority directive agenda ambition intent".split())
ATTEMPT_NOUNS = frozenset("effort attempt bid try endeavor endeavour".split())
IRREALIS_HEADS = frozenset("likely about ready set due bound going eager poised able unlikely supposed sure certain willing".split())
MOTION_LEMMAS = frozenset("go walk run move head hurry rush drift wander march stride stumble come travel ride drive fly sail climb".split())
REQUEST_NOUNS = frozenset("leave go-ahead license licence authorization authorisation approval clearance permission application request review admission".split())

REFERENCE_LEMMAS = frozenset("""
remember recall talk speak read think dream mention describe hear discuss imagine write know learn picture
tell report repeat wonder reminisce recount study_about
""".split())
DEPART_LEMMAS = frozenset("leave depart flee escape exit abandon vacate evacuate quit".split())
SOURCE_MOTION_LEMMAS = frozenset("come return walk run go move emerge stumble climb step hurry drift arrive".split())
PLAN_CONTROL_LEMMAS = frozenset("plan intend hope want mean aim prepare decide expect wish resolve choose propose arrange need contemplate consider".split())
ATTEMPT_CONTROL_LEMMAS = frozenset("try attempt endeavor endeavour strive struggle seek fight strain".split())
INCHOATIVE_LEMMAS = frozenset("start begin set head make work move close near approach advance edge creep proceed".split())
INCHOATIVE_CONTROL = frozenset("start begin set commence".split())
PERMISSION_LEMMAS = frozenset("clear allow permit authorize authorise grant approve license licence invite".split())
REQUEST_LEMMAS = frozenset("request ask seek await apply petition submit wait_for queue".split())
FAILURE_LEMMAS = frozenset("refuse deny bar block repel stop prevent halt reject forbid lock seal foil thwart rebuff obstruct".split())
FAIL_PARTICLE_LEMMAS = frozenset("turn send drive force push beat wave".split())  # + back/away/off
FAIL_STATE_ADJ = frozenset("blocked sealed closed locked barred shut impassable".split())
SUCCESS_CONTROL = frozenset("manage succeed".split())
FAIL_CONTROL = frozenset("fail".split())
MODAL_LEMMAS = frozenset("would might could may should will shall must can ought".split())
NEG_LEMMAS = frozenset("not never n't no".split())
PERSONAL_PRON = frozenset("he she they him her them i we me us you".split())
CLAUSE_BREAK_DEPS = frozenset("ROOT conj advcl relcl ccomp parataxis csubj acl".split())
_CHAIN_DEPS = frozenset("xcomp pcomp prep pobj dobj attr oprd".split())

EVENT_STATES = ("CURRENT", "COMPLETED", "IN_PROGRESS", "PLANNED", "ATTEMPTED", "PENDING",
                "FAILED", "REFERENCE", "DEPARTED", "UNKNOWN")
EVENT_RESULTS = ("SUCCESS", "FAILURE", "UNKNOWN", "NONE")
CONFIDENCE_CLASSES = ("STRUCTURAL_HIGH", "STRUCTURAL_PARTIAL", "UNKNOWN")


# ---------------------------------------------------------------- helpers
def _norm_loc(text: str) -> str:
    from tools.location_relation_r6 import _normalize_loc
    return _normalize_loc(text.replace("\u2019", "'"))


def _is_place_tok(tok) -> bool:
    if tok.pos_ not in ("NOUN", "PROPN"):
        return False
    heads = _place_heads()
    t = tok.text.lower()
    lem = tok.lemma_.lower()
    heads = heads | _PLACE_HEADS_EXTRA
    return t in heads or lem in heads or (t.endswith("s") and t[:-1] in heads)


def _mention_span(tok) -> Tuple[int, int]:
    """Head + left modifiers (compound/amod/poss/nmod) -> (start_char, end_char)."""
    left = tok
    for c in tok.lefts:
        if c.dep_ in ("compound", "amod", "poss", "nmod", "nummod") or (c.dep_ == "det" and False):
            if c.i < left.i:
                left = c
    # include possessive marker subtree for poss (Mira 's apartment)
    start = min(t.idx for t in left.subtree if t.i <= tok.i and t.dep_ != "det") if left is not tok else tok.idx
    return start, tok.idx + len(tok.text)


def _has_neg(tok) -> bool:
    for c in tok.children:
        if c.dep_ == "neg" or c.lower_ in ("never", "not", "n't", "nowhere"):
            return True
        if c.dep_ == "det" and c.lower_ == "no":
            return True
    return False


def _aux(tok) -> List[Any]:
    return [c for c in tok.children if c.dep_ in ("aux", "auxpass")]


def _subject_of(tok):
    for c in tok.children:
        if c.dep_ in ("nsubj", "nsubjpass", "expl"):
            return c
    return None


def _is_verbal(tok) -> bool:
    return tok.pos_ in ("VERB", "AUX")


def _particles(tok) -> List[str]:
    return [c.lower_ for c in tok.children if c.dep_ in ("prt", "advmod")]


class _Ctx:
    def __init__(self, depicted: Optional[Iterable[str]], characters: Optional[Any]):
        self.name_to_id: Dict[str, str] = {}
        if isinstance(characters, dict):
            items = list(characters.items())
            for cid, val in items:
                names: List[str] = []
                if isinstance(val, dict):
                    names = [str(val.get("name") or "")] + [str(a) for a in (val.get("aliases") or [])]
                elif isinstance(val, (list, tuple)):
                    names = [str(v) for v in val]
                else:
                    names = [str(val)]
                for n in names + [str(cid)]:
                    if n.strip():
                        self.name_to_id[n.strip().lower()] = str(cid)
        elif characters:
            for c in characters:
                if isinstance(c, dict):
                    cid = str(c.get("id") or c.get("name") or "")
                    for n in [c.get("name")] + list(c.get("aliases") or []):
                        if n:
                            self.name_to_id[str(n).strip().lower()] = cid
                else:
                    self.name_to_id[str(c).strip().lower()] = str(c).strip()
        self.depicted: Optional[set] = None
        if depicted is not None:
            self.depicted = set()
            for d in depicted:
                d = str(d).strip()
                if not d:
                    continue
                self.depicted.add(d.lower())
                cid = self.name_to_id.get(d.lower())
                if cid:
                    self.depicted.add(cid.lower())

    def char_id(self, text: str) -> str:
        t = (text or "").strip().lower()
        if not t:
            return ""
        if t in self.name_to_id:
            return self.name_to_id[t]
        return ""


# ---------------------------------------------------------------- core
def _clause_root(tok):
    cur = tok
    guard = 0
    while cur.dep_ not in CLAUSE_BREAK_DEPS and cur.head.i != cur.i and guard < 40:
        cur = cur.head
        guard += 1
    return cur


def _governing(loc):
    """Return (prep, nominal_chain, verb, path) for the location head token."""
    prep = ""
    nominal: List[Any] = []
    path: List[Any] = []
    cur = loc
    guard = 0
    # coordinated location: 'the hall and the forge' -> use first conjunct attachment
    while cur.dep_ == "conj" and cur.head.pos_ in ("NOUN", "PROPN") and guard < 5:
        cur = cur.head
        guard += 1
    while guard < 30:
        guard += 1
        h = cur.head
        if h.i == cur.i:
            return prep, nominal, None, path
        path.append(h)
        if cur.dep_ in ("pobj",) and h.dep_ in ("prep", "agent") or (h.pos_ == "ADP"):
            if not prep:
                prep = h.lower_
            elif nominal == [] and h.lower_ in ("into", "inside", "within"):
                prep = h.lower_
            cur = h
            continue
        if cur.dep_ == "prep" and h.pos_ == "ADV" and h.lower_ in ("inside", "outside", "out", "back", "away"):
            prep = h.lower_ + ("_" + prep if prep else "")
            cur = h
            continue
        if _is_verbal(h):
            return prep, nominal, h, path
        if h.pos_ in ("NOUN", "PROPN", "PRON", "ADJ", "ADV", "NUM"):
            if h.pos_ in ("NOUN", "PROPN"):
                nominal.append(h)
            cur = h
            continue
        cur = h
    return prep, nominal, None, path


def _control_chain(verb) -> List[Any]:
    """Verb chain from the governing verb up to its clause head (xcomp/pcomp links)."""
    chain = [verb]
    cur = verb
    guard = 0
    while guard < 8:
        guard += 1
        if cur.dep_ in ("xcomp",) and _is_verbal(cur.head):
            cur = cur.head
            chain.append(cur)
            continue
        if cur.dep_ in ("pcomp",) and cur.head.pos_ == "ADP" and _is_verbal(cur.head.head):
            cur = cur.head.head
            chain.append(cur)
            continue
        if cur.dep_ in ("csubj", "csubjpass") and _is_verbal(cur.head):
            chain.append(cur.head)
            break
        break
    return chain


def _resolve_subject(verb_chain: List[Any], ctx: _Ctx) -> Tuple[Any, str]:
    """Return (subject token, role) where role in {'subj','obj_traverser'}."""
    for v in verb_chain:
        s = _subject_of(v)
        if s is not None:
            return s, "subj"
    # conj inherits subject of first conjunct
    top = verb_chain[-1]
    cur = top
    guard = 0
    while cur.dep_ == "conj" and guard < 6:
        cur = cur.head
        guard += 1
        s = _subject_of(cur)
        if s is not None:
            return s, "subj"
        for v in _control_chain_down(cur):
            s = _subject_of(v)
            if s is not None:
                return s, "subj"
    # advcl / infinitival complement of a noun or adjective: nearest governing verb with a subject
    cur = top
    guard = 0
    while cur.head.i != cur.i and guard < 12:
        guard += 1
        cur = cur.head
        if _is_verbal(cur):
            s = _subject_of(cur)
            if s is not None:
                return s, "governing_subj"
        if cur.dep_ in ("relcl", "ccomp", "parataxis"):
            break
    return None, ""


def _control_chain_down(v) -> List[Any]:
    return [v]


def _subject_text(tok) -> str:
    if tok is None:
        return ""
    if tok.pos_ == "PROPN":
        parts = [c for c in tok.lefts if c.dep_ == "compound" and c.pos_ == "PROPN"] + [tok]
        return " ".join(p.text for p in parts)
    return tok.text


def _resolve_pronoun(pron, ctx: _Ctx):
    """Pronoun -> nearest governing subject (walk up heads; then earlier sentences)."""
    cur = pron.head
    # an object pronoun ('admitted him') never resolves to the agent of its own verb
    if pron.dep_ not in ("nsubj", "nsubjpass") and _is_verbal(cur) and cur.head.i != cur.i:
        cur = cur.head
    guard = 0
    seen = set()
    while guard < 30:
        guard += 1
        if _is_verbal(cur):
            s = _subject_of(cur)
            if s is not None and s.i != pron.i and s.lower_ not in PERSONAL_PRON and s.pos_ in ("PROPN", "NOUN"):
                if s.i not in seen and (s.pos_ == "PROPN" or ctx.char_id(s.text)):
                    return s
            seen.add(cur.i)
        if cur.head.i == cur.i:
            break
        cur = cur.head
    # previous sentences: nearest preceding nsubj PROPN
    doc = pron.doc
    prev = [sn for sn in doc.sents if sn.end <= pron.sent.start]
    for sn in reversed(prev):
        subs = [t for t in sn if t.dep_ in ("nsubj", "nsubjpass") and t.pos_ == "PROPN"]
        subs += [c for t in subs for c in t.children if c.dep_ == "conj" and c.pos_ == "PROPN"]
        if not subs:
            continue
        names = {_subject_text(t).lower() for t in subs}
        return subs[0] if len(names) == 1 else None
    return None


def _event_frame(loc, ctx: _Ctx) -> Dict[str, Any]:
    prep, nominal, verb, path = _governing(loc)
    first_prep = loc.head.lower_ if loc.dep_ == "pobj" else ""
    rec: Dict[str, Any] = {
        "FIRST_PREP": first_prep,
        "PREPOSITION": prep,
        "NOMINAL_CHAIN": [n.lemma_.lower() for n in nominal],
    }
    nom_lemmas = [n.lemma_.lower() for n in nominal]
    nom_texts = [n.lower_ for n in nominal]
    if verb is None:
        rec.update(PREDICATE="", chain=[], verb=None, nominal_tokens=nominal)
        return rec
    rec["nominal_tokens"] = nominal
    chain = _control_chain(verb)
    rec["verb"] = verb
    rec["chain"] = chain
    lemma = verb.lemma_.lower()
    chain_lemmas = [v.lemma_.lower() for v in chain]
    auxes = [a for v in chain for a in _aux(v)]
    rec["PREDICATE"] = verb.lemma_.lower()
    rec["AUXILIARIES"] = [a.lower_ for a in auxes]
    negated = any(_has_neg(v) for v in chain) or any(_has_neg(t) for t in path if t.i != verb.i) \
        or any(_has_neg(n) for n in nominal)
    # R16 P6 cessation: 'no longer', 'not ... anymore', 'ceased to', 'stopped <V>ing' negate the clause
    cess = False
    for v in chain:
        for c in v.children:
            if c.lower_ == "longer" and any(g.lower_ == "no" for g in c.children):
                cess = True
            if c.lower_ in CESSATION_ADVS:
                cess = True
            if c.lower_ in ("anymore",) or (c.lower_ == "more" and any(g.lower_ == "any" for g in c.children)):
                cess = True
    if any(v.lemma_.lower() in CESSATION_CONTROL for v in chain[1:]):
        cess = True
    rec["CESSATION"] = cess
    negated = negated or cess
    rec["NEGATED"] = negated
    # tense / aspect
    tags = [verb.tag_] + [a.tag_ for a in auxes]
    tense = "UNKNOWN"
    top = chain[-1]
    top_aux = _aux(top)
    tt = [top.tag_] + [a.tag_ for a in top_aux]
    if any(a.lemma_.lower() in ("will", "shall") for a in auxes):
        tense = "FUTURE"
    elif "VBD" in tt:
        tense = "PAST"
    elif any(t in ("VBZ", "VBP") for t in tt):
        tense = "PRESENT"
    elif top.tag_ == "VBN" and top_aux:
        tense = "PAST"
    aspect = "SIMPLE"
    if verb.tag_ == "VBG" and any(a.lemma_.lower() == "be" for a in _aux(verb)):
        aspect = "PROGRESSIVE"
    elif any(a.lemma_.lower() == "have" for a in auxes):
        aspect = "PERFECT"
    rec["TENSE"] = tense
    rec["ASPECT"] = aspect
    modal = [a.lower_ for a in auxes if a.tag_ == "MD" or a.lemma_.lower() in MODAL_LEMMAS]
    rec["MODALITY"] = modal[0].upper() if modal else ("CONTROL_" + chain_lemmas[-1].upper() if len(chain) > 1 else "REALIS")
    rec["chain_lemmas"] = chain_lemmas
    rec["nom_lemmas"] = nom_lemmas
    rec["nom_texts"] = nom_texts
    rec["modal"] = bool(modal) and not (len(modal) == 1 and modal[0] in ("could", "can") and tense == "PAST" and False)
    passive = any(c.dep_ in ("nsubjpass", "auxpass") for c in verb.children)
    rec["passive"] = passive
    rec["particles"] = [p for v in chain for p in _particles(v)]
    has_to = any(c.dep_ == "aux" and c.tag_ == "TO" for c in top.children)
    rec["infinitive"] = bool(has_to and (not _is_verbal(top.head) or top.dep_ in ("acl", "csubj", "advcl", "relcl")))
    rec["inf_head"] = top.head.lemma_.lower() if rec["infinitive"] else ""
    # described (non-realized) event: gerund / infinitive / event-nominal as subject of a predicate
    described = None
    if top.dep_ in ("csubj", "csubjpass") or (top.tag_ == "VBG" and top.dep_ in ("nsubj", "nsubjpass")):
        described = top.head
    elif nominal and nominal[-1].dep_ in ("nsubj", "nsubjpass") and nominal[-1].head.i == verb.i:
        described = verb
    if described is None and top.tag_ == "VBG" and top.dep_ == "ROOT" and _subject_of(top) is None \
            and not _aux(top) and any(t.lemma_.lower() in PLAN_NOUNS for t in top.subtree):
        described = top
    rec["described_by"] = described
    return rec




def _classify(loc, fr: Dict[str, Any], ctx: _Ctx) -> Dict[str, Any]:
    verb = fr.get("verb")
    prep = fr.get("PREPOSITION") or ""
    noms = fr.get("nom_lemmas") or []
    out = {
        "EVENT_TYPE": "UNKNOWN", "EVENT_STATE": "UNKNOWN", "EVENT_RESULT": "UNKNOWN",
        "LOCATION_ROLE": "UNKNOWN", "BOUNDARY_RELATION": "", "ACCESS_RELATION": "",
        "CURRENT_OCCUPANCY_EVIDENCE": False, "COMPLETED_TRAVERSAL_EVIDENCE": False,
        "PARSER_CONFIDENCE_CLASS": "UNKNOWN", "SOURCE_LOCATION": "", "DESTINATION_LOCATION": "",
        "traverser": None,
    }

    def setv(et, st, res, role, conf="STRUCTURAL_HIGH"):
        out.update(EVENT_TYPE=et, EVENT_STATE=st, EVENT_RESULT=res, LOCATION_ROLE=role,
                   PARSER_CONFIDENCE_CLASS=conf)

    contain = fr.get("FIRST_PREP") in ("inside", "within", "into")
    if not contain and (any(n in BOUNDARY_NOUNS for n in noms) or prep in BOUNDARY_PREPS or prep.startswith("outside")):
        out["BOUNDARY_RELATION"] = (prep if prep in BOUNDARY_PREPS or prep.startswith("outside") else
                                    next(n for n in noms if n in BOUNDARY_NOUNS))
    if any(n in ACCESS_NOUNS for n in noms):
        out["ACCESS_RELATION"] = next(n for n in noms if n in ACCESS_NOUNS)

    # Location as subject: 'X remained the objective'
    if loc.dep_ in ("nsubj", "nsubjpass") and verb is not None:
        attrs = [c for c in verb.children if c.dep_ in ("attr", "acomp", "oprd")]
        if any(a.lemma_.lower() in PLAN_NOUNS for a in attrs):
            setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
            return out
        setv("DESCRIPTION", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN")
        return out
    if verb is None:
        # verbless small clause: '<Character> on the skybridge' / '<Character> at the anvil in the forge'
        sc = _small_clause_subject(loc)
        if False and sc is not None and fr.get("FIRST_PREP") in OCC_PREPS | {"inside", "within"} \
                and not any(n in BOUNDARY_NOUNS | REF_NOUNS | PLAN_NOUNS | ACCESS_NOUNS | REQUEST_NOUNS for n in noms) \
                and not out["BOUNDARY_RELATION"]:
            setv("OCCUPANCY_SMALL_CLAUSE", "CURRENT", "NONE", "CURRENT_SITE", "STRUCTURAL_PARTIAL")
            out["CURRENT_OCCUPANCY_EVIDENCE"] = True
            out["small_clause_subject"] = sc
            return out
        # R15 tighten (2): no predicate -> no structural occupancy evidence -> UNKNOWN
        setv("VERBLESS" if sc is not None else "UNATTACHED", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN")
        out["small_clause_subject"] = sc
        return out

    chain = fr["chain"]
    lem = verb.lemma_.lower()
    cl = fr["chain_lemmas"]
    upper = set(cl[1:])
    parts = set(fr.get("particles") or [])
    top = chain[-1]

    # gerund / clause as subject of plan copula: 'entering X remained the assignment'
    for v in chain:
        if v.dep_ in ("csubj", "csubjpass") or (v.dep_ in ("nsubj",) and v.tag_ == "VBG"):
            attrs = [c for c in v.head.children if c.dep_ in ("attr", "acomp", "oprd")]
            if any(a.lemma_.lower() in PLAN_NOUNS for a in attrs) or v.head.lemma_.lower() in PLAN_CONTROL_LEMMAS:
                setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
                return out
    # described events (gerund / infinitive / event nominal as subject) are never realized
    desc = fr.get("described_by")
    if desc is not None:
        sub = {t.lemma_.lower() for t in desc.subtree}
        if sub & PLAN_NOUNS or desc.lemma_.lower() in PLAN_CONTROL_LEMMAS:
            setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
        else:
            setv("DESCRIBED_EVENT", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        return out
    # 'served as Kael's assignment' / 'filed as the target'
    as_plan = any(c.dep_ == "prep" and c.lower_ == "as" and any(g.lemma_.lower() in PLAN_NOUNS for g in c.subtree)
                  for v in chain for c in v.children)
    # plan noun attachment: 'the objective was X' / 'plan for X'
    if as_plan or any(n in PLAN_NOUNS for n in noms):
        setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
        return out

    # ---- R16 P5: clause reported under a communication/cognition verb ('said that he was in X') is reference
    rep_head = top.head if top.dep_ == "ccomp" else None
    if rep_head is not None and _is_verbal(rep_head) and rep_head.lemma_.lower() in (
            COMMUNICATION_LEMMAS | COGNITION_LEMMAS | REFERENCE_LEMMAS | PERCEPTION_LEMMAS) or (rep_head is not None and _is_verbal(rep_head) and any(c.dep_ == "mark" and c.lower_ in ("that", "whether", "if") for c in top.children)):
        setv("REPORTED_CLAUSE", "REFERENCE", "NONE", "REFERENCE_SITE", "STRUCTURAL_PARTIAL")
        return out
    # ---- R15 tighten (1): proximity ('near', 'beside', 'by', 'next to', 'close to') is never occupancy
    fp0 = fr.get("FIRST_PREP") or ""
    prox = fp0 in PROXIMITY_PREPS or (fp0 in ("to", "by") and loc.head.head.lower_ in ("next", "close", "close-by"))
    if prox and not fr.get("NEGATED"):
        setv("PROXIMITY", "UNKNOWN", "UNKNOWN", "UNKNOWN", "STRUCTURAL_PARTIAL")
        out["BOUNDARY_RELATION"] = "PROXIMITY"
        return out
    # ---- negation (P11)
    if fr.get("NEGATED"):
        if lem in REFERENCE_LEMMAS:
            setv("REFERENCE", "REFERENCE", "NONE", "REFERENCE_SITE")
        else:
            setv("NEGATED_EVENT", "FAILED", "FAILURE", "FAILED_DESTINATION")
        return out
    # ---- explicit failure control: failed to enter X
    if upper & FAIL_CONTROL:
        setv("TRAVERSAL", "FAILED", "FAILURE", "FAILED_DESTINATION")
        return out
    # ---- modal / plan (P12)
    if fr.get("modal") or (upper & PLAN_CONTROL_LEMMAS) or (lem in PLAN_CONTROL_LEMMAS and not prep):
        setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
        return out
    # ---- infinitival complement of a non-verbal head: 'permission to enter X', 'likely to enter X'
    if fr.get("infinitive"):
        ih = fr.get("inf_head") or ""
        ihead = fr["chain"][-1].head if fr.get("chain") else None
        ih_req = ihead is not None and (ih in PERMISSION_LEMMAS | REQUEST_LEMMAS or any(c.dep_ == "dobj" and c.lemma_.lower() in REQUEST_NOUNS for c in ihead.children))
        if ih in REQUEST_NOUNS or ih_req:
            setv("ACCESS_REQUEST", "PENDING", "UNKNOWN", "DESTINATION")
        elif ih in ATTEMPT_NOUNS:
            setv("ATTEMPT", "ATTEMPTED", "UNKNOWN", "DESTINATION")
        elif ih in IRREALIS_HEADS or ih in PLAN_NOUNS:
            setv("PLAN", "PLANNED", "UNKNOWN", "PLANNED_SITE")
        else:
            setv("IRREALIS", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    # ---- reference (P11): the location is the content (object / about / of), not the activity site
    ref_content = loc.dep_ in ("dobj", "attr") or prep in REF_PREPS or fr.get("FIRST_PREP") in REF_PREPS
    if ((lem in REFERENCE_LEMMAS or (upper & REFERENCE_LEMMAS)) and ref_content) or any(n in REF_NOUNS for n in noms):
        setv("REFERENCE", "REFERENCE", "NONE", "REFERENCE_SITE")
        return out
    # ---- departure (P11)
    if lem in DEPART_LEMMAS or prep in SOURCE_PREPS or prep in ("out", "out_of") or prep.startswith("out_") or prep.startswith("away") \
            or (prep == "of" and "out" in parts):
        setv("DEPARTURE", "DEPARTED", "NONE", "SOURCE")
        out["SOURCE_LOCATION"] = "SELF"
        return out
    # ---- failure (P10)
    is_fail = (lem in FAILURE_LEMMAS and not (lem in ("seal", "lock") and fr.get("FIRST_PREP") in ("inside", "within", "in"))) \
        or (lem == "turn" and "aside" in parts) or (lem in FAIL_PARTICLE_LEMMAS and parts & {"back", "away", "off"})
    if is_fail:
        setv("ACCESS", "FAILED", "FAILURE", "FAILED_DESTINATION")
        out["ACCESS_RELATION"] = out["ACCESS_RELATION"] or "DENIED"
        return out
    # ---- pending / request / authorization (P6)
    if lem in REQUEST_LEMMAS or (upper & REQUEST_LEMMAS) or (upper & PERMISSION_LEMMAS) or any(n in REQUEST_NOUNS for n in noms) \
            or any(c.dep_ in ("dobj", "nsubjpass") and c.lemma_.lower() in REQUEST_NOUNS for v in chain[1:] for c in v.children) \
            or (lem == "wait" and prep == "for") or lem in ("grant", "authorize", "clear", "approve", "permit"):
        setv("ACCESS_REQUEST", "PENDING", "UNKNOWN", "DESTINATION")
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    # ---- attempt (P7)
    # R16: testing verbs are access attempts only when they target the location/access itself
    # ('tested the passage into X', 'probed the gate of X'), not an activity object ('checked the readouts in X').
    test_access = lem in ("test", "probe", "check", "assess", "verify", "evaluate", "inspect", "examine") and (
        loc.dep_ == "dobj" or any(n in ACCESS_NOUNS | BOUNDARY_NOUNS for n in noms)
        or (fr.get("FIRST_PREP") or "") in ("into", "through", "to", "toward", "towards"))
    if (upper & ATTEMPT_CONTROL_LEMMAS) or lem in ATTEMPT_CONTROL_LEMMAS or test_access:
        setv("ATTEMPT", "ATTEMPTED", "UNKNOWN", "DESTINATION")
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    # ---- inchoative / in-progress (P7)
    if (upper & INCHOATIVE_CONTROL) or (lem in INCHOATIVE_LEMMAS and (prep in DEST_PREPS or not prep or prep in ("in",) and lem == "set")) \
            or prep in ("toward", "towards") or (lem in ("make", "head") and prep == "for") \
            or any(v.dep_ == "pcomp" and v.head.lower_ in ("toward", "towards") for v in chain) \
            or (lem in ("approach", "near") ):
        setv("MOTION", "IN_PROGRESS", "UNKNOWN", "DESTINATION")
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    # ---- boundary only (outside / before / gate of X) cannot bind X
    crossing = lem in ("cross", "pass", "clear", "breach") and bool(noms) and noms[-1] in BOUNDARY_NOUNS and prep == "of"
    if crossing and not fr.get("modal"):
        setv("TRAVERSAL", "COMPLETED", "SUCCESS", "SUCCESSFUL_DESTINATION")
        out["COMPLETED_TRAVERSAL_EVIDENCE"] = True
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    if out["BOUNDARY_RELATION"] and not (prep in INTO_PREPS and lem in TRAVERSE_INTO_LEMMAS | CAUSED_TRAVERSE_LEMMAS | {"enter"}):
        if lem in OCC_LEMMAS or lem == "be":
            setv("OCCUPANCY_BOUNDARY", "CURRENT", "NONE", "BOUNDARY_SITE", "STRUCTURAL_PARTIAL")
        else:
            setv("BOUNDARY", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        return out
    progressive = fr.get("ASPECT") == "PROGRESSIVE"
    # ---- completed traversal (P5)
    trav = False
    kids = {c.lower_ for c in verb.children}
    inside_kid = loc.dep_ == "dobj" and loc.head.i == verb.i and any(
        c.lower_ in ("inside", "into", "in") and c.dep_ in ("prt", "advmod") for c in verb.children)
    part_only = bool(noms) and all(n in PART_NOUNS for n in noms)
    if lem in TRAVERSE_OBJ_LEMMAS and (loc.dep_ == "dobj" and not noms or part_only or
                                       (noms and noms[-1] in BOUNDARY_NOUNS and prep == "of" and lem == "enter")):
        trav = True
    elif lem == "cross" and noms and noms[-1] in BOUNDARY_NOUNS and prep == "of":
        trav = True  # crossed the threshold of X
    elif lem in ("get", "make", "end", "wind", "find") and (fr.get("FIRST_PREP") in ("into", "inside", "within") or
                                                           ((parts | kids) & {"through", "inside", "in"} and (prep in ("to", "into", "inside") or part_only))):
        trav = True  # got inside / made it into / ended up inside / got through to
    elif lem in TRAVERSE_INTO_LEMMAS and prep in ("into", "inside", "through", "inside_", "in") and (prep != "in" or "inside" in parts):
        trav = True
    elif lem in TRAVERSE_INTO_LEMMAS and prep.startswith("inside"):
        trav = True
    elif lem in ARRIVE_LEMMAS and prep in ("in", "at", "inside"):
        trav = True
    elif lem in RETURN_LEMMAS and prep in ("to", "into", "inside"):
        trav = True
    elif inside_kid and lem in CAUSED_TRAVERSE_LEMMAS | TRAVERSE_INTO_LEMMAS:
        trav = True
        if lem in CAUSED_TRAVERSE_LEMMAS and not fr.get("passive"):
            out["traverser"] = "OBJECT"
    elif lem in CAUSED_TRAVERSE_LEMMAS and (fr.get("FIRST_PREP") in ("into", "inside", "through", "to") or prep in ("into", "inside", "through", "to") or prep.startswith("inside")):
        trav = True
        out["traverser"] = "OBJECT"
    elif lem in GAIN_LEMMAS and out["ACCESS_RELATION"]:
        trav = True
    elif lem == "cross" and (loc.dep_ == "dobj" or prep in ("into", "to")):
        trav = True
    if lem == "pass" and prep in ("to",):
        trav = False
    # ---- R16 P2 completed motion, structural (no verb list): character subject + motion predicate
    # (intransitive verb taking an into/inside/through PP on the verb itself) + realis completed event.
    fp2 = fr.get("FIRST_PREP") or ""
    pp2 = loc.head if loc.dep_ == "pobj" else None
    dsub = _dep_subject(chain)
    if not trav and fp2 in ("into", "inside", "through") and pp2 is not None and pp2.head.i == verb.i \
            and verb.pos_ == "VERB" and not upper and not noms and not fr.get("passive") \
            and not any(c.dep_ in ("dobj", "ccomp") for c in verb.children) \
            and lem not in (PERCEPTION_LEMMAS | COMMUNICATION_LEMMAS | COGNITION_LEMMAS | REFERENCE_LEMMAS
                            | REQUEST_LEMMAS | PERMISSION_LEMMAS | FAILURE_LEMMAS | ATTEMPT_CONTROL_LEMMAS) \
            and _finite_asserted(verb, fr) and not _speech_like(verb):
        if _is_char_subject(dsub, ctx):
            trav = True
            out["r16_rule"] = "P2_COMPLETED_MOTION"
        else:
            setv("MOTION_NONCHARACTER", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
            return out
    if trav and out.get("traverser") != "OBJECT" and dsub is not None and dsub.pos_ == "NOUN" \
            and not _is_char_subject(dsub, ctx) and out.get("r16_rule") is None and fr.get("FIRST_PREP") in ("into", "inside", "through") \
            and lem not in CAUSED_TRAVERSE_LEMMAS:
        setv("MOTION_NONCHARACTER", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        return out
    if trav and prep == "through" and any(
            c.dep_ == "prep" and c.lower_ in ("into", "inside", "to") for c in verb.children):
        setv("TRAVERSAL", "COMPLETED", "SUCCESS", "TRANSIT_SITE", "STRUCTURAL_PARTIAL")
        out["COMPLETED_TRAVERSAL_EVIDENCE"] = True
        return out
    if trav:
        if progressive:
            setv("TRAVERSAL", "IN_PROGRESS", "UNKNOWN", "DESTINATION")
            out["DESTINATION_LOCATION"] = "SELF"
            return out
        if upper & SUCCESS_CONTROL or not upper:
            setv("TRAVERSAL", "COMPLETED", "SUCCESS", "SUCCESSFUL_DESTINATION")
            out["COMPLETED_TRAVERSAL_EVIDENCE"] = True
            out["DESTINATION_LOCATION"] = "SELF"
            return out
        setv("TRAVERSAL", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        return out
    # ---- current occupancy (P4/P13)
    occ_pred = lem in OCC_LEMMAS or (lem == "be" and not fr.get("nom_lemmas")) or \
        (lem == "seat" and fr.get("passive"))
    if lem == "be" and fr.get("nom_lemmas"):
        occ_pred = all(n in PART_NOUNS for n in fr["nom_lemmas"])
    subj_tied = _dep_subject(chain) is not None
    if occ_pred and subj_tied:
        located = prep in OCC_PREPS or prep.startswith("inside") or prep in ("across", "through", "around") and lem == "pace" \
            or (loc.dep_ == "dobj" and lem in ("occupy", "pace", "patrol", "guard")) \
            or (fr.get("nom_lemmas") and all(n in PART_NOUNS for n in fr["nom_lemmas"]))
        if located and not (upper - SUCCESS_CONTROL - {"keep", "continue", "remain"}):
            setv("OCCUPANCY", "CURRENT", "NONE", "CURRENT_SITE")
            out["CURRENT_OCCUPANCY_EVIDENCE"] = True
            return out
    # activity predicate + containment/locative complement (P4/P13): 'sealed the hatch inside X',
    # 'collapses in the back alley', 'worked the bellows at the forge'.  Motion verbs excluded.
    fp = fr.get("FIRST_PREP") or ""
    special = BOUNDARY_NOUNS | REF_NOUNS | PLAN_NOUNS | ACCESS_NOUNS | REQUEST_NOUNS | ATTEMPT_NOUNS
    # R15 structural activity rule: (a) subject attached by dependency and (b) the locative PP
    # attaches to the verb itself (prep head == verb, or via advmod/obl of the verb), never to a noun.
    pp = loc.head if loc.dep_ == "pobj" else None
    pp_on_verb = pp is not None and (pp.head.i == verb.i or (
        pp.head.dep_ in ("advmod", "obl", "npadvmod") and pp.head.head.i == verb.i)) and not noms
    # R16 P4 object-attachment recovery: '<Char> restrung the bow in X' -> PP re-attached to the verb
    # only for a determined/plural concrete direct object that is not itself a place and no placement/light verb.
    obj = pp.head if pp is not None else None
    recovered = (pp is not None and not pp_on_verb and obj.dep_ == "dobj" and obj.head.i == verb.i
                 and noms == [obj.lemma_.lower()] and not _is_place_tok(obj) and obj.lemma_.lower() not in special
                 and (any(c.dep_ in ("det", "poss", "nummod") for c in obj.children) or obj.tag_ == "NNS")
                 and lem not in PLACEMENT_LEMMAS | LIGHT_LEMMAS
                 and fp in ACTIVITY_PREPS)
    if recovered:
        out["PP_REATTACHED"] = "OBJECT->VERB"
    # R16 P5: perception / communication / cognition (lexical class OR clausal/dative/about dependency) never occupancy
    lf = _lemma_forms(verb)
    if fp in ACTIVITY_PREPS and (lf & (PERCEPTION_LEMMAS | COMMUNICATION_LEMMAS | COGNITION_LEMMAS) or _speech_like(verb)
                                 or (fp == "at" and lf & DIRECTED_AT_LEMMAS)):
        setv("PERCEPTION_COMMUNICATION_MEMORY", "UNKNOWN", "UNKNOWN", "UNKNOWN", "STRUCTURAL_PARTIAL")
        return out
    dsub3 = _dep_subject(chain)
    # placement verbs with an object describe where the OBJECT ends up, not the subject
    if lem in PLACEMENT_LEMMAS and any(c.dep_ == "dobj" for c in verb.children):
        setv("PLACEMENT", "UNKNOWN", "UNKNOWN", "UNKNOWN", "STRUCTURAL_PARTIAL")
        return out
    # R16 P3: character subject + realis activity predicate + physical locative PP on the predicate.
    if fp in ACTIVITY_PREPS and verb.pos_ == "VERB" and not upper and (pp_on_verb or recovered) and subj_tied \
            and _is_char_subject(dsub3, ctx) and not fr.get("modal") \
            and lem not in _activity_excluded() and not any(n in special for n in (noms if not recovered else [])):
        setv("ACTIVITY_OCCUPANCY_RECOVERED" if recovered else "ACTIVITY_OCCUPANCY", "CURRENT", "NONE", "CURRENT_SITE", "STRUCTURAL_PARTIAL")
        out["CURRENT_OCCUPANCY_EVIDENCE"] = True
        return out
    # destination prepositions without completion
    if prep in DEST_PREPS or prep == "into":
        setv("MOTION", "UNKNOWN", "UNKNOWN", "DESTINATION", "STRUCTURAL_PARTIAL")
        out["DESTINATION_LOCATION"] = "SELF"
        return out
    setv("UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN")
    return out


PLACEMENT_LEMMAS = frozenset("put place set lay leave store hide stash drop throw toss pour load pack stuff plant bury hang park".split())
LIGHT_LEMMAS = frozenset("take have make give show lose gain hold get find keep own buy sell rent inherit lease".split())
CHAR_PRON = frozenset("he she they i we you".split())
CESSATION_CONTROL = frozenset("cease quit stop".split())


DIRECTED_AT_LEMMAS = frozenset("""point frown glare scowl smile grin nod wave laugh sneer wink gesture aim shout yell
bark snap growl squint blink marvel gawk gape leer jeer scoff""".split())
CESSATION_ADVS = frozenset("formerly previously".split())


def _lemma_forms(tok) -> set:
    """Lemma plus surface-derived stems (guards against lemmatizer slips like 'stared' -> 'star')."""
    t = tok.lower_
    out = {tok.lemma_.lower(), t}
    for suf in ("ed", "d", "s", "es", "ing"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            b = t[: -len(suf)]
            out |= {b, b + "e"}
            if len(b) > 2 and b[-1] == b[-2]:
                out.add(b[:-1])
    return out


def _finite_asserted(verb, fr) -> bool:
    """R16 P10: finite asserted clause without relying on VBD/VBN tags.
    Root or conjunct (of a root/conjunct) clause, nominal subject attached, no infinitival 'to',
    no modal/future/progressive, no subordinating mark, not a participle/gerund."""
    if fr.get("modal") or fr.get("ASPECT") == "PROGRESSIVE" or fr.get("passive"):
        return False
    if verb.tag_ in ("VBG",) or any(c.dep_ == "aux" and c.tag_ == "TO" for c in verb.children):
        return False
    if verb.tag_ == "VBN" and not any(a.lemma_.lower() == "have" for a in _aux(verb)):
        return False
    if any(a.lemma_.lower() in ("do",) for a in _aux(verb)):
        return False  # do-support appears only with negation/questions/emphasis here; not asserted completion
    cur = verb
    g = 0
    while cur.dep_ == "conj" and g < 6:
        cur = cur.head
        g += 1
    if cur.dep_ != "ROOT":
        return False
    if any(c.dep_ == "mark" for c in verb.children) or any(c.dep_ == "mark" for c in cur.children):
        return False
    return True


def _is_char_subject(s, ctx) -> bool:
    """R16: animate/character subject by structure + structured context only (no NER, no guessing)."""
    if s is None or s.dep_ == "expl":
        return False
    if s.lower_ in CHAR_PRON:
        return True
    if s.pos_ == "PROPN":
        return True
    return bool(ctx.char_id(_subject_text(s)))


def _realis_past(verb, fr) -> bool:
    if fr.get("modal") or fr.get("ASPECT") == "PROGRESSIVE":
        return False
    if verb.tag_ == "VBD":
        return True
    return verb.tag_ == "VBN" and any(a.lemma_.lower() == "have" for a in _aux(verb)) and not fr.get("passive")


def _speech_like(verb) -> bool:
    """P5 dependency role: clausal complement, 'about' content, or dative recipient -> communication/cognition frame."""
    return any(c.dep_ in ("ccomp", "dative") or (c.dep_ == "prep" and c.lower_ in ("about", "of") and c.head.i == verb.i)
               for c in verb.children)


def _activity_excluded() -> frozenset:
    return (MOTION_LEMMAS | TRAVERSE_INTO_LEMMAS | TRAVERSE_OBJ_LEMMAS | CAUSED_TRAVERSE_LEMMAS | ARRIVE_LEMMAS
            | DEPART_LEMMAS | INCHOATIVE_LEMMAS | PERCEPTION_LEMMAS | COMMUNICATION_LEMMAS | COGNITION_LEMMAS
            | {"be", "have"})


def _dep_subject(chain: List[Any]):
    """Grammatical subject tied by dependency (own nsubj/nsubjpass, xcomp controller, or conj head)."""
    for v in chain:
        s = _subject_of(v)
        if s is not None and s.dep_ != "expl":
            return s
    cur = chain[-1] if chain else None
    g = 0
    while cur is not None and cur.dep_ == "conj" and g < 6:
        cur = cur.head
        g += 1
        s = _subject_of(cur)
        if s is not None and s.dep_ != "expl":
            return s
    return None


def _small_clause_subject(loc):
    """Verbless '<NP subject> <locative PP>' -> subject token (PROPN/pronoun) or None."""
    cur = loc
    g = 0
    while g < 8 and cur.head.i != cur.i:
        g += 1
        h = cur.head
        if h.pos_ in ("PROPN", "PRON") and h.dep_ in ("ROOT", "nsubj"):
            return h
        if _is_verbal(h):
            return None
        cur = h
    if cur.pos_ in ("PROPN",):
        return cur
    return None


def _completion_events(sent) -> List[Tuple[Any, Any]]:
    """Realis traversal verbs with no location of their own: 'and crossed inside', 'then entered'."""
    out = []
    lemmas = TRAVERSE_INTO_LEMMAS | {"enter", "cross", "pass"}
    for t in sent:
        if t.pos_ != "VERB" or t.lemma_.lower() not in lemmas:
            continue
        if _has_neg(t) or any(a.tag_ == "MD" or a.lemma_.lower() in MODAL_LEMMAS for a in _aux(t)):
            continue
        if any(c.dep_ == "aux" and c.tag_ == "TO" for c in t.children) or t.dep_ in ("xcomp", "pcomp", "acl"):
            continue
        if t.tag_ == "VBG" and not any(a.lemma_.lower() == "be" for a in _aux(t)):
            continue
        if any(_is_place_tok(g) for g in t.subtree if g.i != t.i):
            continue
        inward = any(c.lower_ in ("inside", "in", "through", "indoors", "within") and c.dep_ in ("advmod", "prt", "prep")
                     and not any(g.dep_ == "pobj" for g in c.children) for c in t.children)
        bare_enter = t.lemma_.lower() == "enter" and not any(c.dep_ in ("dobj", "prep") for c in t.children)
        if not (inward or bare_enter):
            continue
        subj = _dep_subject([t])
        if subj is None and t.dep_ == "dep" and _is_verbal(t.head):
            subj = _subject_of(t.head)
        out.append((t, subj))
    return out


def _failure_events(sent) -> List[Tuple[Any, Any]]:
    """(failure verb, subject token) for clause-level failures without their own location."""
    out = []
    for t in sent:
        if not _is_verbal(t):
            continue
        lem = t.lemma_.lower()
        parts = set(_particles(t))
        fail = lem in FAILURE_LEMMAS or (lem in FAIL_PARTICLE_LEMMAS and parts & {"back", "away", "off"})
        # R16 P15: negated traversal ('could not get through', 'never made it inside') is a failure event
        if _has_neg(t) and (parts & {"through", "in", "inside", "past"} or lem in ("enter", "pass", "cross", "reach")):
            fail = True
        if lem == "find":
            for c in t.children:
                if c.dep_ in ("ccomp", "oprd", "xcomp", "acomp") and (c.lower_ in FAIL_STATE_ADJ or any(
                        g.lower_ in FAIL_STATE_ADJ for g in c.subtree)):
                    fail = True
        if any(c.dep_ == "acomp" and c.lower_ in FAIL_STATE_ADJ for c in t.children) and lem == "be":
            fail = True
        if fail:
            subj = _subject_of(t)
            if subj is None:
                cur = t
                g = 0
                while cur.dep_ == "conj" and g < 6 and subj is None:
                    cur = cur.head
                    subj = _subject_of(cur)
                    g += 1
            out.append((t, subj))
    return out


def _subject_key(rec: Dict[str, Any]) -> str:
    return (rec.get("SUBJECT_CHARACTER_ID") or rec.get("SUBJECT_TEXT") or "").lower()


def analyze_doc(doc, *, depicted_characters: Optional[Iterable[str]] = None,
                character_context: Optional[Any] = None) -> List[Dict[str, Any]]:
    ctx = _Ctx(depicted_characters, character_context)
    records: List[Dict[str, Any]] = []
    for s_i, sent in enumerate(doc.sents):
        sent_recs: List[Dict[str, Any]] = []
        for tok in sent:
            if not _is_place_tok(tok):
                continue
            # skip a place head used as compound modifier of another place head
            if tok.dep_ == "compound" and _is_place_tok(tok.head):
                continue
            start, end = _mention_span(tok)
            mention = doc.text[start:end]
            fr = _event_frame(tok, ctx)
            cls = _classify(tok, fr, ctx)
            verb = fr.get("verb")
            chain = fr.get("chain") or []
            subj, _how = _resolve_subject(chain, ctx) if chain else (None, "")
            if subj is None and cls.get("small_clause_subject") is not None:
                subj = cls["small_clause_subject"]
            if cls.get("traverser") == "OBJECT" and verb is not None:
                obj = next((c for c in verb.children if c.dep_ == "dobj"), None)
                if obj is not None:
                    subj = obj
                elif fr.get("passive"):
                    subj = _subject_of(verb)
            subj_text = _subject_text(subj) if subj is not None else ""
            resolved = subj
            if subj is not None and subj.lower_ in PERSONAL_PRON:
                resolved = _resolve_pronoun(subj, ctx)
            resolved_text = _subject_text(resolved) if resolved is not None else ""
            cid = ctx.char_id(resolved_text) if resolved_text else ""
            if not cid and resolved is not None and resolved.pos_ == "PROPN" and not ctx.name_to_id:
                cid = resolved_text  # no structured context: exact surface name, no fuzzy correction
            if subj is not None and subj.lower_ in PERSONAL_PRON and resolved is None:
                cid = UNRESOLVED  # UNRESOLVED_PRONOUN_POLICY=FAIL_NEUTRAL
            root = _clause_root(chain[-1]) if chain else _clause_root(tok)
            rec = {
                "LOCATION_MENTION": mention,
                "CANONICAL_LOCATION": _norm_loc(mention),
                "HEAD": tok.lower_,
                "START_CHAR": start,
                "END_CHAR": end,
                "SENTENCE_ID": s_i,
                "CLAUSE_ID": "s%dc%d" % (s_i, root.i),
                "DEPENDENCY_ROOT": root.lemma_.lower(),
                "LOCATION_DEP": tok.dep_,
                "PREPOSITION": fr.get("PREPOSITION", ""),
                "NOMINAL_CHAIN": fr.get("NOMINAL_CHAIN", []),
                "SUBJECT_TEXT": subj_text,
                "SUBJECT_LEMMA": subj.lemma_.lower() if subj is not None else "",
                "SUBJECT_RESOLVED_TEXT": resolved_text,
                "SUBJECT_CHARACTER_ID": cid,
                "SUBJECT_IS_DEPICTED": None,
                "PREDICATE": fr.get("PREDICATE", ""),
                "CONTROL_CHAIN": fr.get("chain_lemmas", []),
                "AUXILIARIES": fr.get("AUXILIARIES", []),
                "NEGATED": bool(fr.get("NEGATED", False)),
                "TENSE": fr.get("TENSE", "UNKNOWN"),
                "ASPECT": fr.get("ASPECT", "UNKNOWN"),
                "MODALITY": fr.get("MODALITY", "UNKNOWN"),
                "SUPERSEDED_BY": "",
            }
            for k in ("EVENT_TYPE", "EVENT_STATE", "EVENT_RESULT", "BOUNDARY_RELATION", "ACCESS_RELATION",
                      "CURRENT_OCCUPANCY_EVIDENCE", "COMPLETED_TRAVERSAL_EVIDENCE", "LOCATION_ROLE",
                      "PARSER_CONFIDENCE_CLASS"):
                rec[k] = cls[k]
            rec["SOURCE_LOCATION"] = rec["CANONICAL_LOCATION"] if cls["SOURCE_LOCATION"] else ""
            rec["DESTINATION_LOCATION"] = rec["CANONICAL_LOCATION"] if cls["DESTINATION_LOCATION"] or \
                rec["LOCATION_ROLE"] in ("SUCCESSFUL_DESTINATION", "FAILED_DESTINATION", "DESTINATION", "PLANNED_SITE") else ""
            rec["_verb_i"] = verb.i if verb is not None else -1
            sent_recs.append(rec)
        # ---- P10 failure precedence (clause-level failure on same subject, later in sentence)
        fails = _failure_events(sent)
        for fverb, fsubj in fails:
            fkey = ""
            if fsubj is not None:
                r = _resolve_pronoun(fsubj, ctx) if fsubj.lower_ in PERSONAL_PRON else fsubj
                ftxt = _subject_text(r) if r is not None else ""
                fkey = (ctx.char_id(ftxt) or ftxt).lower()
            for rec in sent_recs:
                if rec["EVENT_STATE"] in ("ATTEMPTED", "IN_PROGRESS", "PENDING", "UNKNOWN") and \
                        rec["LOCATION_ROLE"] in ("DESTINATION", "UNKNOWN") and rec["_verb_i"] != fverb.i and \
                        rec["_verb_i"] < fverb.i and (not fkey or fkey == _subject_key(rec)):
                    rec.update(EVENT_STATE="FAILED", EVENT_RESULT="FAILURE", LOCATION_ROLE="FAILED_DESTINATION",
                               ACCESS_RELATION=rec["ACCESS_RELATION"] or "DENIED",
                               SUPERSEDED_BY="FAILURE:" + fverb.lemma_.lower(),
                               PARSER_CONFIDENCE_CLASS="STRUCTURAL_PARTIAL")
                    rec["DESTINATION_LOCATION"] = rec["CANONICAL_LOCATION"]
        for cverb, csubj in _completion_events(sent):
            ckey = ""
            if csubj is not None:
                rr = _resolve_pronoun(csubj, ctx) if csubj.lower_ in PERSONAL_PRON else csubj
                if rr is not None:
                    ct = _subject_text(rr)
                    ckey = (ctx.char_id(ct) or ct).lower()
            if not ckey:
                continue
            prior = [rec for rec in records if rec["EVENT_STATE"] in ("PENDING", "ATTEMPTED", "IN_PROGRESS")]
            cands = [rec for rec in prior + sent_recs if (rec in prior or rec["_verb_i"] < cverb.i) and rec["LOCATION_ROLE"] == "DESTINATION"
                     and rec["EVENT_STATE"] in ("PENDING", "ATTEMPTED", "IN_PROGRESS", "UNKNOWN")
                     and _subject_key(rec) == ckey]
            # an access noun used as the permission object ('granted passage into X') is not a destination
            cands = [rec for rec in cands if rec["HEAD"] not in ACCESS_NOUNS] or cands
            if len({rec["CANONICAL_LOCATION"] for rec in cands}) != 1:
                continue  # ambiguous or none: fail neutral
            for rec in cands:
                rec.update(EVENT_STATE="COMPLETED", EVENT_RESULT="SUCCESS", LOCATION_ROLE="SUCCESSFUL_DESTINATION",
                           COMPLETED_TRAVERSAL_EVIDENCE=True, SUPERSEDED_BY="COMPLETION:" + cverb.lemma_.lower(),
                           PARSER_CONFIDENCE_CLASS="STRUCTURAL_PARTIAL")
                rec["DESTINATION_LOCATION"] = rec["CANONICAL_LOCATION"]
        records.extend(sent_recs)
    # ---- P9 completion precedence (same subject + location, scene-level)
    for rec in records:
        if rec["EVENT_STATE"] in ("ATTEMPTED", "IN_PROGRESS", "PENDING") and rec["LOCATION_ROLE"] == "DESTINATION":
            for other in records:
                if other is rec or other["EVENT_STATE"] != "COMPLETED":
                    continue
                if other["CANONICAL_LOCATION"] == rec["CANONICAL_LOCATION"] and _subject_key(other) == _subject_key(rec):
                    rec["SUPERSEDED_BY"] = "COMPLETION:" + other["CLAUSE_ID"]
    # ---- P8 subject ownership / depiction
    for rec in records:
        role = rec["LOCATION_ROLE"]
        if rec["SUBJECT_CHARACTER_ID"] == UNRESOLVED:
            rec["SUBJECT_IS_DEPICTED"] = "UNKNOWN"
            if role in ("CURRENT_SITE", "SUCCESSFUL_DESTINATION"):
                rec["LOCATION_ROLE"] = "UNRESOLVED_SUBJECT_SITE"
            rec.pop("_verb_i", None)
            continue
        if ctx.depicted is not None:
            sid = (rec["SUBJECT_CHARACTER_ID"] or "").lower()
            depicted = bool(sid) and sid in ctx.depicted
            rec["SUBJECT_IS_DEPICTED"] = depicted
            if role in ("CURRENT_SITE", "SUCCESSFUL_DESTINATION") and not depicted:
                rec["LOCATION_ROLE"] = "NONDEPICTED_SUBJECT_SITE" if sid else "UNRESOLVED_SUBJECT_SITE"
        rec.pop("_verb_i", None)
    return records


def analyze(text: str, *, depicted_characters: Optional[Iterable[str]] = None,
            character_context: Optional[Any] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    doc = parse(text)
    if doc is None:
        return {"PARSER_AVAILABLE": False, "PARSER_ERROR": _NLP_ERROR, "records": [], "PARSE_MS": 0.0}
    recs = analyze_doc(doc, depicted_characters=depicted_characters, character_context=character_context)
    return {"PARSER_AVAILABLE": True, "PARSER_ERROR": "", "records": recs,
            "PARSE_MS": (time.perf_counter() - t0) * 1000.0}


def match_record(records: List[Dict[str, Any]], loc_norm: str, pos: int) -> Optional[Dict[str, Any]]:
    """Find the R15 record for a legacy candidate (normalized loc + absolute char pos)."""
    if not records or not loc_norm:
        return None
    head = loc_norm.split()[-1]
    best = None
    best_d = 10 ** 9
    for r in records:
        if r["HEAD"] != head and r["CANONICAL_LOCATION"].split()[-1:] != [head] \
                and not (head.endswith("s") and r["HEAD"] == head[:-1]) and not (r["HEAD"].endswith("s") and r["HEAD"][:-1] == head):
            continue
        if pos >= 0 and r["START_CHAR"] - 2 <= pos <= r["END_CHAR"]:
            return r
        d = abs(r["START_CHAR"] - pos) if pos >= 0 else 0
        if d < best_d:
            best, best_d = r, d
    return best


RECORD_FIELDS = (
    "LOCATION_MENTION", "CANONICAL_LOCATION", "CLAUSE_ID", "DEPENDENCY_ROOT", "SUBJECT_TEXT", "SUBJECT_LEMMA",
    "SUBJECT_CHARACTER_ID", "SUBJECT_IS_DEPICTED", "PREDICATE", "AUXILIARIES", "NEGATED", "TENSE", "ASPECT",
    "MODALITY", "EVENT_TYPE", "EVENT_STATE", "EVENT_RESULT", "SOURCE_LOCATION", "DESTINATION_LOCATION",
    "BOUNDARY_RELATION", "ACCESS_RELATION", "CURRENT_OCCUPANCY_EVIDENCE", "COMPLETED_TRAVERSAL_EVIDENCE",
    "LOCATION_ROLE", "PARSER_CONFIDENCE_CLASS",
)
EMPTY_RECORD: Dict[str, Any] = {
    "LOCATION_MENTION": "", "CANONICAL_LOCATION": "", "CLAUSE_ID": "", "DEPENDENCY_ROOT": "", "SUBJECT_TEXT": "",
    "SUBJECT_LEMMA": "", "SUBJECT_CHARACTER_ID": "", "SUBJECT_IS_DEPICTED": None, "PREDICATE": "", "AUXILIARIES": [],
    "NEGATED": False, "TENSE": "UNKNOWN", "ASPECT": "UNKNOWN", "MODALITY": "UNKNOWN", "EVENT_TYPE": "UNKNOWN",
    "EVENT_STATE": "UNKNOWN", "EVENT_RESULT": "UNKNOWN", "SOURCE_LOCATION": "", "DESTINATION_LOCATION": "",
    "BOUNDARY_RELATION": "", "ACCESS_RELATION": "", "CURRENT_OCCUPANCY_EVIDENCE": False,
    "COMPLETED_TRAVERSAL_EVIDENCE": False, "LOCATION_ROLE": "UNKNOWN", "PARSER_CONFIDENCE_CLASS": "UNKNOWN",
}


# ---------------------------------------------------------------- SHADOW MODE
R15_SHADOW_MODE = True
PRODUCTION_CUTOVER = False


def _new_bind(role: str) -> bool:
    """NEW_BIND = the existing R12 single bind check; no separate bind logic."""
    from tools.location_relation_r6 import _BIND_ROLES
    return role in _BIND_ROLES


def shadow_compare(scene_text: str, *, depicted_characters: Optional[Iterable[str]] = None,
                   character_context: Optional[Any] = None) -> Dict[str, Any]:
    """Run legacy r6.classify (unchanged, production) and R15 side by side. Never alters production."""
    from tools import location_relation_r6 as r6
    legacy = r6.classify(scene_text)
    text = r6.expand_contractions(str(scene_text or ""))
    res = analyze(text, depicted_characters=depicted_characters, character_context=character_context)
    recs = list(res["records"])
    used = set()
    cases: List[Dict[str, Any]] = []

    def case(old_m, new_r):
        old_role = str(old_m.get("LOCATION_ROLE") or "") if old_m else ""
        old_bind = bool(old_m.get("FINAL_BIND_ALLOWED")) if old_m else False
        new_role = str(new_r.get("LOCATION_ROLE") or "UNKNOWN") if new_r else "UNKNOWN"
        nb = _new_bind(new_role)
        reasons = []
        if old_m is None:
            reasons.append("NO_LEGACY_MENTION")
        if new_r is None:
            reasons.append("NO_R15_RECORD:UNKNOWN_SEMANTICS_DEFAULT=NEUTRAL")
        if old_role != new_role:
            reasons.append("ROLE:%s->%s" % (old_role or "-", new_role))
        if old_bind != nb:
            reasons.append("BIND:%s->%s" % (old_bind, nb))
        if new_r and new_r.get("SUBJECT_IS_DEPICTED") is False:
            reasons.append("SUBJECT_NOT_DEPICTED")
        row = {
            "LOCATION": (old_m or {}).get("NORMALIZED") or (new_r or {}).get("CANONICAL_LOCATION", ""),
            "OLD_LOCATION_ROLE": old_role, "NEW_LOCATION_ROLE": new_role,
            "OLD_BIND": old_bind, "NEW_BIND": nb,
            "OLD_SUBJECT": "",  # legacy r6 carries no grammatical subject
            "NEW_SUBJECT": (new_r or {}).get("SUBJECT_CHARACTER_ID") or (new_r or {}).get("SUBJECT_TEXT", ""),
            "DISAGREEMENT": bool(old_role != new_role or old_bind != nb),
            "DISAGREEMENT_REASON": ";".join(r for r in reasons if not r.startswith("NO_LEGACY") or True) if (old_role != new_role or old_bind != nb) else "",
            "R15_RECORD": {k: (new_r or EMPTY_RECORD).get(k) for k in RECORD_FIELDS},
        }
        row["R15_RECORD"]["FINAL_BIND_ALLOWED"] = nb
        row["R15_RECORD"]["FINAL_BIND_REASON"] = "LOCATION_ROLE=" + new_role
        cases.append(row)

    # R15 tighten (4): match by character offset.  Legacy CLAUSE_ID is the clause start offset in
    # the contraction-expanded text and RAW starts at the location token; R15 records carry spans.
    low = text.lower()
    for m in legacy.get("LOCATION_RELATION_MENTIONS") or []:
        loc = str(m.get("NORMALIZED") or "")
        raw = str(m.get("RAW") or m.get("RAW_LOCATION_MENTION") or loc).lower()
        try:
            cst = int(str(m.get("CLAUSE_ID") or "0"))
        except ValueError:
            cst = 0
        pos = low.find(raw, cst) if raw else -1
        end = pos + len(raw) if pos >= 0 else -1
        r = None
        if pos >= 0 and loc:
            head = loc.split()[-1]
            for i, rr in enumerate(recs):
                hm = rr["HEAD"] == head or rr["HEAD"] + "s" == head or head + "s" == rr["HEAD"]
                if hm and rr["START_CHAR"] < end and pos < rr["END_CHAR"]:
                    r = rr
                    used.add(i)
                    break
        m_off = dict(m)
        m_off["_OFFSET"] = pos
        case(m_off, r)
        cases[-1]["OLD_OFFSET"] = pos
        cases[-1]["NEW_OFFSET"] = r["START_CHAR"] if r else -1
    for i, r in enumerate(recs):
        if i not in used and not any(c["R15_RECORD"].get("LOCATION_MENTION") == r["LOCATION_MENTION"] and
                                     c["R15_RECORD"].get("CLAUSE_ID") == r["CLAUSE_ID"] for c in cases):
            case(None, r)
    return {
        "R15_SHADOW_MODE": True, "PRODUCTION_CUTOVER": False,
        "PARSER_AVAILABLE": res["PARSER_AVAILABLE"], "PARSE_MS": res["PARSE_MS"],
        "LEGACY_RESULT_UNCHANGED": True, "cases": cases,
    }
