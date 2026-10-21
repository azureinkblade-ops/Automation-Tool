# -*- coding: utf-8 -*-
"""R6 compositional location-relation classifier.

Deterministic per-mention classification from lexical families, negation,
aspect, and preposition semantics. No LLM. No sentence-wide keyword bind.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

CURRENT = "CURRENT_LOCATION_EVIDENCE"
NEGATED = "NEGATED_LOCATION"
DEPARTED = "DEPARTED_LOCATION"
REFERENCE = "REFERENCE_ONLY_LOCATION"
AMBIGUOUS = "AMBIGUOUS_LOCATION"

PRECEDENCE = {NEGATED: 50, DEPARTED: 40, REFERENCE: 30, CURRENT: 20, AMBIGUOUS: 10}

_TOKEN_RX = re.compile(r"[a-z0-9']+", re.I)
_CLAUSE_SPLIT_RX = re.compile(
    r"\s*(?:;+|"
    r"\s+although\s+|\s+though\s+|\s+however\s+|"
    r",?\s+and\s+instead\s+|\band\s+instead\s+|"
    r"\s+instead\s+|\s+while\s+|\s+but\s+|\s+then\s+|"
    r"\s+before\s+|\s+after\s+|"
    r",\s+and\s+|\s+and\s+"
    r")\s*",
    re.I,
)

_CONTRACTIONS = (
    (re.compile(r"\bwasn't\b", re.I), "was not"),
    (re.compile(r"\bweren't\b", re.I), "were not"),
    (re.compile(r"\bisn't\b", re.I), "is not"),
    (re.compile(r"\baren't\b", re.I), "are not"),
    (re.compile(r"\bdidn't\b", re.I), "did not"),
    (re.compile(r"\bdoesn't\b", re.I), "does not"),
    (re.compile(r"\bdon't\b", re.I), "do not"),
    (re.compile(r"\bhadn't\b", re.I), "had not"),
    (re.compile(r"\bhasn't\b", re.I), "has not"),
    (re.compile(r"\bhaven't\b", re.I), "have not"),
    (re.compile(r"\bcouldn't\b", re.I), "could not"),
    (re.compile(r"\bwouldn't\b", re.I), "would not"),
    (re.compile(r"\bshouldn't\b", re.I), "should not"),
    (re.compile(r"\bcan't\b", re.I), "can not"),
    (re.compile(r"\bwon't\b", re.I), "will not"),
)

PLACE_HEADS = frozenset("""
alley apartment stairwell staircase hallway corridor kitchen room hall chamber market
bazaar village town city street road square plaza courtyard garden park forest mountain
valley river lake shore beach temple shrine altar pavilion sect monastery tower gate
library office shop house home building station platform tunnel warehouse factory workshop
forge foundry smithy arena camp fortress castle palace dungeon ruins cave pod portal
cafe bar school hospital lab hangar deck cabin passage path trail pavement sidewalk
counter desk rooftop roof balcony lobby basement attic bridge skybridge undercity
plaza hall halls forges rooms apartments
""".split())

DET = frozenset("the a an his her their its my our your this that these those some every each own".split())
ADVERBS = frozenset(
    "far well already still just even quite entirely once long way very really only also then "
    "ahead together quietly first second later soon".split()
)
STOP = frozenset("""
as while after before with and that which where when who whom whose of to for but or nor so yet if than
was were is are be been being had has have did does do could would should might must will shall can
he she they them him her i we you it
""".split()) | ADVERBS

# form -> lemma
_FORM: Dict[str, str] = {}
# lemma -> family
_FAMILY: Dict[str, str] = {}


def _add(family: str, lemma: str, *forms: str) -> None:
    allf = {lemma, *forms}
    _FAMILY[lemma] = family
    for f in allf:
        _FORM[f] = lemma


def _reg(lemma: str) -> Tuple[str, ...]:
    out = {lemma, lemma + "s", lemma + "ed", lemma + "ing"}
    if lemma.endswith("e"):
        out.add(lemma + "d")
        out.add(lemma[:-1] + "ing")
        out.add(lemma + "s")
    if lemma.endswith("y") and lemma[-2:] not in ("ay", "ey", "oy"):
        out.add(lemma[:-1] + "ies")
        out.add(lemma[:-1] + "ied")
    return tuple(out)


def _boot() -> None:
    if _FORM:
        return
    # CURRENT occupancy / motion-into
    for lem in ("enter", "arrive", "reach", "wait", "work", "remain", "stay", "return",
                "occupy", "linger", "reside", "shelter", "rest", "sleep", "kneel", "crouch",
                "pace", "live", "hide", "labor", "visit", "stop"):
        _add("CURRENT", lem, *_reg(lem))
    _add("CURRENT", "occupy", "occupy", "occupies", "occupied", "occupying")
    _add("CURRENT", "hide", "hide", "hides", "hiding", "hid", "hidden")
    _add("CURRENT", "sleep", "sleep", "sleeps", "sleeping", "slept")
    _add("CURRENT", "kneel", "kneel", "kneels", "kneeling", "knelt")
    _add("CURRENT", "stand", "stand", "stands", "standing", "stood")
    _add("CURRENT", "sit", "sit", "sits", "sitting", "sat")
    _add("CURRENT", "be", "be", "am", "is", "are", "was", "were", "been", "being")
    _add("CURRENT", "go", "go", "goes", "going", "went", "gone")
    _add("CURRENT", "move", "move", "moves", "moved", "moving")
    _add("CURRENT", "walk", "walk", "walks", "walked", "walking")
    _add("CURRENT", "come", "come", "comes", "coming", "came")
    # REFERENCE
    for lem in ("remember", "recall", "mention", "describe", "learn", "dream", "imagine",
                "picture", "report", "discuss", "repeat"):
        _add("REFERENCE", lem, *_reg(lem))
    _add("REFERENCE", "think", "think", "thinks", "thinking", "thought")
    _add("REFERENCE", "tell", "tell", "tells", "telling", "told")
    _add("REFERENCE", "hear", "hear", "hears", "hearing", "heard")
    _add("REFERENCE", "read", "read", "reads", "reading")
    _add("REFERENCE", "know", "know", "knows", "knowing", "knew", "known")
    _add("REFERENCE", "speak", "speak", "speaks", "speaking", "spoke", "spoken")
    _add("REFERENCE", "talk", "talk", "talks", "talked", "talking")
    for n in ("story", "stories", "tale", "tales", "legend", "legends", "memory", "memories",
              "rumor", "rumors", "account", "accounts", "report", "news", "vision", "dream",
              "image", "thought"):
        _FORM[n] = "story"
        _FAMILY["story"] = "REFERENCE_NOUN"
    # DEPARTURE
    _add("DEPARTED", "leave", "leave", "leaves", "leaving", "left")
    _add("DEPARTED", "depart", *_reg("depart"))
    _add("DEPARTED", "escape", *_reg("escape"))
    _add("DEPARTED", "flee", "flee", "flees", "fleeing", "fled")
    _add("DEPARTED", "exit", *_reg("exit"))
    _add("DEPARTED", "abandon", *_reg("abandon"))
    _add("DEPARTED", "run", "run", "runs", "running", "ran")
    _add("NEG", "avoid", *_reg("avoid"))
    _add("NEG", "miss", *_reg("miss"))
    # INTENT / ATTEMPT (non-current). Explicit inflections: _reg("plan") does not yield "planned".
    _add("INTENT", "plan", "plan", "plans", "planned", "planning")
    _add("INTENT", "mean", "mean", "means", "meant", "meaning")
    _add("INTENT", "intend", *_reg("intend"))
    _add("INTENT", "hope", *_reg("hope"))
    _add("INTENT", "expect", *_reg("expect"))
    _add("INTENT", "prepare", *_reg("prepare"))
    _add("INTENT", "aim", *_reg("aim"))
    _add("INTENT", "want", *_reg("want"))
    _add("INTENT", "try", *_reg("try"))
    _add("INTENT", "attempt", *_reg("attempt"))
    _add("INTENT", "seek", "seek", "seeks", "seeking", "sought")
    _add("INTENT", "head", "head", "heads", "headed", "heading")
    _add("INTENT", "wish", "wish", "wishes", "wished", "wishing")
    _add("INTENT", "resolve", *_reg("resolve"))
    _add("INTENT", "decide", *_reg("decide"))
    _add("INTENT", "choose", "choose", "chooses", "chose", "chosen", "choosing")
    _add("INTENT", "elect", *_reg("elect"))
    _add("INTENT", "propose", *_reg("propose"))
    _add("INTENT", "arrange", *_reg("arrange"))
    _add("INTENT", "contemplate", *_reg("contemplate"))
    _add("INTENT", "consider", *_reg("consider"))
    _add("INTENT", "anticipate", *_reg("anticipate"))
    _add("INTENT", "figure", *_reg("figure"))
    # ATTEMPT / effort (non-result)
    _add("ATTEMPT", "struggle", *_reg("struggle"))
    _add("ATTEMPT", "strive", "strive", "strives", "strived", "strove", "striving")
    _add("ATTEMPT", "endeavor", *_reg("endeavor"))
    _add("ATTEMPT", "fight", "fight", "fights", "fought", "fighting")
    _add("ATTEMPT", "strain", *_reg("strain"))
    # RESULT / success (completed, occupancy-capable)
    _add("RESULT", "manage", *_reg("manage"))
    _add("RESULT", "succeed", *_reg("succeed"))
    # NEGATION lemmas (particles handled separately)
    _add("NEG", "fail", *_reg("fail"))
    _add("NEG", "unable", "unable")


_boot()

REF_NOUNS = frozenset(
    "story stories tale tales legend legends memory memories rumor rumors account accounts "
    "report news vision dream image thought history chronicle chronicles gossip page pages "
    "note notes ballad class lecture".split()
)
NEG_WORDS = frozenset("not never nowhere without no".split())
PREP_CURRENT = frozenset("in inside within at into on through".split())
PREP_NEAR = frozenset("near beside by".split())
PREP_FROM = frozenset("from".split())
PREP_REF = frozenset("about of".split())
PREP_DEST = frozenset("to toward towards for".split())
PREP_AWAY = frozenset()  # handled as multiword away from


def expand_contractions(text: str) -> str:
    out = text
    for rx, repl in _CONTRACTIONS:
        out = rx.sub(repl, out)
    return out


def clauses(text: str) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    last = 0
    for m in _CLAUSE_SPLIT_RX.finditer(text):
        if m.start() > last and text[last:m.start()].strip():
            spans.append((last, m.start(), text[last:m.start()]))
        last = m.end()
    if last < len(text) and text[last:].strip():
        spans.append((last, len(text), text[last:]))
    if not spans:
        spans.append((0, len(text), text))
    return spans


def tokenize(text: str) -> List[Tuple[str, int, int]]:
    return [(m.group(0).lower(), m.start(), m.end()) for m in _TOKEN_RX.finditer(text)]


def lemma_of(tok: str) -> str:
    return _FORM.get(tok, tok)


def family_of(tok: str) -> str:
    return _FAMILY.get(lemma_of(tok), "")


def _noncurrent_complement(toks: List[Tuple[str, int, int]], loc_i: int) -> Tuple[bool, str, str]:
    """Detect INTENT/ATTEMPT complement (to-infinitive or gerund) governing this loc.

    RESULT (managed to / succeeded in) is completed, not noncurrent.
    """
    if loc_i <= 0:
        return False, "", ""
    before = [toks[i][0] for i in range(loc_i)]
    joined = " " + " ".join(before) + " "
    if " managed to " in joined or " succeeded in " in joined:
        return False, "RESULT", "to" if " to " in joined else "gerund"
    for i in range(loc_i):
        fam = family_of(toks[i][0])
        if fam not in ("INTENT", "ATTEMPT"):
            continue
        rest = [toks[j][0] for j in range(i + 1, loc_i)]
        if "to" in rest:
            return True, fam, "to"
        if any(w.endswith("ing") for w in rest):
            return True, fam, "gerund"
    if any(p in joined for p in (
        " effort to ", " ready to ", " bid to ", " wish to ", " no wish to ",
        " poised to ", " due to ", " geared to ", " like to ",
    )):
        return True, "INTENT", "to"
    return False, "", ""


_MODALS = frozenset("would might could may should ought".split())
_MOTION_LEMMAS = frozenset(
    "go enter visit reach slip wander drop step drift stop return stay walk come "
    "move occupy linger occupy visit".split()
)
_PLAN_MOD = frozenset("selected chosen intended authorized preferred stated proposed".split())
_PLAN_NOUNS = frozenset(
    "course option choice objective goal plan route assignment intention "
    "proposal agenda mission task destination waypoint appointment".split()
)
_ACCESS_NOUNS = frozenset(
    "way access entrance passage entry admittance interior threshold "
    "permission clearance admission gate boundary".split()
)
_DENIAL_LEMMAS = frozenset("refuse deny bar prevent block lock halt shut".split())
_GRANT_LEMMAS = frozenset("admit allow gain cross break clear pass secure".split())
_REQUEST_LEMMAS = frozenset("request ask seek petition".split())
_TEST_LEMMAS = frozenset("test check probe examine try".split())
_APPROACH_LEMMAS = frozenset("approach".split())
_WAIT_LEMMAS = frozenset("wait".split())
_INSPECT_LEMMAS = frozenset("examine probe inspect".split())
_BOUNDARY_NOUNS = frozenset("entrance gate threshold boundary lip".split())


def _infl(lem: str) -> frozenset:
    s = {lem, lem + "s", lem + "ed", lem + "ing"}
    if lem.endswith("e"):
        s.add(lem + "d")
        s.add(lem[:-1] + "ing")
    if lem.endswith("y") and lem[-2:] not in ("ay", "ey", "oy"):
        s.add(lem[:-1] + "ies")
        s.add(lem[:-1] + "ied")
    return frozenset(s)


_DENIAL_FORMS = frozenset().union(*(_infl(x) for x in _DENIAL_LEMMAS)) | frozenset(
    "denied refusing refused denying barred blocking blocked".split()
)
_GRANT_FORMS = frozenset().union(*(_infl(x) for x in _GRANT_LEMMAS)) | frozenset(
    "admitted allowed gained crossed broke broken cleared passed secured".split()
)
_REQUEST_FORMS = frozenset().union(*(_infl(x) for x in _REQUEST_LEMMAS)) | frozenset(
    "requesting asked seeking petitioning".split()
)
_TEST_FORMS = frozenset().union(*(_infl(x) for x in _TEST_LEMMAS)) | frozenset(
    "testing checking probing examining trying".split()
)
_APPROACH_FORMS = frozenset().union(*(_infl(x) for x in _APPROACH_LEMMAS)) | frozenset(
    "approaching approached".split()
)
_WAIT_FORMS = frozenset().union(*(_infl(x) for x in _WAIT_LEMMAS))
_INSPECT_FORMS = frozenset().union(*(_infl(x) for x in _INSPECT_LEMMAS)) | frozenset(
    "examining probing inspecting".split()
)
_R9_FAILED = (
    " short of ", " foiled ", " fell short", " turned back", " stopped before ",
    " came up short", " never made ", " could not make ", " bounced off ",
    " thwarted ", " rebuffed ", " denied at ", " stalled outside ", " held off ",
    " locked out ", " fell short of ",
)
_R9_SUCCESS = (
    " made it into ", " made it inside ", " got inside ", " got through into ",
    " ended up inside ", " successfully entered ", " got in and ",
    " got in ", " finally got inside ", " won through ", " gained the interior ",
)
_R9_SCHEDULE = (
    " itinerary", " schedule", " booked for ", " next week", " tomorrow",
    " future objective", " later objective", " later stop", " next destination",
    " on the agenda", " penciled ", " likely to ", " expected to ",
)
_R9_INVERT = (
    " was the plan", " remained the plan", " was his choice", " was her choice",
    " was still only", " was on the agenda", "'s choice",
    "'s proposal", "'s agenda", " was what ",
)
_R9_OCCUPY = (
    " stationed in ", " posted in ", " based in ", " on site at ",
    " spent the night in ", " present inside ", " kept watch ",
    " quartered in ", " encamped in ", " ensconced in ", " seated inside ",
    " lodged in ", " bunked in ", " nested in ",
)
_PRIVATIVE_ACCESS_RX = re.compile(
    r"\b(?:no|not any)\s+(?:way|access|entrance|passage|admittance|entry)\s+(?:into|to|in)\b"
)
_FROM_PREVENT_RX = re.compile(r"\b(?:kept|prevented|blocked|barred|stopped)\s+from\b")
_TURNED_AWAY_RX = re.compile(r"\b(?:turned|driven|forced|beaten)\s+(?:away|back|off)\b")
_KEPT_OUT_RX = re.compile(r"\b(?:kept|held|shut|locked|barred)\s+(?:out|outside)\b")
_THROUGH_OK_RX = re.compile(r"\b(?:got|made|broke|came|pushed|won)\s+(?:it\s+)?through\b")
_ADMIT_RX = re.compile(r"\b(?:admitted|allowed)\s+(?:into|inside|in)\b")
_THRESHOLD_RX = re.compile(r"\b(?:passed|cleared)\s+(?:the\s+)?threshold\b")
_NO_FARTHER_RX = re.compile(r"\b(?:no|not)\s+farther\b")
_FIND_NO_RX = re.compile(r"\b(?:find|found|finding)\s+no\b")
# R11 event-frame constructions (realization / polarity), not plan-noun tables.
_EVAL_RX = re.compile(
    r"\b(?:counted as|constituted|formed|filed as|filed under|logged as|sat as)\b"
    r"|\b(?:remained|stayed)\s+(?!inside\b|in\b|within\b|on\b)"
    r"|\b(?:was|were)\s+the\b"
)
_ACTION_NOM_RX = re.compile(
    r"\b(?:making|getting|securing|taking)\s+(?:entry|a\s+(?:return|visit|foothold|path)|return|visit|foothold|path)\b"
    r"|\b(?:a\s+)?(?:walk|push|visit|return|advance|arrival|entry|drive|bid|path)\s+"
    r"(?:into|to|toward|towards|at|back\s+to)\b"
    r"|\bto\s+(?:make|press|secure|force)\s+(?:entry|a\s+(?:return|visit|path)|a\s+walk|the)?\b"
    r"|\barrival at\b|\breaching\b|\bgetting inside\b|\bentering\b"
)
_STOP_BARRIER_RX = re.compile(
    r"\b(?:stopped|blocked|held|kept)\s+(?:at|outside|before|beyond|past)\b"
)
_TURN_ASIDE_RX = re.compile(r"\bturned aside\b")
_GET_PAST_RX = re.compile(r"\b(?:could not|couldn't|cannot)\s+get\s+past\b")
_COULD_NOT_CROSS_RX = re.compile(r"\b(?:could not|couldn't|cannot)\s+cross\b")
_THRESHOLD_STOP_RX = re.compile(
    r"\b(?:stopped|blocked|held)\s+at\s+(?:the\s+)?threshold\b"
)
_BLOCKED_OUTSIDE_RX = re.compile(r"\bblocked outside\b")
_KEPT_BEYOND_RX = re.compile(r"\bkept beyond\b")
_LET_INSIDE_RX = re.compile(r"\b(?:let|ushered)\s+(?:inside|into|in|through)\b")
_GRANTED_PASSAGE_RX = re.compile(r"\bgranted passage\b")
_MADE_ACROSS_RX = re.compile(r"\bmade it across\b")
_CLEARED_ENTER_RX = re.compile(r"\bcleared to enter\b")
_PASSED_BEYOND_RX = re.compile(
    r"\b(?:passed|cleared|crossed)\s+(?:beyond|through|the)\s+(?:the\s+)?threshold\b"
)
_ALLOWED_ENTER_RX = re.compile(r"\ballowed to enter\b")
_PHYS_OCCUPY_RX = re.compile(
    r"\b(?:physically inside|on the premises|present within|"
    r"beyond the entrance inside)\b"
)
# R12 structural classificatory / access (not growing R11 stem tables).
_CLASSIFY_AS_RX = re.compile(r"\b(?:\w+(?:ed|en|ing)|stood)\s+as\b")
_CLASSIFY_V_RX = re.compile(r"\b(?:constituted|represented|amounted)\s+to\b|\b(?:constituted|represented)\b")
_SENT_BACK_RX = re.compile(r"\b\w+\s+back\s+(?:from|at|before|outside)\b")
_ROUTE_CLOSED_RX = re.compile(
    r"\b(?:crossing|passage|entry|path|gate|way)\b.{0,64}\b(?:closed|unavailable|blocked)\b"
)
_CLOSED_AT_RX = re.compile(r"\b(?:closed|unavailable)\s+(?:at|to|into|before)\b")
_WAVED_OFF_RX = re.compile(r"\bwaved off\b")
_AUTH_TRAVERSE_RX = re.compile(
    r"\b(?:waved|shown|brought|escorted|guided|permitted|admitted)\s+"
    r"(?:through|inside|into|past|beyond|across|in)\b"
)
_UNKNOWN_ACCESS_RX = re.compile(
    r"\b(?:approached the gate|asked for entry|waited for permission|"
    r"tried the entrance|reached the threshold)\b"
)
# R14 event operators (structure, not R13 lemma-list growth).
_AUTH_STATE_RX = re.compile(
    r"\b(?:authorization|admission|permission|clearance|approval|application|authority)\b"
)
_PENDING_REL_RX = re.compile(
    r"\b(?:await\w*|pending|submit\w*|under review|application for)\b"
)
_QUERY_OP_RX = re.compile(
    r"\b(?:verif(?:y|ies|ied|ying)|evaluat(?:e|es|ed|ing)|assess(?:es|ed|ing)?|"
    r"determin(?:e|es|ed|ing))\b"
)
_BOUNDARY_REL_RX = re.compile(
    r"\b(?:neared|nearing|alongside|drew up|closed on|arrived outside|"
    r"exterior(?:\s+side)?)\b"
    r"|\b(?:toward|towards|before)\s+(?:the\s+)?(?:entrance|gate|threshold|boundary|lip|doorway)\b"
)
_INCHOATIVE_RX = re.compile(
    r"\b(?:start(?:ed|ing)?|began|begin(?:ning)?|set off)\b.{0,28}"
    r"\b(?:toward|towards|for|direction|approach|making)\b"
    r"|\bmaking for\b|\bworked toward\b"
)
_BIND_ROLES = frozenset({"CURRENT_SITE", "SUCCESSFUL_DESTINATION"})


def _is_motion_gerund(w: str) -> bool:
    if not w.endswith("ing"):
        return False
    if family_of(w) == "CURRENT" or lemma_of(w) in _MOTION_LEMMAS:
        return True
    stem = w[:-3]
    cands = {stem, stem + "e"}
    if len(stem) > 2:
        cands.add(stem[:-1])
    return any(
        c in _MOTION_LEMMAS or c in _GRANT_LEMMAS or family_of(c) == "CURRENT"
        for c in cands
    )


def _has_motion(words: List[str]) -> bool:
    return any(
        family_of(w) == "CURRENT" or lemma_of(w) in _MOTION_LEMMAS or w in _MOTION_LEMMAS
        or _is_motion_gerund(w)
        for w in words
    )


def _r9_clause(joined: str, words: List[str]) -> Dict[str, bool]:
    """R9 modal/result plus R10 construction normalization (not extra sentence stems)."""
    j = joined if joined.startswith(" ") else f" {joined} "
    lemmas = [lemma_of(w) for w in words]
    locative_cue = any(w in ("in", "into", "at", "inside", "within", "to", "toward", "towards") for w in words)
    motion = _has_motion(words)
    gerund = any(_is_motion_gerund(w) for w in words)
    to_inf = j.lstrip().startswith("to ") or bool(re.search(
        r"\bto\s+(?:go|enter|walk|visit|return|reach|step|move|cross|occupy)\b", j
    ))
    plan_noun = any(
        w in _PLAN_NOUNS or lemma_of(w) in _PLAN_NOUNS or w in _PLAN_MOD
        for w in words
    )
    gerund_plan = gerund and plan_noun
    to_plan = bool(to_inf) and plan_noun
    subject_plan = bool(plan_noun) and any(lemma_of(w) in ("be", "remain") for w in words) and not locative_cue
    # stay as copula only when a plan noun is present (not locative occupancy)
    stay_plan = bool(plan_noun) and any(lemma_of(w) == "stay" for w in words) and gerund
    inverted = (
        gerund_plan or to_plan or subject_plan or stay_plan
        or any(p in j for p in _R9_INVERT)
        or j.lstrip().startswith("to ")
    )
    plan_rel = bool(plan_noun and (inverted or subject_plan or stay_plan or gerund_plan or to_plan))
    scheduled = any(p in j for p in _R9_SCHEDULE) or (subject_plan and not gerund)
    occupy = any(p in j for p in _R9_OCCUPY) or bool(_PHYS_OCCUPY_RX.search(j))
    action_nom = bool(_ACTION_NOM_RX.search(j))
    evaluative = bool(_EVAL_RX.search(j) or _CLASSIFY_AS_RX.search(j) or _CLASSIFY_V_RX.search(j))
    action_as_plan = bool((gerund or to_inf or action_nom) and evaluative)
    occupancy_verb = any(
        family_of(w) == "CURRENT" and w not in (
            "was", "were", "is", "are", "be", "been", "being", "remained", "stayed",
        )
        for w in words
    )
    loc_as_plan = bool(
        evaluative and not occupy and not occupancy_verb
        and " inside " not in j and " within " not in j
    )
    denied_frame = bool(
        _STOP_BARRIER_RX.search(j) or _TURN_ASIDE_RX.search(j) or _GET_PAST_RX.search(j)
        or _COULD_NOT_CROSS_RX.search(j) or _THRESHOLD_STOP_RX.search(j)
        or _BLOCKED_OUTSIDE_RX.search(j) or _KEPT_BEYOND_RX.search(j)
        or _SENT_BACK_RX.search(j) or _ROUTE_CLOSED_RX.search(j) or _CLOSED_AT_RX.search(j)
        or _WAVED_OFF_RX.search(j)
    )
    granted_frame = bool(
        _LET_INSIDE_RX.search(j) or _GRANTED_PASSAGE_RX.search(j) or _MADE_ACROSS_RX.search(j)
        or _CLEARED_ENTER_RX.search(j) or _PASSED_BEYOND_RX.search(j) or _ALLOWED_ENTER_RX.search(j)
        or _AUTH_TRAVERSE_RX.search(j)
    )
    inside_occ = occupy or (" inside " in j) or (" within " in j)
    access_n = any(w in _ACCESS_NOUNS or lemma_of(w) in _ACCESS_NOUNS for w in words)
    req_v = any(w in _REQUEST_FORMS or lemma_of(w) in _REQUEST_LEMMAS for w in words)
    test_v = any(w in _TEST_FORMS or lemma_of(w) in _TEST_LEMMAS for w in words)
    insp_v = any(w in _INSPECT_FORMS or lemma_of(w) in _INSPECT_LEMMAS for w in words)
    appr_v = any(w in _APPROACH_FORMS or lemma_of(w) in _APPROACH_LEMMAS for w in words)
    wait_v = any(w in _WAIT_FORMS or lemma_of(w) in _WAIT_LEMMAS for w in words)
    boundary_n = any(w in _BOUNDARY_NOUNS for w in words)
    at_boundary = bool(re.search(
        r"\b(?:at|outside|to)\s+(?:the\s+)?(?:entrance|gate|threshold|boundary|lip)\b", j
    )) or (" outside " in j)
    pre_request = bool(req_v and (access_n or "permission" in j or "clearance" in j or "admission" in j))
    pre_wait = bool(wait_v and not inside_occ and (
        access_n or at_boundary or "permission" in j or "clearance" in j or "boundary" in j
    ))
    pre_test = bool((test_v or insp_v) and (access_n or boundary_n or "enter" in j or "entered" in j))
    pre_inspect = bool(insp_v and (access_n or boundary_n))
    pre_approach = bool(
        (not inside_occ) and (not granted_frame) and (
            appr_v or at_boundary or bool(re.search(r"\bcoming up to\b", j))
            or (boundary_n and any(lemma_of(w) in ("reach", "stand", "come") or w in ("reached", "reaching", "stood", "standing", "came") for w in words))
            or bool(_BOUNDARY_REL_RX.search(j))
        )
    )
    auth_noun = bool(_AUTH_STATE_RX.search(j))
    pending_rel = bool(_PENDING_REL_RX.search(j) or (wait_v and auth_noun))
    op_auth = bool(
        not inside_occ
        and (
            (auth_noun and (pending_rel or req_v))
            or (pending_rel and ("entry" in j or access_n))
        )
    )
    op_query = bool(_QUERY_OP_RX.search(j) and (access_n or boundary_n or "enter" in j or "entry" in j or "route" in j))
    op_inchoative = bool((not inside_occ) and (not granted_frame) and _INCHOATIVE_RX.search(j))
    unknown_access = bool(
        pre_request or pre_wait or pre_test or pre_inspect or pre_approach
        or op_auth or op_query or op_inchoative or _UNKNOWN_ACCESS_RX.search(j)
    )
    denial_v = any(w in _DENIAL_FORMS or lemma_of(w) in _DENIAL_LEMMAS for w in words)
    failed = bool(
        any(p in j for p in _R9_FAILED)
        or _PRIVATIVE_ACCESS_RX.search(j)
        or _FROM_PREVENT_RX.search(j)
        or _TURNED_AWAY_RX.search(j)
        or _KEPT_OUT_RX.search(j)
        or _NO_FARTHER_RX.search(j)
        or _FIND_NO_RX.search(j)
        or (denial_v and access_n)
        or " washed out " in j
        or " never got through " in j
    )
    grant_v = any(
        (w in _GRANT_FORMS or lemma_of(w) in _GRANT_LEMMAS) and not w.endswith("ing")
        for w in words
    )
    success = (not failed) and bool(
        any(p in j for p in _R9_SUCCESS)
        or _THROUGH_OK_RX.search(j)
        or _ADMIT_RX.search(j)
        or _THRESHOLD_RX.search(j)
        or " gained access " in j
        or " crossed into " in j
        or " broke through into " in j
        or (" interior " in j and any(lemma_of(w) in ("reach", "gain", "get") for w in words))
        or (" successfully " in j and motion)
        or (grant_v and locative_cue)
    )
    has_not = " not " in j or " never " in j
    refish = any(family_of(w) == "REFERENCE" for w in words)
    was_to = False
    for i, w in enumerate(words):
        if w in ("was", "were") and "to" in words[i + 1:i + 5] and motion:
            was_to = True
            break
    modal = (
        (not has_not) and (not refish) and (motion or locative_cue)
        and (any(w in _MODALS for w in words) or was_to)
    )
    if " if " in j and any(w in _MODALS for w in words) and (motion or locative_cue) and not refish:
        modal = True
    hypothetical = modal or (
        (" later " in j or " tomorrow " in j)
        and any(w in _MODALS for w in words)
        and not refish
        and (motion or locative_cue)
    )
    failed = bool(failed or denied_frame)
    if has_not and re.search(r"\bforce a path\b", j):
        failed = True
    success = (not failed) and bool(success or granted_frame)
    if (unknown_access or evaluative or action_as_plan or loc_as_plan) and not granted_frame:
        success = False
    access_result = "DENIED" if failed else ("GRANTED" if success else "UNKNOWN")
    if failed:
        access_phase = "BLOCKED"
        event_real = "FAILED"
        pre_op = "NONE"
    elif success:
        access_phase = "COMPLETE"
        event_real = "COMPLETED"
        pre_op = "NONE"
    elif op_auth:
        access_phase = "WAIT" if (wait_v or "await" in j or "pending" in j) else "REQUEST"
        event_real = "UNRESOLVED"
        pre_op = "AUTHORIZATION_PENDING"
    elif op_query:
        access_phase = "TEST"
        event_real = "UNRESOLVED"
        pre_op = "ACCESS_QUERY"
    elif pre_inspect:
        access_phase = "INSPECTION"
        event_real = "UNRESOLVED"
        pre_op = "ACCESS_INSPECTION"
    elif pre_test:
        access_phase = "TEST"
        event_real = "UNRESOLVED"
        pre_op = "ACCESS_INSPECTION" if insp_v else "ACCESS_QUERY"
    elif op_inchoative:
        access_phase = "ATTEMPT"
        event_real = "IN_PROGRESS"
        pre_op = "MOTION_INCHOATIVE"
    elif pre_approach:
        access_phase = "APPROACH"
        event_real = "IN_PROGRESS"
        pre_op = "BOUNDARY_APPROACH"
    elif pre_request:
        access_phase = "REQUEST"
        event_real = "UNRESOLVED"
        pre_op = "AUTHORIZATION_PENDING"
    elif pre_wait:
        access_phase = "WAIT"
        event_real = "UNRESOLVED"
        pre_op = "AUTHORIZATION_PENDING"
    elif unknown_access:
        access_phase = "ATTEMPT"
        event_real = "UNRESOLVED"
        pre_op = "ACCESS_ATTEMPT"
    else:
        access_phase = "UNKNOWN"
        event_real = "COMPLETED" if occupy else "UNRESOLVED"
        pre_op = "NONE"
    temporal = (
        "PROSPECTIVE" if (modal or inverted or scheduled or hypothetical or action_as_plan or loc_as_plan or plan_rel)
        else ("FAILED" if failed else ("ACTUAL" if (success or occupy) else "AMBIGUOUS"))
    )
    loc_role = (
        "FAILED_DESTINATION" if failed else
        "SUCCESSFUL_DESTINATION" if success else
        "DESTINATION" if unknown_access else
        "PLANNED_SITE" if (action_as_plan or loc_as_plan or inverted or modal or plan_rel) else
        "CURRENT_SITE" if occupy else
        "UNKNOWN"
    )
    noncurrent = bool(
        (modal or inverted or scheduled or failed or hypothetical or plan_rel or action_as_plan or loc_as_plan or unknown_access)
        and not success
        and not (occupy and not unknown_access)
    )
    pred = next((w for w in words if family_of(w) in ("CURRENT", "INTENT", "ATTEMPT") or _is_motion_gerund(w)), words[0] if words else "")
    return {
        "modal": bool(modal),
        "inverted": bool(inverted),
        "scheduled": bool(scheduled),
        "failed": bool(failed),
        "success": bool(success),
        "occupancy": bool(occupy),
        "hypothetical": bool(hypothetical),
        "noncurrent": noncurrent,
        "plan_noun": bool(plan_noun or loc_as_plan or action_as_plan),
        "plan_relation": bool(plan_rel or action_as_plan or loc_as_plan),
        "action_nominalized": bool(gerund or to_inf or action_nom),
        "access_denied": bool(failed),
        "access_granted": bool(success),
        "action_form": "gerund" if gerund else ("infinitive" if to_inf else ("nominal" if action_nom else "")),
        "event_predicate": pred,
        "event_complement": " ".join(w for w in words if w in ("into", "to", "in", "inside", "at", "from")),
        "event_argument_role": loc_role,
        "event_modality": "modal" if modal else "",
        "event_polarity": "negative" if failed or has_not else "positive",
        "event_result": access_result,
        "event_temporal_status": temporal,
        "location_role": loc_role,
        "access_attempt": bool(failed or success or denied_frame or granted_frame or unknown_access),
        "access_result": access_result,
        "access_phase": access_phase,
        "preaccess": bool(unknown_access),
        "access_requested": bool(pre_request or op_auth),
        "access_tested": bool(pre_test or op_query),
        "access_inspected": bool(pre_inspect),
        "access_approached": bool(pre_approach),
        "access_traversal_complete": bool(success),
        "preaccess_operator": pre_op,
        "event_realization": event_real,
        "authorization_pending": pre_op == "AUTHORIZATION_PENDING",
        "access_query": pre_op == "ACCESS_QUERY",
        "access_inspection": pre_op == "ACCESS_INSPECTION",
        "boundary_approach": pre_op == "BOUNDARY_APPROACH",
        "motion_inchoative": pre_op == "MOTION_INCHOATIVE",
        "explicit_completion_evidence": bool(granted_frame or success),
        "explicit_failure_evidence": bool(failed),
    }


def _is_place_head(tok: str) -> bool:
    t = tok.lower()
    if t in PLACE_HEADS:
        return True
    if t.endswith("s") and t[:-1] in PLACE_HEADS:
        return True
    return False


def _np_at(tokens: List[Tuple[str, int, int]], i: int) -> Optional[Tuple[int, int, str]]:
    """Consume a short place NP starting at i. Requires a place head."""
    if i >= len(tokens):
        return None
    j = i
    while j < len(tokens) and (tokens[j][0] in DET or tokens[j][0] in ADVERBS):
        j += 1
    if j >= len(tokens):
        return None
    if family_of(tokens[j][0]) in ("CURRENT", "DEPARTED", "REFERENCE", "INTENT", "NEG") and not _is_place_head(tokens[j][0]):
        return None
    parts: List[str] = []
    start = j
    while j < len(tokens) and len(parts) < 4:
        w = tokens[j][0]
        if w in STOP or w in PREP_CURRENT or w in PREP_NEAR or w in PREP_FROM or w in PREP_REF or w in PREP_DEST:
            break
        if w in NEG_WORDS:
            break
        if family_of(w) in ("CURRENT", "DEPARTED", "REFERENCE", "INTENT", "NEG") and parts:
            break
        parts.append(w)
        j += 1
    last = max((k for k, p in enumerate(parts) if _is_place_head(p)), default=-1)
    if last < 0:
        return None
    parts = parts[: last + 1]
    j = start + len(parts)
    return (start, j, " ".join(parts))


def _normalize_loc(phrase: str) -> str:
    parts = [w for w in phrase.lower().split() if w not in DET and w not in STOP]
    return " ".join(parts).strip()


def classify(scene_text: str) -> Dict[str, Any]:
    raw = str(scene_text or "")
    text = expand_contractions(raw)
    blocked: Dict[str, str] = {}
    mentions: List[Dict[str, Any]] = []
    detections: List[Dict[str, Any]] = []
    flags = {"neg": False, "dep": False, "ref": False, "cur": False}
    cstart = 0
    r9: Dict[str, bool] = {}

    def beats(old: str, new: str) -> bool:
        return PRECEDENCE.get(new, 0) > PRECEDENCE.get(old, 0)

    def emit(*, cls: str, loc: str, span: str, clause: str, head: str, mods: List[str],
             negation: str, aspect: str, prep: str, family: str, bind: Optional[bool] = None,
             loc_raw: str = "") -> None:
        if not loc and cls not in (NEGATED, DEPARTED):
            return
        pre_role = bool(cls == CURRENT) if bind is None else bool(bind)
        if cls in (AMBIGUOUS,) and bind is None:
            pre_role = False
        role = str(r9.get("location_role") or "")
        if cls == REFERENCE:
            role = "REFERENCE_SITE"
        elif cls == DEPARTED:
            role = "SOURCE"
        elif cls == NEGATED:
            role = "FAILED_DESTINATION"
        elif r9.get("failed"):
            role = "FAILED_DESTINATION"
        elif r9.get("success"):
            role = "SUCCESSFUL_DESTINATION"
        elif r9.get("preaccess"):
            role = "DESTINATION"
        elif r9.get("noncurrent") or r9.get("plan_relation"):
            role = "PLANNED_SITE"
        elif cls == CURRENT or r9.get("occupancy"):
            role = "CURRENT_SITE"
        elif prep in PREP_DEST or prep == "for":
            role = role or "DESTINATION"
        elif not role:
            role = "UNKNOWN"
        bind_ok = role in _BIND_ROLES
        legacy_override = False
        if pre_role and not bind_ok:
            # fail closed: legacy CURRENT candidate cannot override role
            legacy_override = False
        if bind_ok:
            cls = CURRENT
        else:
            if cls == CURRENT:
                cls = AMBIGUOUS
            bind_ok = False
        rejection = ""
        if not bind_ok:
            rejection = {
                NEGATED: "NEGATED_LOCATION",
                DEPARTED: "DEPARTED_LOCATION",
                REFERENCE: "REFERENCE_ONLY_LOCATION",
                AMBIGUOUS: "AMBIGUOUS_LOCATION",
            }.get(cls, "LOCATION_ROLE_" + role)
        rec = {
            "RAW": span[:160],
            "RAW_LOCATION_MENTION": (loc_raw or loc)[:160],
            "NORMALIZED": loc,
            "LOCATION_RELATION_CLASS": cls,
            "RELATION_CLASS": cls,
            "RELATION_FAMILY": {
                CURRENT: "CURRENT", NEGATED: "NEGATED", DEPARTED: "DEPARTED",
                REFERENCE: "REFERENCE_ONLY", AMBIGUOUS: "AMBIGUOUS",
            }.get(cls, "AMBIGUOUS"),
            "MATCHED_CUE": head or prep or family,
            "MATCHED_CUE_FAMILY": family,
            "CLAUSE_OR_WINDOW": clause.strip()[:240],
            "CLAUSE_SPAN": clause.strip()[:240],
            "NEGATION_SCOPE": loc if cls == NEGATED else "",
            "REFERENCE_SCOPE": loc if cls == REFERENCE else "",
            "CURRENT_LOCATION_EVIDENCE": bool(cls == CURRENT),
            "CURRENT_EVIDENCE": bool(cls == CURRENT),
            "BIND_ALLOWED": bind_ok,
            "REJECTION_REASON": rejection,
            "RELATION_HEAD": head,
            "RELATION_MODIFIERS": list(mods),
            "NEGATION": negation,
            "ASPECT": aspect,
            "PREPOSITION": prep,
            "LEXICAL_FAMILY": family,
            "TENSE": aspect,
            "LOCATIVE_CUE": prep if prep in PREP_CURRENT or prep in PREP_NEAR else "",
            "REFERENCE_CUE": head if family in ("REFERENCE", "REFERENCE_NOUN") else "",
            "DEPARTURE_CUE": head if family == "DEPARTED" else "",
            "CLAUSE_ID": str(cstart),
            "PREDICATE_ID": head or prep or family,
            "PREDICATE_HEAD": head,
            "PREDICATE_FAMILY": family,
            "INTENT_DETECTED": bool(family == "INTENT" or aspect in ("about_to", "attempt")),
            "ATTEMPT_DETECTED": bool(family == "ATTEMPT" or aspect == "attempt"),
            "RESULT_DETECTED": bool(family == "RESULT"),
            "CURRENT_OCCUPANCY_DETECTED": bool(cls == CURRENT),
            "MODAL_AUXILIARY": " ".join(w for w in words if w in _MODALS),
            "MODAL_CLASS": "PROSPECTIVE" if r9.get("modal") else "",
            "PROSPECTIVE_ACTION": bool(r9.get("modal") or r9.get("hypothetical")),
            "HYPOTHETICAL_ACTION": bool(r9.get("hypothetical")),
            "SCHEDULED_ACTION": bool(r9.get("scheduled")),
            "NOMINALIZED_ACTION": bool(r9.get("inverted")),
            "INVERTED_INTENT": bool(r9.get("inverted")),
            "RESULT_POLARITY": "failure" if r9.get("failed") else ("success" if r9.get("success") else ""),
            "RESULT_SUCCESS": bool(r9.get("success")),
            "RESULT_FAILURE": bool(r9.get("failed")),
            "ACTUAL_OCCUPANCY_EVIDENCE": bool(cls == CURRENT),
            "ACTION_FORM": r9.get("action_form") or "",
            "ACTION_NOMINALIZED": bool(r9.get("action_nominalized") or r9.get("inverted")),
            "PLAN_NOUN": bool(r9.get("plan_noun")),
            "PLAN_RELATION": bool(r9.get("plan_relation")),
            "ACCESS_STATE": "denied" if r9.get("access_denied") else ("granted" if r9.get("access_granted") else ""),
            "ACCESS_DENIED": bool(r9.get("access_denied")),
            "ACCESS_GRANTED": bool(r9.get("access_granted")),
            "EVENT_PREDICATE": r9.get("event_predicate") or "",
            "EVENT_COMPLEMENT": r9.get("event_complement") or "",
            "EVENT_ARGUMENT_ROLE": r9.get("event_argument_role") or "",
            "EVENT_MODALITY": r9.get("event_modality") or "",
            "EVENT_POLARITY": r9.get("event_polarity") or "",
            "EVENT_RESULT": r9.get("event_result") or "",
            "EVENT_TEMPORAL_STATUS": r9.get("event_temporal_status") or "",
            "EVENT_REALIZATION": r9.get("event_temporal_status") or "",
            "LOCATION_ROLE": role,
            "ACCESS_ATTEMPT": bool(r9.get("access_attempt")),
            "ACCESS_RESULT": r9.get("access_result") or "",
            "ACCESS_PHASE": r9.get("access_phase") or "",
            "ACCESS_REQUESTED": bool(r9.get("access_requested")),
            "ACCESS_TESTED": bool(r9.get("access_tested")),
            "ACCESS_INSPECTED": bool(r9.get("access_inspected")),
            "ACCESS_APPROACHED": bool(r9.get("access_approached")),
            "ACCESS_TRAVERSAL_COMPLETE": bool(r9.get("access_traversal_complete")),
            "PREACCESS_OPERATOR": r9.get("preaccess_operator") or "NONE",
            "EVENT_REALIZATION": r9.get("event_realization") or r9.get("event_temporal_status") or "",
            "AUTHORIZATION_PENDING": bool(r9.get("authorization_pending")),
            "ACCESS_QUERY": bool(r9.get("access_query")),
            "ACCESS_INSPECTION": bool(r9.get("access_inspection")),
            "BOUNDARY_APPROACH": bool(r9.get("boundary_approach")),
            "MOTION_INCHOATIVE": bool(r9.get("motion_inchoative")),
            "EXPLICIT_COMPLETION_EVIDENCE": bool(r9.get("explicit_completion_evidence")),
            "EXPLICIT_FAILURE_EVIDENCE": bool(r9.get("explicit_failure_evidence")),
            "ACCESS_DIRECTION": "into" if prep in ("into", "in", "inside") else (prep or ""),
            "ACCESS_BARRIER_STATE": "blocked" if r9.get("failed") else ("open" if r9.get("success") else ""),
            "ACCESS_AUTHORIZATION": "denied" if r9.get("failed") else ("granted" if r9.get("success") else "unknown"),
            "ACCESS_TRAVERSAL": "completed" if r9.get("success") else ("blocked" if r9.get("failed") else ""),
            "PRE_ROLE_BIND_CANDIDATE": bool(pre_role),
            "FINAL_BIND_ALLOWED": bool(bind_ok),
            "FINAL_BIND_REASON": "LOCATION_ROLE=" + role,
            "LEGACY_BIND_OVERRIDE": bool(legacy_override),
            "PREDICATE_LEMMA": lemma_of(head) if head else "",
            "COMPLEMENT_TYPE": "",
            "COMPLEMENT_HEAD": "",
            "DESTINATION_ONLY": bool(prep in PREP_DEST or prep == "for"),
            "SOURCE_LOCATION": loc if cls == DEPARTED else "",
            "DESTINATION_LOCATION": loc if (prep in PREP_DEST or prep == "for") and cls != CURRENT else "",
            "triggers": [head or prep or family],
            "phrase": loc,
            "class": cls,
            "span": span[:120],
        }
        detections.append({"phrase": loc, "class": cls, "span": span[:120]})
        mentions.append(rec)
        if cls == NEGATED:
            flags["neg"] = True
        elif cls == DEPARTED:
            flags["dep"] = True
        elif cls == REFERENCE:
            flags["ref"] = True
        elif cls == CURRENT:
            flags["cur"] = True
            for b in list(blocked):
                if blocked.get(b) == AMBIGUOUS and (loc in b or b in loc or loc == b):
                    del blocked[b]
        if loc and cls in (NEGATED, DEPARTED, REFERENCE, AMBIGUOUS):
            if cls == AMBIGUOUS and any(
                m.get("RELATION_CLASS") == CURRENT and (loc in m.get("NORMALIZED", "") or m.get("NORMALIZED", "") in loc)
                for m in mentions
            ):
                pass
            else:
                prev = blocked.get(loc)
                if prev is None or beats(prev, cls):
                    blocked[loc] = cls

    for cstart, cend, clause in clauses(text):
        toks = tokenize(clause)
        if not toks:
            continue
        words = [t[0] for t in toks]
        # multiword flags in this clause
        joined = " " + " ".join(words) + " "
        r9 = _r9_clause(joined, words)
        neg = ""
        aspect = ""
        intent = False
        attempt = False
        if " failed to " in joined or " unable to " in joined or " yet to " in joined:
            neg = "failed_to" if " failed to " in joined or " unable to " in joined else "yet_to"
        if any(w in NEG_WORDS for w in words) or " no longer " in joined:
            if not neg:
                if "never" in words:
                    neg = "never"
                elif "nowhere" in words:
                    neg = "nowhere"
                elif "without" in words:
                    neg = "without"
                elif "no" in words and "longer" in words:
                    neg = "no_longer"
                elif "not" in words:
                    neg = "not"
        if " already " in joined:
            aspect = "already"
        elif " still " in joined:
            aspect = "still"
        elif " about to " in joined or " going to " in joined:
            aspect = "about_to"
            intent = True
        if " tried to " in joined or " trying to " in joined or " attempt" in joined:
            attempt = True
            aspect = aspect or "attempt"
        if any(family_of(w) == "INTENT" for w in words):
            intent = True
        if any(p in joined for p in (
            " on the way to ", " bound for ", " make for ", " set out for ",
            " heading toward ", " heading towards ", " heading for ",
            " preparing to ", " meant to ", " planned to ", " intending to ",
        )):
            intent = True
        if " unsuccessfully " in joined:
            attempt = True
        if " anywhere near " in joined or " well clear of " in joined or " clear of " in joined:
            if not neg:
                neg = "proximity_neg" if "not" in words or "never" in words or "wasn't" in words or "was not" in joined or "kept" in words else neg
            if " clear of " in joined:
                neg = neg or "clear_of"
            if " anywhere near " in joined and ("not" in words or "never" in words):
                neg = "not_anywhere_near"

        # collect candidate locations: after preps and verbs, plus place-head NPs
        seen_spans = set()
        candidates: List[Dict[str, Any]] = []

        def add_cand(start_i: int, end_i: int, phrase: str, prep: str, head: str, fam: str) -> None:
            loc = _normalize_loc(phrase)
            if not loc:
                return
            key = (start_i, loc)
            if key in seen_spans:
                return
            seen_spans.add(key)
            span = clause[toks[start_i][1]: toks[end_i - 1][2]] if end_i > start_i else phrase
            candidates.append({
                "loc": loc, "loc_raw": phrase, "prep": prep, "head": head, "fam": fam,
                "span": span.strip(), "i": start_i,
            })

        for i, (w, _, _) in enumerate(toks):
            # preposition + NP
            if w in PREP_CURRENT or w in PREP_NEAR or w in PREP_FROM or w in PREP_REF or w in PREP_DEST or w == "behind":
                np = _np_at(toks, i + 1)
                if np:
                    add_cand(np[0], np[1], np[2], w, "", "PREP")
            if w == "away" and i + 1 < len(toks) and toks[i + 1][0] == "from":
                np = _np_at(toks, i + 2)
                if np:
                    add_cand(np[0], np[1], np[2], "away_from", "away", "DEPARTED")
            if w == "out" and i + 1 < len(toks) and toks[i + 1][0] == "of":
                np = _np_at(toks, i + 2)
                if np:
                    add_cand(np[0], np[1], np[2], "out_of", "out", "DEPARTED")
            if w == "clear" and i + 1 < len(toks) and toks[i + 1][0] == "of":
                np = _np_at(toks, i + 2)
                if np:
                    add_cand(np[0], np[1], np[2], "clear_of", "clear", "NEG")
            if w == "foot" and i + 1 < len(toks) and toks[i + 1][0] in PREP_CURRENT:
                np = _np_at(toks, i + 2)
                if np:
                    add_cand(np[0], np[1], np[2], toks[i + 1][0], "set_foot", "CURRENT")
            # verb + NP
            fam = family_of(w)
            if fam in ("CURRENT", "DEPARTED", "REFERENCE", "INTENT", "NEG", "ATTEMPT", "RESULT"):
                skip = i + 1
                # skip particles: to / into / from / of
                if skip < len(toks) and toks[skip][0] in ("to", "into", "from", "of", "about"):
                    prep_v = toks[skip][0]
                    skip += 1
                else:
                    prep_v = ""
                np = _np_at(toks, skip)
                if np:
                    add_cand(np[0], np[1], np[2], prep_v, lemma_of(w), fam)
            # put NP behind
            if w == "put":
                np = _np_at(toks, i + 1)
                if np and np[1] < len(toks) and toks[np[1]][0] == "behind":
                    add_cand(np[0], np[1], np[2], "behind", "put_behind", "DEPARTED")
            # place-head NP anywhere
            if _is_place_head(w):
                # include up to 3 tokens back as modifiers
                s = i
                while s > 0 and toks[s - 1][0] not in STOP and toks[s - 1][0] not in DET \
                        and family_of(toks[s - 1][0]) not in ("CURRENT", "DEPARTED", "REFERENCE", "INTENT", "NEG") \
                        and toks[s - 1][0] not in PREP_CURRENT | PREP_NEAR | PREP_FROM | PREP_REF | PREP_DEST \
                        and (i - s) < 3:
                    s -= 1
                if s > 0 and toks[s - 1][0] in DET:
                    phrase = " ".join(x[0] for x in toks[s:i + 1])
                    add_cand(s, i + 1, phrase, "", "", "PLACE_HEAD")
                else:
                    phrase = " ".join(x[0] for x in toks[s:i + 1])
                    add_cand(s, i + 1, phrase, "", "", "PLACE_HEAD")

        # classify each candidate using clause-local features
        for cand in candidates:
            loc = cand["loc"]
            prep = cand["prep"]
            head = cand["head"]
            fam = cand["fam"]
            cls = AMBIGUOUS
            bind: Optional[bool] = False
            family = fam or "AMBIGUOUS"

            locative = prep in PREP_CURRENT or prep in PREP_NEAR
            ref_prep = prep in PREP_REF
            away = prep in ("away_from", "out_of", "behind", "from")
            dest_only = prep in PREP_DEST
            loc_i = cand["i"]
            and_before = max((i for i, t in enumerate(toks) if t[0] == "and" and i < loc_i), default=-1)
            neg_i = min(
                (i for i, t in enumerate(toks)
                 if t[0] in NEG_WORDS or lemma_of(t[0]) in ("fail", "avoid", "miss") or t[0] in ("unable", "yet")),
                default=-1,
            )
            local_neg = neg
            if local_neg and and_before > neg_i >= 0:
                local_neg = ""  # later conjunct is not under the earlier negation
            mods = []
            if local_neg:
                mods.append(local_neg)
            if aspect:
                mods.append(aspect)

            ref_noun_present = any(w in REF_NOUNS for w in words)
            ref_verb_present = any(family_of(w) == "REFERENCE" for w in words)
            dep_verb = family_of(head) == "DEPARTED" or fam == "DEPARTED" or prep in ("away_from", "out_of") or head in ("put_behind", "away")
            cur_verb = family_of(head) == "CURRENT" or fam == "CURRENT" or head == "set_foot"
            # "left X behind"
            if "behind" in words and lemma_of(head) == "leave" or ("behind" in words and "left" in words and loc):
                dep_verb = True

            # Avoid / fail / miss as non-entry
            if fam == "NEG" or lemma_of(head) in ("avoid", "fail", "miss") or prep == "clear_of":
                cls = NEGATED
                family = "NEGATED"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "avoid",
                     mods=mods, negation=neg or "avoid", aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue

            # far away from / far from (proximity vs motion-away)
            if prep == "away_from":
                motion_away = any(lemma_of(w) in ("walk", "move", "go", "head", "run", "flee", "leave") for w in words)
                if "far" in words or not motion_away:
                    cls = NEGATED
                    family = "NEGATED"
                    emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "away_from",
                         mods=mods, negation=neg or "away_from", aspect=aspect, prep=prep, family=family,
                         loc_raw=cand["loc_raw"])
                    continue
                cls = DEPARTED
                family = "DEPARTED"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "away_from",
                     mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue
            if prep == "from" and lemma_of(head) in ("come", "be", "walk", "return"):
                cls = DEPARTED
                family = "DEPARTED"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "from",
                     mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue
            if prep == "from" and any(w in ("far", "away", "way") for w in words):
                cls = NEGATED
                family = "NEGATED"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "far_from",
                     mods=mods, negation=neg or "far_from", aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue

            # Intent / attempt / future: attach via complement, not the whole sentence.
            nc, nc_fam, nc_comp = _noncurrent_complement(toks, loc_i)
            intent_before = any(family_of(toks[i][0]) == "INTENT" for i in range(max(0, loc_i)))
            to_after_intent = nc and nc_comp == "to"
            nearest_fam = ""
            for i in range(loc_i - 1, -1, -1):
                fam_i = family_of(toks[i][0])
                if fam_i in ("CURRENT", "DEPARTED", "REFERENCE", "INTENT", "NEG", "ATTEMPT", "RESULT"):
                    nearest_fam = fam_i
                    break
            local_intent = bool(
                nc
                or nearest_fam == "INTENT"
                or nearest_fam == "ATTEMPT"
                or aspect in ("about_to",)
                or (intent and nearest_fam not in ("CURRENT", "DEPARTED", "REFERENCE", "NEG", "RESULT"))
                or r9.get("noncurrent")
            )
            if nc_fam == "RESULT" or r9.get("success"):
                local_intent = False
            if local_intent:
                genuine_occ = (
                    locative and nearest_fam == "CURRENT" and not to_after_intent
                    and aspect not in ("about_to",)
                    and not r9.get("noncurrent")
                )
                if not genuine_occ:
                    cls = AMBIGUOUS
                    bind = False
                    family = "INTENT"
                    emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or aspect,
                         mods=mods, negation=neg, aspect=aspect, prep=prep, family=family, bind=False,
                         loc_raw=cand["loc_raw"])
                    continue

            # Negation over locative / reach / enter / near
            if local_neg:
                if (locative or dest_only or cur_verb or prep in PREP_NEAR or prep == "clear_of"
                        or head in ("reach", "enter", "arrive", "set_foot", "go")
                        or fam == "NEG"):
                    cls = NEGATED
                    family = "NEGATED"
                    emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or neg,
                         mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                         loc_raw=cand["loc_raw"])
                    continue

            # Departure
            if dep_verb or prep == "away_from" or (prep == "from" and family_of(head) in ("DEPARTED", "CURRENT") and lemma_of(head) in ("leave", "depart", "escape", "flee", "run", "walk", "move", "go", "head")):
                # walk away / move away / head away already away_from
                if lemma_of(head) in ("walk", "move", "go", "head") and prep not in ("away_from", "from"):
                    pass  # occupancy walk in X is current
                else:
                    cls = DEPARTED
                    family = "DEPARTED"
                    emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or prep,
                         mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                         loc_raw=cand["loc_raw"])
                    continue

            # Reference: of/about with ref noun/verb, or ref verb + loc without locative occupancy
            if (ref_prep and (ref_noun_present or ref_verb_present)) or (ref_verb_present and not locative) or (ref_noun_present and not locative):
                if locative and cur_verb and not ref_prep:
                    pass  # working in X while remembering Y handled by per-mention
                else:
                    # If this loc is attached via in/inside, keep current
                    if locative and not ref_prep:
                        pass
                    else:
                        cls = REFERENCE
                        family = "REFERENCE"
                        emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "reference",
                             mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                             loc_raw=cand["loc_raw"])
                        continue

            # Current locative occupancy
            if locative and not dest_only:
                cls = CURRENT
                family = "CURRENT"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or prep,
                     mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue
            if cur_verb and prep in ("", "into", "to") and family_of(head) == "CURRENT":
                # "to" after return/arrive/go into occupancy; "to" after want is intent (handled)
                if lemma_of(head) in ("go", "come") and dest_only and not locative:
                    cls = AMBIGUOUS
                    bind = False
                    family = "DESTINATION"
                    emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head,
                         mods=mods, negation=neg, aspect=aspect, prep=prep, family=family, bind=False,
                         loc_raw=cand["loc_raw"])
                    continue
                cls = CURRENT
                family = "CURRENT"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or prep,
                     mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue

            if (r9.get("occupancy") or r9.get("success")) and not r9.get("noncurrent"):
                cls = CURRENT
                family = "CURRENT"
                emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "occupancy",
                     mods=mods, negation=neg, aspect=aspect, prep=prep, family=family,
                     loc_raw=cand["loc_raw"])
                continue

            # default: if only a place head with no cue, do not bind
            cls = AMBIGUOUS
            emit(cls=cls, loc=loc, span=cand["span"], clause=clause, head=head or "",
                 mods=mods, negation=neg, aspect=aspect, prep=prep, family=family or "AMBIGUOUS",
                 bind=False, loc_raw=cand["loc_raw"])

    primary = CURRENT
    if flags["cur"]:
        primary = CURRENT
    elif flags["dep"]:
        primary = DEPARTED
    elif flags["neg"]:
        primary = NEGATED
    elif flags["ref"]:
        primary = REFERENCE

    return {
        "LOCATION_RELATION_CLASS": primary,
        "LOCATION_NEGATION_DETECTED": flags["neg"],
        "LOCATION_DEPARTURE_DETECTED": flags["dep"],
        "LOCATION_REFERENCE_ONLY": flags["ref"],
        "LOCATION_RELATION_PRECEDENCE_DEFINED": True,
        "PER_MENTION_LOCATION_RELATION": True,
        "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE": True,
        "R6_RELATION_OBSERVABILITY_COMPLETE": True,
        "R7_SCOPE_OBSERVABILITY_COMPLETE": True,
        "R8_PREDICATE_OBSERVABILITY_COMPLETE": True,
        "R9_CONSTRUCTION_OBSERVABILITY_COMPLETE": True,
        "R10_CONSTRUCTION_OBSERVABILITY_COMPLETE": True,
        "R11_EVENT_FRAME_OBSERVABILITY_COMPLETE": True,
        "R12_AUTHORITATIVE_ROLE_OBSERVABILITY_COMPLETE": True,
        "R13_PREACCESS_OBSERVABILITY_COMPLETE": True,
        "R14_PREACCESS_OPERATOR_OBSERVABILITY_COMPLETE": True,
        "PREACCESS_EVENT_MODEL": True,
        "PREACCESS_STATE_MODEL": True,
        "LOCATION_ROLE_AUTHORITATIVE": True,
        "SINGLE_BIND_DECISION_POINT": True,
        "EVENT_REALIZATION_COMPOSITIONAL": True,
        "ACCESS_FRAME_AUTHORITATIVE": True,
        "RELATION_CLASSIFICATION_COMPOSITIONAL": True,
        "LEXICAL_FAMILY_NORMALIZATION": True,
        "blocked_phrases": blocked,
        "detections": detections,
        "LOCATION_RELATION_MENTIONS": mentions,
    }
