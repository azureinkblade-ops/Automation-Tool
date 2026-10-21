"""Scene environment consistency — SceneEnvironmentSpec + novel-scoped location authority.

Bounded remediation for SCENE_ENVIRONMENT_CONSISTENCY_REMEDIATION (Parts A–P) and
SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Parts B–F, M).
Domain: environment / location / composition only. Does NOT invent canon, does NOT
touch identity / wardrobe / held-prop / scene-critical-effects contracts.

Authority precedence (highest wins):
  TEXT_CANON_SCENE > STUDIO_BIBLE_LOCATION > SCENE_CONTEXT > VISUAL_DIRECTION > MODEL_PRIOR

R2 location evidence policy:
  * Character names (governed + Studio Bible character names, possessives) are NEVER
    location evidence; Bible `history` (relationship / context prose) is not scored.
  * Evidence classes: CANONICAL_NAME, PLACE_ALIAS, PLACE_DESCRIPTOR (architecture /
    terrain), ENVIRONMENT_DESCRIPTOR (lighting / weather / particles / magic / weak cues).
  * Binding requires positive place evidence (a canonical-name or place-alias hit, a
    multi-word place descriptor, or two distinct single-word place descriptors).
    Environment descriptors alone never bind (e.g. 'rain' does not bind ha_alley).
  * Otherwise LOCATION_ID=UNRESOLVED with a neutral environment derived only from
    validated scene-context place phrases (deterministic grammar, no LLM).

Unknown locations never borrow foreign landmarks across novels.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

# ---- Part A: authority precedence -------------------------------------------------
AUTHORITY_PRECEDENCE: Tuple[str, ...] = (
    "TEXT_CANON_SCENE",
    "STUDIO_BIBLE_LOCATION",
    "SCENE_CONTEXT",
    "VISUAL_DIRECTION",
    "MODEL_PRIOR",
)

UNSPECIFIED = "UNSPECIFIED"
UNRESOLVED = "UNRESOLVED"
UNRESOLVED_LOCATION_POLICY = "NEUTRAL"
NO_LOCATION_IDS = (UNSPECIFIED, UNRESOLVED, "")

# Hard HP landmarks that must never appear in HA/EN/SF environment language.
HP_HARD_LANDMARKS: Tuple[str, ...] = (
    "ruined sect hall",
    "jade altar",
    "sect hall",
)
HP_SOFT_LANDMARKS: Tuple[str, ...] = HP_HARD_LANDMARKS + (
    "broken jade railing",
    "jade railings",
    "dormant formation",
    "jade mist",
    "qi motes",
)

# Per-novel foreign landmarks used for leak rejection (Part I).
FOREIGN_LANDMARKS: Dict[str, Tuple[str, ...]] = {
    "ha": (
        "ruined sect hall", "jade altar", "sect hall", "neon city", "soulforge",
        "iron chains", "obsidian pod", "nexus portal",
    ),
    "en": (
        "ruined sect hall", "jade altar", "sect hall", "apartment stairwell",
        "soulforge era", "iron chains", "system panel",
    ),
    "hp": (
        "neon city", "apartment kitchen", "soulforge", "iron chains",
        "system panel", "obsidian pod", "skybridge",
    ),
    "sf": (
        "ruined sect hall", "jade altar", "sect hall", "neon city",
        "apartment kitchen", "system panel", "nexus portal",
    ),
}

# Part B (R2): scene-cue aliases -> EXISTING Studio Bible location ids only.
# Source: Inkblade Author Studio/scripts/aivsb/locations/locations.yaml (no invented ids).
# PLACE aliases are positive place evidence; ENVIRONMENT cues are weak supporting evidence
# only and can never bind a location on their own.
PLACE_ALIASES: Dict[str, Dict[str, str]] = {
    "en": {
        "nexuspod": "en_nexus_pod",
        "nexus pod": "en_nexus_pod",
        "one-room apartment": "en_nexus_pod",
        # R4: bare "apartment" removed — home-bias false bind onto Mira's apartment / generic apartment
        # mentions. Specific "one-room apartment" / nexus pod aliases retained.
        "portal chamber": "en_nexus_portal",
        "nexus portal": "en_nexus_portal",
        "shadowforge": "en_nexus_portal",
        "initiation chamber": "en_nexus_portal",
        "skybridge": "en_nexus_city",
        "megacity": "en_nexus_city",
        "rooftop": "en_nexus_city",
        "city grid": "en_nexus_city",
        "skyline": "en_nexus_city",
        "nexus city": "en_nexus_city",
    },
    "ha": {
        # Only ha_alley exists in Studio Bible for HA. Apartment/kitchen/hallway
        # have no HA bible location -> UNRESOLVED (no borrow).
        "alley": "ha_alley",
        "back alley": "ha_alley",
        "alleyway": "ha_alley",
    },
    "hp": {
        "sect hall": "hp_sect",
        "ruined sect": "hp_sect",
        "jade altar": "hp_sect",
        "sect courtyard": "hp_sect",
        "mountain sect": "hp_sect",
        "jade hall": "hp_sect",
        "broken stair": "hp_sect",
        "ancient ruins": "hp_ruins",
        "collapsed pillars": "hp_ruins",
    },
    "sf": {
        "forge": "sf_forge",
        "soul-forge": "sf_forge",
        "soulforge": "sf_forge",
        "sanctuary": "sf_sanctuary",
        "vessel passage": "sf_sanctuary",
    },
}
ENVIRONMENT_CUES: Dict[str, Dict[str, str]] = {
    "en": {"neon": "en_nexus_city", "traffic": "en_nexus_city", "holographic": "en_nexus_portal"},
    "ha": {"wet pavement": "ha_alley"},
    "hp": {"molten-copper": "hp_ruins"},
    "sf": {
        "anvil": "sf_forge", "chains": "sf_forge", "bellows": "sf_forge", "cinders": "sf_forge",
        "ash": "sf_forge", "slag": "sf_forge", "industrial": "sf_forge",
    },
}
# Back-compat name: the positive (place) alias table.
LOCATION_ALIASES: Dict[str, Dict[str, str]] = PLACE_ALIASES

STILL_ROLES: Tuple[str, ...] = ("establishing", "travel", "climax")

# Novel-neutral framing templates (no landmark nouns). Placeholders filled from
# resolved environment / scene action only.
_CAMERA_TEMPLATES: Tuple[str, ...] = (
    "full-body medium shot of {subject} {action_clause}; {subject} fills approximately 20 to 25 percent of the frame height and is immediately recognizable even at thumbnail size, while {place} fills the background",
    "over-the-shoulder tracking shot from behind {subject} {motion_clause}; {subject} fills approximately 20 to 25 percent of the frame height and is clearly visible and prominent, with {place_ahead} ahead",
    "three-quarter side view at subject height, {subject} clearly the subject {climax_clause}; {subject} fills approximately 20 to 25 percent of the frame height",
)

_POSE_TEMPLATES: Tuple[str, ...] = (
    "standing at the threshold, head tilted upward, reading the space ahead",
    "advancing through the middle ground, one foot forward, body leaning into motion",
    "holding the decisive stance at the focal point, grounded, attention locked on the turning moment",
)

# R2 Part E/F: per-role camera vocabulary for the AIVSB effective prefix. Camera ids are
# single snake_case tokens so the composer header "<novel>, expressing <e>, <camera> shot"
# (identity_preservation AIVSB format signature backstop) is preserved.
ROLE_CAMERAS: Dict[str, Dict[str, str]] = {
    "establishing": {"camera": "wide_establishing", "lens": "24mm",
                     "composition": "full figure small in a wide environment frame"},
    "travel": {"camera": "over_shoulder_tracking", "lens": "35mm",
               "composition": "rear three-quarter view in motion with leading lines"},
    "climax": {"camera": "low_angle_closeup", "lens": "85mm",
               "composition": "tight framing on face and hands at the decisive moment"},
}


@dataclass
class SceneEnvironmentSpec:
    """Resolved environment binding for one still / package."""

    novel: str
    location_id: str = UNRESOLVED
    location_name: str = UNRESOLVED
    authority: str = "MODEL_PRIOR"
    place_phrase: str = "a neutral setting"
    architecture: str = ""
    lighting: str = ""
    environment_state: str = ""
    damage_state: str = ""
    weather: str = ""
    ambient_particles: str = ""
    magic_effects: str = ""
    scene_action: str = ""
    still_index: int = 0
    still_role: str = "establishing"
    composition_goal: str = ""
    hp_landmarks_allowed: bool = False
    unknown_location: bool = True
    observability: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["authority_precedence"] = list(AUTHORITY_PRECEDENCE)
        return d


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _has_phrase(text_norm: str, phrase: str) -> bool:
    """Word-boundary phrase match (plural tolerant). text_norm must be _norm()'d."""
    p = _norm(phrase)
    if not p:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?:s|es)?(?![a-z0-9])", text_norm) is not None


def scan_landmarks(text: str, landmarks: Sequence[str]) -> List[str]:
    low = _norm(text)
    return [lm for lm in landmarks if lm in low]


def foreign_landmarks_for(novel: str) -> Tuple[str, ...]:
    return FOREIGN_LANDMARKS.get(str(novel).lower(), HP_HARD_LANDMARKS)


def reject_cross_novel_landmarks(novel: str, text: str) -> List[str]:
    """Return foreign landmarks found in text for the given novel (empty = clean)."""
    return scan_landmarks(text, foreign_landmarks_for(novel))


# ---- R2 Part B: character-name decontamination ---------------------------------------
# Governed / recurring character display names (also used for AIVSB name scrubbing).
_GOVERNED_DISPLAY_NAMES = (
    "Liang", "Kai", "Kael Veyra", "Kael", "Jarek", "Gray", "Elyen", "Marta",
)
_CHAR_NAME_CACHE: Dict[str, Tuple[str, ...]] = {}


def character_name_tokens() -> Tuple[str, ...]:
    """Lowercase name tokens of governed + Studio Bible characters (never location evidence)."""
    if "all" in _CHAR_NAME_CACHE:
        return _CHAR_NAME_CACHE["all"]
    names = set()
    for n in _GOVERNED_DISPLAY_NAMES:
        for t in _norm(n).split():
            names.add(t)
    try:  # Studio Bible character names (read-only, lazy to avoid an import cycle)
        import visual_director as _vd  # noqa: WPS433

        for key, prof in (_vd.load_character_profiles() or {}).items():
            for src in (key, str((prof or {}).get("name") or "")):
                for t in re.findall(r"[a-z][a-z'\-]+", _norm(src)):
                    t = t.strip("'-")
                    if len(t) >= 3:
                        names.add(t)
    except Exception:
        pass
    out = tuple(sorted(names, key=len, reverse=True))
    _CHAR_NAME_CACHE["all"] = out
    return out


def strip_character_tokens(text: str, extra_names: Optional[Sequence[str]] = None) -> Tuple[str, List[str]]:
    """Remove character names (incl. possessives) from text. Returns (clean_norm_text, rejected)."""
    low = _norm(text)
    names = list(character_name_tokens()) + [_norm(n) for n in (extra_names or []) if n]
    rejected: List[str] = []
    for n in sorted(set(names), key=len, reverse=True):
        if not n:
            continue
        pat = r"(?<![a-z0-9])" + re.escape(n) + r"(?:'s|s'|’s)?(?![a-z0-9])"
        if re.search(pat, low):
            rejected.append(n)
            low = re.sub(pat, " ", low)
    return re.sub(r"\s+", " ", low).strip(), rejected


# ---- R2 Part D: deterministic place extractor -----------------------------------------
PLACE_HEAD_NOUNS = frozenset("""
alley alleyway apartment apartments stairwell staircase stairway stair stairs hallway corridor kitchen room
bedroom bathroom lobby elevator basement cellar attic balcony rooftop roof hall halls chamber chambers market
bazaar village town city megacity street streets road lane avenue boulevard highway bridge skybridge overpass
square plaza courtyard yard garden park forest woods grove jungle mountain mountains peak summit cliff valley
canyon gorge ravine river lake pond sea ocean shore beach coast harbor dock pier island desert field fields
meadow farm orchard temple shrine sanctuary altar pavilion sect monastery tower towers gate gateway entrance
doorway threshold library archive archives office shop stall tavern inn house home building district
undercity slum station platform subway tunnel sewer warehouse factory workshop smithy foundry forge forges
arena camp tent barracks fortress castle palace dungeon cell prison mine mines ruins ruin cave cavern crypt
tomb cemetery graveyard pod portal skyline cafe restaurant bar club classroom school hospital ward clinic lab
laboratory hangar deck cabin ship vessel passage passages pathway path trail crossroads intersection pavement
sidewalk counter desk table window windows rooftops roofs walls wall terrace veranda porch cottage hut manor
estate compound hideout den lair grotto gallery theater
""".split())
# 'counter', 'desk', 'table', 'window', 'wall' are scene-setting anchors (placement), accepted
# only together with a preposition (handled by the grammar), never bound to Bible canon.
TEMPORAL_DISCOURSE_TOKENS = frozenset("""
once twice since until dawn dusk noon midnight morning evening night tonight today tomorrow yesterday moment
moments time times review reviews word words edge while when then later soon after before during ever never
always again sometimes meanwhile instead though although because whatever whenever whoever however perhaps
maybe already still just only even also very really thing things something nothing everything anything way
ways part parts kind sort fact case point side reason question answer idea truth sense manner order chance
voice silence breath thought thoughts mind memory memories name names life death sky light dark darkness
""".split())
_PREPOSITIONS = (
    "in", "at", "on", "inside", "into", "through", "across", "beneath", "under", "below", "near",
    "beside", "within", "toward", "towards", "along", "onto", "over", "outside", "behind", "above",
    "from", "before", "around", "past", "among", "amid", "throughout", "atop", "upon",
)
_DETERMINERS = ("the", "a", "an", "his", "her", "their", "its", "my", "our", "your", "this", "that",
                "these", "those", "some", "every", "each")
_PHRASE_STOP = frozenset("""
as while after before with and that which where when who whom whose of to for but or nor so yet if than
was were is are be been being had has have did does do could would should might must will shall can
passing fact silence
""".split())




# ---- R3/R4: negation / departure / reference-only location relations (per-mention) ------
# Deterministic relation handling. Only CURRENT_LOCATION_EVIDENCE may positively bind LOCATION_ID.
# R4: classification is PER MENTION — never a sentence-wide reference/negation flag that
# suppresses co-occurring current locations. Precedence per mention:
#   NEGATED > DEPARTED > REFERENCE_ONLY > CURRENT_LOCATION > AMBIGUOUS
LOCATION_RELATION_CURRENT = "CURRENT_LOCATION_EVIDENCE"
LOCATION_RELATION_NEGATED = "NEGATED_LOCATION"
LOCATION_RELATION_DEPARTED = "DEPARTED_LOCATION"
LOCATION_RELATION_REFERENCE = "REFERENCE_ONLY_LOCATION"
LOCATION_RELATION_AMBIGUOUS = "AMBIGUOUS_LOCATION"

LOCATION_RELATION_PRECEDENCE = {
    LOCATION_RELATION_NEGATED: 50,
    LOCATION_RELATION_DEPARTED: 40,
    LOCATION_RELATION_REFERENCE: 30,
    LOCATION_RELATION_CURRENT: 20,
    LOCATION_RELATION_AMBIGUOUS: 10,
}

# R5: semantic families. Classification uses cue+loc in a local clause/window,
# not sentence-wide keyword presence.
RELATION_FAMILY_CURRENT = "CURRENT"
RELATION_FAMILY_REFERENCE_ONLY = "REFERENCE_ONLY"
RELATION_FAMILY_NEGATED = "NEGATED"
RELATION_FAMILY_DEPARTED = "DEPARTED"
RELATION_FAMILY_AMBIGUOUS = "AMBIGUOUS"
RELATION_FAMILY_MEMORY = "MEMORY"
RELATION_FAMILY_COMMUNICATION = "COMMUNICATION"
RELATION_FAMILY_INFORMATION = "INFORMATION"
RELATION_FAMILY_IMAGINED = "IMAGINED"
RELATION_FAMILY_NEGATION_NONENTRY = "NEGATION_NONENTRY"
RELATION_FAMILY_NEGATION_PROXIMITY = "NEGATION_PROXIMITY"
RELATION_FAMILY_CURRENT_LOCATIVE = "CURRENT_LOCATIVE"

_LOC_CAP = r"[a-z0-9'\-]+(?:\s+[a-z0-9'\-]+){0,4}?"
# Stop loc capture at clause/discourse/verb so "Nexus Pod reached Mira" does not swallow the verb.
_LOC_TAIL = (
    r"(?=\s+(?:from|while|when|as\b|after|before|and\b|but\b|then\b|"
    r"he\b|she\b|they\b|that\b|reached\b|circulated\b|haunted\b|bothered\b|"
    r"was\b|were\b|is\b|are\b|only\b|without\b|except\b|again\b|clearly\b|"
    r"twice\b|still\b|over\b|by\b|first\b|yet\b|in\b|at\b|"
    r"in\s+passing|entirely\b|of\s+legend|used\s+to|that\s+night)|[;,\.]|$)"
)
_DET = r"(?:the\s+|a\s+|an\s+|his\s+|her\s+|their\s+|its\s+|my\s+|our\s+|your\s+|own\s+)*"
_LOC_BARE = rf"{_DET}(?P<loc>{_LOC_CAP})"
_LOC = rf"{_LOC_BARE}{_LOC_TAIL}"

# (relation_class, regex, trigger, cue_family)
# Blocking classes only (NEGATED / DEPARTED / REFERENCE).
_LOCATION_RELATION_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]", str, str], ...] = (
    # ---- DEPARTED ----
    (LOCATION_RELATION_DEPARTED, re.compile(
        rf"\b(?:left|leaving)\s+{_LOC_BARE}\s+behind\b", re.I), "left_behind", RELATION_FAMILY_DEPARTED),
    (LOCATION_RELATION_DEPARTED, re.compile(
        rf"\b(?:departed|escaped|fled|ran)\s+from\s+{_LOC}", re.I), "departed_from", RELATION_FAMILY_DEPARTED),
    (LOCATION_RELATION_DEPARTED, re.compile(
        rf"\bmoved\s+away\s+from\s+{_LOC}", re.I), "moved_away_from", RELATION_FAMILY_DEPARTED),
    # ---- NEGATED: proximity ----
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bnowhere\s+near\s+{_LOC}", re.I), "nowhere_near", RELATION_FAMILY_NEGATION_PROXIMITY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bnot\s+anywhere\s+near\s+{_LOC}", re.I), "not_anywhere_near", RELATION_FAMILY_NEGATION_PROXIMITY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bnot\s+near\s+{_LOC}", re.I), "not_near", RELATION_FAMILY_NEGATION_PROXIMITY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:a\s+)?long\s+way\s+from\s+{_LOC}", re.I), "long_way_from", RELATION_FAMILY_NEGATION_PROXIMITY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:well\s+)?(?:far\s+away|far|away)\s+from\s+{_LOC}", re.I), "far_or_away_from", RELATION_FAMILY_NEGATION_PROXIMITY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bstayed\s+(?:well\s+)?away\s+from\s+{_LOC}", re.I), "stayed_away_from", RELATION_FAMILY_NEGATION_PROXIMITY),
    # ---- NEGATED: non-entry / absence ----
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bnever\s+(?:entered|went\s+into|reached|arrived\s+at)\s+{_LOC}", re.I),
     "never_entered_reached", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:did\s+not|didn't)\s+(?:enter|go\s+into|reach|arrive\s+at)\s+{_LOC}", re.I),
     "did_not_enter_go_into", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:was\s+not|wasn't)\s+(?:in|inside|at|within)\s+{_LOC}", re.I),
     "was_not_inside", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:had\s+not|hadn't)\s+(?:reached|returned\s+to|entered)\s+{_LOC}", re.I),
     "had_not_reached_returned", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bnever\s+(?:reached|arrived\s+at)\s+{_LOC}", re.I), "never_reached", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\b(?:not|no\s+longer)\s+(?:in|at|inside|within|near)\s+{_LOC}", re.I),
     "not_in_at_inside_within_near", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bavoided\s+{_LOC}", re.I), "avoided_place", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\boutside\s+{_LOC_BARE}.{{0,40}}?\bbarred\s+from\b", re.I), "outside_barred", RELATION_FAMILY_NEGATION_NONENTRY),
    (LOCATION_RELATION_NEGATED, re.compile(
        rf"\bbarred\s+from\s+(?:entering\b|{_LOC})", re.I), "barred_from", RELATION_FAMILY_NEGATION_NONENTRY),
    # ---- REFERENCE_ONLY: MEMORY ----
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:remembered|recalled|could\s+still\s+remember)\s+(?:(?:the\s+)?(?:story|tale|legend|news|memory|vision|thought|dream|image|account|rumor)\s+(?:of\s+)?)?{_LOC}",
        re.I), "remembered_recalled", RELATION_FAMILY_MEMORY),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:thinking|thought|kept\s+thinking)\s+back\s+to\s+{_LOC}", re.I),
     "thinking_back_to", RELATION_FAMILY_MEMORY),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bthought\s+of\s+{_LOC}", re.I), "thought_of", RELATION_FAMILY_MEMORY),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bmemory\s+of\s+{_LOC}", re.I), "memory_of", RELATION_FAMILY_MEMORY),
    # ---- REFERENCE_ONLY: COMMUNICATION ----
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\btold\s+\w+(?:\s+\w+)?\s+about\s+{_LOC}", re.I), "told_about", RELATION_FAMILY_COMMUNICATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:spoke|talked)\s+(?:to\s+\w+\s+)?(?:about|of)\s+{_LOC}", re.I),
     "spoke_talked_about", RELATION_FAMILY_COMMUNICATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bmentioned\s+{_LOC}", re.I), "mentioned", RELATION_FAMILY_COMMUNICATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bdescribed\s+{_LOC}", re.I), "described", RELATION_FAMILY_COMMUNICATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bheard\s+(?:about|of)\s+{_LOC}", re.I), "heard_about", RELATION_FAMILY_COMMUNICATION),
    # ---- REFERENCE_ONLY: INFORMATION ----
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:read|learned|knew)\s+about\s+{_LOC}", re.I), "read_learned_knew_about", RELATION_FAMILY_INFORMATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bheard\s+news\s+(?:about|of|from)\s+{_LOC}", re.I), "heard_news_about", RELATION_FAMILY_INFORMATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:story|tale|legend|news|rumor|account|report)\s+(?:of|about)\s+{_LOC}", re.I),
     "story_of_about", RELATION_FAMILY_INFORMATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:vision|memory|dream|image|thought|story|tale|legend)\s+(?:of\s+|the\s+)?{_LOC_BARE}\s+had\s+shown\b",
        re.I), "vision_had_shown", RELATION_FAMILY_INFORMATION),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:called|named|titled|known\s+as)\s+[\"']?{_LOC}", re.I), "called_named", RELATION_FAMILY_INFORMATION),
    # ---- REFERENCE_ONLY: IMAGINED ----
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bdreamed\s+(?:of|about)\s+{_LOC}", re.I), "dreamed_of", RELATION_FAMILY_IMAGINED),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\b(?:imagined|pictured)\s+{_LOC}", re.I), "imagined_pictured", RELATION_FAMILY_IMAGINED),
    (LOCATION_RELATION_REFERENCE, re.compile(
        rf"\bvision\s+of\s+{_LOC}", re.I), "vision_of", RELATION_FAMILY_IMAGINED),
)

# Positive CURRENT locative cues — per-mention observability only; never blocks.
_CURRENT_LOCATION_PATTERNS: Tuple[Tuple["re.Pattern[str]", str, str], ...] = (
    (re.compile(rf"\b(?:entered|entering)\s+{_LOC}", re.I), "entered_place", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(rf"\b(?:went\s+into|returned\s+to|arrived\s+at)\s+{_LOC}", re.I),
     "went_returned_arrived", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(rf"\breached\s+{_LOC}", re.I), "reached_place", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(rf"\bworked\s+inside\s+{_LOC}", re.I), "worked_inside", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(
        rf"\b(?:inside|within|into|in|at)\s+{_LOC}", re.I), "locative_prep", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(
        rf"\b(?:waited|stood|sat|knelt|worked|sealed|entered|entering|waiting|standing|sitting)\s+"
        rf"(?:(?:the\s+)?(?:bellows|hatch|doors?)\s+)?(?:at|in|inside|within|near)\s+"
        rf"{_LOC}", re.I), "verb_locative", RELATION_FAMILY_CURRENT_LOCATIVE),
    (re.compile(rf"\b(?:near|beside|by)\s+{_LOC}", re.I), "near_beside", RELATION_FAMILY_CURRENT_LOCATIVE),
)

# Outside-but-not-inside: exterior proximity without interior access.
_OUTSIDE_RX = re.compile(
    rf"\boutside\s+(?:the\s+)?(?P<loc>{_LOC_CAP})", re.I
)

# Trailing discourse to strip from captured place phrases (R4 reference paraphrases).
_LOC_TRAILER_RX = re.compile(
    r"\s+(?:from\s+)?(?:childhood|youth|years?|age|memory|memories|legend|legends|"
    r"while|when|as|after|before|and|but|then|into|onto|under|over|"
    r"in\s+passing|that\s+night|he\s+used|used\s+to|entirely)\b.*$",
    re.I,
)

_CLAUSE_SPLIT_RX = re.compile(
    r"\s*(?:;+|,\s+and\s+instead\s+|\band\s+instead\s+|\s+while\s+|\s+but\s+)\s*",
    re.I,
)
_NEG_CURRENT_PREFIX_RX = re.compile(
    r"(?:never|did(?:\s+not|n't)|had(?:\s+not|n't)|was(?:\s+not|n't)|not\s+anywhere|nowhere)\s*$",
    re.I,
)


def _relation_clauses(text: str) -> List[Tuple[int, int, str]]:
    """Local clause windows. A cue in one clause must not classify another clause's place."""
    spans: List[Tuple[int, int, str]] = []
    last = 0
    for m in _CLAUSE_SPLIT_RX.finditer(text):
        if m.start() > last:
            chunk = text[last:m.start()]
            if chunk.strip():
                spans.append((last, m.start(), chunk))
        last = m.end()
    if last < len(text) and text[last:].strip():
        spans.append((last, len(text), text[last:]))
    if not spans:
        spans.append((0, len(text), text))
    return spans


def _clause_for_index(text: str, index: int) -> str:
    for start, end, chunk in _relation_clauses(text):
        if start <= index < end:
            return chunk.strip()
    return text.strip()


def _normalize_relation_loc(loc_raw: str) -> str:
    loc = re.sub(r"\s+", " ", (loc_raw or "").strip().lower())
    if not loc:
        return ""
    loc = _LOC_TRAILER_RX.sub("", loc).strip()
    parts = [w for w in loc.split() if w not in TEMPORAL_DISCOURSE_TOKENS and w not in _PHRASE_STOP]
    # Drop leading determiners left over
    while parts and parts[0] in _DETERMINERS:
        parts = parts[1:]
    return " ".join(parts).strip()


def _relation_beats(existing: str, new: str) -> bool:
    """Return True if new class should replace existing under R4 precedence."""
    return LOCATION_RELATION_PRECEDENCE.get(new, 0) > LOCATION_RELATION_PRECEDENCE.get(existing, 0)


def classify_location_relations(scene_text: str) -> Dict[str, Any]:
    """Per-mention relation classes. R6 compositional families; only CURRENT may bind."""
    from tools.location_relation_r6 import classify as _r6_classify
    return _r6_classify(scene_text)
    """Return per-mention relation classes and blocked location tokens for a scene.

    Only CURRENT_LOCATION_EVIDENCE may bind LOCATION_ID. Negated / departed /
    reference-only mentions are recorded per-mention and excluded from positive binding.
    Co-occurring CURRENT mentions remain bindable (no sentence-wide reference flag).
    """
    text = str(scene_text or "")
    blocked: Dict[str, str] = {}  # normalized phrase -> blocking class
    detections: List[Dict[str, Any]] = []
    mentions: List[Dict[str, Any]] = []
    negation_detected = False
    departure_detected = False
    reference_only = False
    current_detected = False

    def _emit(cls: str, loc: str, span: str, trigger: str, *, note: str = "",
              bind_allowed: Optional[bool] = None, cue_family: str = "",
              clause: str = "", loc_raw: str = "") -> None:
        nonlocal negation_detected, departure_detected, reference_only, current_detected
        if not loc and cls != LOCATION_RELATION_NEGATED and cls != LOCATION_RELATION_DEPARTED:
            return
        bind_ok = bool(cls == LOCATION_RELATION_CURRENT) if bind_allowed is None else bool(bind_allowed)
        rejection = ""
        if not bind_ok:
            rejection = {
                LOCATION_RELATION_NEGATED: "NEGATED_LOCATION",
                LOCATION_RELATION_DEPARTED: "DEPARTED_LOCATION",
                LOCATION_RELATION_REFERENCE: "REFERENCE_ONLY_LOCATION",
                LOCATION_RELATION_AMBIGUOUS: "AMBIGUOUS_LOCATION",
            }.get(cls, "RELATION_BLOCKED")
        class_family = {
            LOCATION_RELATION_CURRENT: RELATION_FAMILY_CURRENT,
            LOCATION_RELATION_NEGATED: RELATION_FAMILY_NEGATED,
            LOCATION_RELATION_DEPARTED: RELATION_FAMILY_DEPARTED,
            LOCATION_RELATION_REFERENCE: RELATION_FAMILY_REFERENCE_ONLY,
            LOCATION_RELATION_AMBIGUOUS: RELATION_FAMILY_AMBIGUOUS,
        }.get(cls, RELATION_FAMILY_AMBIGUOUS)
        rec = {
            "RAW": span[:160],
            "RAW_LOCATION_MENTION": (loc_raw or loc)[:160],
            "NORMALIZED": loc,
            "LOCATION_RELATION_CLASS": cls,
            "RELATION_CLASS": cls,
            "RELATION_FAMILY": class_family,
            "MATCHED_CUE": trigger,
            "MATCHED_CUE_FAMILY": cue_family or class_family,
            "CLAUSE_OR_WINDOW": (clause or span)[:240],
            "NEGATION_SCOPE": loc if cls == LOCATION_RELATION_NEGATED else "",
            "REFERENCE_SCOPE": loc if cls == LOCATION_RELATION_REFERENCE else "",
            "CURRENT_LOCATION_EVIDENCE": bool(cls == LOCATION_RELATION_CURRENT),
            "triggers": [trigger] if trigger else [],
            "CURRENT_EVIDENCE": bool(cls == LOCATION_RELATION_CURRENT),
            "BIND_ALLOWED": bind_ok,
            "REJECTION_REASON": rejection,
            "phrase": loc,
            "class": cls,
            "span": span[:120],
        }
        if note:
            rec["note"] = note
        detections.append({k: rec[k] for k in ("phrase", "class", "span") if k in rec} |
                          ({"note": note} if note else {}))
        mentions.append(rec)
        if cls == LOCATION_RELATION_NEGATED:
            negation_detected = True
        elif cls == LOCATION_RELATION_DEPARTED:
            departure_detected = True
        elif cls == LOCATION_RELATION_REFERENCE:
            reference_only = True
        elif cls == LOCATION_RELATION_CURRENT:
            current_detected = True
        if loc and cls in (
            LOCATION_RELATION_NEGATED, LOCATION_RELATION_DEPARTED, LOCATION_RELATION_REFERENCE,
            LOCATION_RELATION_AMBIGUOUS,
        ):
            prev = blocked.get(loc)
            if prev is None or _relation_beats(prev, cls):
                blocked[loc] = cls

    for cls, rx, trigger, cue_family in _LOCATION_RELATION_PATTERNS:
        for m in rx.finditer(text):
            try:
                loc_raw = m.group("loc")
            except IndexError:
                loc_raw = ""
            loc = _normalize_relation_loc(loc_raw or "")
            span = m.group(0)
            clause = _clause_for_index(text, m.start())
            if not loc:
                if cls in (LOCATION_RELATION_NEGATED, LOCATION_RELATION_DEPARTED):
                    _emit(cls, "", span, trigger, cue_family=cue_family, clause=clause)
                continue
            _emit(cls, loc, span, trigger, cue_family=cue_family, clause=clause, loc_raw=loc_raw or loc)

    # Outside X without an interior "inside/entered X" -> treat X as NEGATED for interior bind
    for m in _OUTSIDE_RX.finditer(text):
        loc = _normalize_relation_loc(m.group("loc") or "")
        if not loc:
            continue
        interior_rx = re.compile(rf"\b(?:inside|entered|entering|within)\s+(?:the\s+)?{re.escape(loc)}\b", re.I)
        if not interior_rx.search(text):
            prev = blocked.get(loc)
            if prev is None or _relation_beats(prev, LOCATION_RELATION_NEGATED) or prev == LOCATION_RELATION_NEGATED:
                _emit(LOCATION_RELATION_NEGATED, loc, m.group(0), "outside_without_interior",
                      note="OUTSIDE_WITHOUT_INTERIOR", cue_family=RELATION_FAMILY_NEGATION_NONENTRY,
                      clause=_clause_for_index(text, m.start()), loc_raw=m.group("loc") or loc)

    # CURRENT locative mentions (observability + proof that reference is not sentence-wide)
    for rx, trigger, cue_family in _CURRENT_LOCATION_PATTERNS:
        for m in rx.finditer(text):
            span = m.group(0)
            span_l = span.lower()
            if "nowhere near" in span_l or re.search(r"\bnot\s+near\b", span_l):
                continue
            start = m.start()
            prefix = text[max(0, start - 24):start].lower()
            if _NEG_CURRENT_PREFIX_RX.search(prefix.rstrip()) or prefix.rstrip().endswith("nowhere"):
                continue
            loc = _normalize_relation_loc(m.group("loc") or "")
            if not loc:
                continue
            blk = _phrase_blocked_by_relation(loc, blocked)
            if blk is not None:
                continue
            _emit(LOCATION_RELATION_CURRENT, loc, span, trigger, cue_family=cue_family,
                  clause=_clause_for_index(text, start), loc_raw=m.group("loc") or loc)

    # Scene-level primary: prefer CURRENT when any current mention exists alongside blocks
    # (per-mention authority). Else highest-precedence blocking class. Else CURRENT default.
    primary = LOCATION_RELATION_CURRENT
    if current_detected:
        primary = LOCATION_RELATION_CURRENT
    elif departure_detected:
        primary = LOCATION_RELATION_DEPARTED
    elif negation_detected:
        primary = LOCATION_RELATION_NEGATED
    elif reference_only:
        primary = LOCATION_RELATION_REFERENCE

    return {
        "LOCATION_RELATION_CLASS": primary,
        "LOCATION_NEGATION_DETECTED": negation_detected,
        "LOCATION_DEPARTURE_DETECTED": departure_detected,
        "LOCATION_REFERENCE_ONLY": reference_only,
        "LOCATION_RELATION_PRECEDENCE_DEFINED": True,
        "PER_MENTION_LOCATION_RELATION": True,
        "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE": True,
        "blocked_phrases": blocked,
        "detections": detections,
        "LOCATION_RELATION_MENTIONS": mentions,
    }


def _phrase_blocked_by_relation(phrase: str, blocked: Dict[str, str]) -> Optional[str]:
    """Return relation class if phrase (or a token of it) is blocked; else None."""
    p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    if not p:
        return None
    if p in blocked:
        return blocked[p]
    best_cls = None
    best_rank = -1
    for b, cls in blocked.items():
        if not b:
            continue
        hit = False
        # token containment either way (pod <-> his own pod; forge <-> the forge)
        if b in p or p in b:
            hit = True
        else:
            b_tokens = set(b.split())
            p_tokens = set(p.split())
            overlap = b_tokens & p_tokens
            if overlap and any(_singular(t) in PLACE_HEAD_NOUNS or len(t) >= 4 for t in overlap):
                hit = True
        if hit:
            rank = LOCATION_RELATION_PRECEDENCE.get(cls, 0)
            if rank > best_rank:
                best_rank = rank
                best_cls = cls
    return best_cls




# ---- R3 Phase 3: place-extractor false-positive rejection ----------------------------
_NOVEL_TITLE_PLACE_RX = re.compile(
    r"\b(?:hundredfold\s+path|heavenly\s+ascension(?:\s+system)?|eternal\s+nexus|soul\s*forge\s*era|soulforge\s*era)\b",
    re.I,
)
_METAPHOR_PLACE_RX = re.compile(
    r"\b(?:forge-heart|forgeheart|heart-forge)\b|(?:^|\s)the\s+way\s+a\s+\w+",
    re.I,
)
_NONLOCATIVE_FORGE_RX = re.compile(
    r"\b(?:maternal|paternal|spiritual|inner|upper)\s+forge\b|"
    r"\bforge\s+had\s+shown\b|"
    r"\bvision\s+(?:the\s+)?(?:upper\s+)?forge\b|"
    r"\bchapter\s+\d+\s*[:\-–—]?\s*.*\bforge\b",
    re.I,
)
_SIMILE_WAY_A_RX = re.compile(r"\b(?:the\s+)?way\s+a\s+(?P<head>\w+)\b", re.I)


def classify_place_phrase(phrase: str, *, scene_text: str = "") -> Dict[str, str]:
    """Label a candidate place phrase: LOCATIVE / NOVEL_TITLE / METAPHOR / NONLOCATIVE_NOUN / NARRATIVE_FRAGMENT."""
    p = (phrase or "").strip()
    low = p.lower()
    scene = str(scene_text or "")
    if not p:
        return {"PLACE_PHRASE_CLASS": "EMPTY", "PLACE_REJECTION_REASON": "EMPTY"}
    if _NOVEL_TITLE_PLACE_RX.search(low) or low in {
        "hundredfold path", "the hundredfold path", "heavenly ascension", "eternal nexus",
        "soul forge era", "soulforge era",
    }:
        return {"PLACE_PHRASE_CLASS": "NOVEL_TITLE", "PLACE_REJECTION_REASON": "NOVEL_TITLE_AS_PLACE"}
    if _METAPHOR_PLACE_RX.search(low) or _SIMILE_WAY_A_RX.fullmatch(low) or low.startswith("way a "):
        return {"PLACE_PHRASE_CLASS": "METAPHOR", "PLACE_REJECTION_REASON": "METAPHOR_AS_PLACE"}
    # narrative fragment: "way a field" / "way a wall"
    if re.match(r"^way\s+a\s+\w+$", low):
        return {"PLACE_PHRASE_CLASS": "NARRATIVE_FRAGMENT", "PLACE_REJECTION_REASON": "NARRATIVE_FRAGMENT"}
    # Non-locative forge / noun uses — check surrounding scene when available
    window = scene if scene else p
    if "forge" in low:
        # True locative: "a forge burned in a hall" / "in the forge" / "at the forge" / "into the forge"
        true_loc = re.search(
            r"\b(?:in|at|inside|into|within|through|from)\s+(?:the\s+|a\s+|an\s+)?(?:\w+\s+){0,2}forge\b|"
            r"\ba\s+forge\s+(?:burned|stood|waited|loomed|glowed|opened)\b|"
            r"\bforge\s+(?:doors?|gates?|entrance|interior|hall|floor|chamber)\b",
            window,
            re.I,
        )
        if _NONLOCATIVE_FORGE_RX.search(window) and not true_loc:
            return {"PLACE_PHRASE_CLASS": "NONLOCATIVE_NOUN", "PLACE_REJECTION_REASON": "NONLOCATIVE_NOUN_AS_PLACE"}
        if re.search(r"\b(?:maternal|paternal|spiritual|inner)\s+forge\b", low):
            return {"PLACE_PHRASE_CLASS": "NONLOCATIVE_NOUN", "PLACE_REJECTION_REASON": "NONLOCATIVE_NOUN_AS_PLACE"}
        if re.search(r"\bforge-heart\b", low):
            return {"PLACE_PHRASE_CLASS": "METAPHOR", "PLACE_REJECTION_REASON": "METAPHOR_AS_PLACE"}
    return {"PLACE_PHRASE_CLASS": "LOCATIVE", "PLACE_REJECTION_REASON": ""}



def _singular(w: str) -> str:
    if w in PLACE_HEAD_NOUNS:
        return w
    for suf in ("es", "s"):
        if w.endswith(suf) and w[: -len(suf)] in PLACE_HEAD_NOUNS:
            return w[: -len(suf)]
    return w


def _validate_place_phrase(words: List[str], *, scene_text: str = "") -> Tuple[bool, str]:
    if not words:
        return False, "EMPTY"
    phrase = " ".join(words)
    cls = classify_place_phrase(phrase, scene_text=scene_text)
    if cls["PLACE_PHRASE_CLASS"] != "LOCATIVE":
        return False, cls["PLACE_REJECTION_REASON"] or cls["PLACE_PHRASE_CLASS"]
    heads = [w for w in words if _singular(w) in PLACE_HEAD_NOUNS]
    if not heads:
        if any(w in TEMPORAL_DISCOURSE_TOKENS for w in words):
            return False, "TEMPORAL_OR_DISCOURSE"
        return False, "NO_PLACE_HEAD_NOUN"
    last = words[-1]
    if last in TEMPORAL_DISCOURSE_TOKENS and _singular(last) not in PLACE_HEAD_NOUNS:
        return False, "TEMPORAL_OR_DISCOURSE_HEAD"
    # Reject path/title heads when the full phrase is a known novel title fragment
    if _singular(last) == "path" and "hundredfold" in phrase.lower():
        return False, "NOVEL_TITLE_AS_PLACE"
    return True, ""


def extract_place_phrases(scene_text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Deterministic place-phrase extraction (no LLM).

    Grammar: PREP [DET] W{1,5} with a place head noun, stopping at conjunctions /
    prepositions / verbs-auxiliaries / punctuation; plus bare 'the <adj>{0,2} <place-head>'.
    Character names are stripped first. Returns (accepted, rejected[{phrase, reason}]).
    """
    clean, _ = strip_character_tokens(scene_text)
    accepted: List[str] = []
    rejected: List[Dict[str, str]] = []
    seen = set()
    det = "|".join(_DETERMINERS)
    prep = "|".join(sorted(_PREPOSITIONS, key=len, reverse=True))
    rx = re.compile(r"(?<![a-z0-9])(?:" + prep + r")\s+(?:(?:" + det + r")\s+)?([a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,5})")
    for seg in re.split(r"[.,;:!?()\[\]\"|—–…]+", clean):
        for m in rx.finditer(seg):
            words = []
            for w in m.group(1).split():
                w = w.strip("'-")
                if not w or w in _PHRASE_STOP or w in _PREPOSITIONS or w in _DETERMINERS:
                    break
                words.append(w)
            # trim trailing non-head words after the last place head (e.g. 'alley behind' -> 'alley')
            idx = max((i for i, w in enumerate(words) if _singular(w) in PLACE_HEAD_NOUNS), default=-1)
            cand_words = words[: idx + 1] if idx >= 0 else words
            phrase = " ".join(cand_words).strip()
            if not phrase or phrase in seen:
                continue
            seen.add(phrase)
            ok, why = _validate_place_phrase(cand_words, scene_text=scene_text)
            if ok:
                accepted.append(phrase)
            else:
                rejected.append({"phrase": phrase, "reason": why, **classify_place_phrase(phrase, scene_text=scene_text)})
        for m in re.finditer(r"(?<![a-z0-9])the\s+((?:[a-z][a-z'\-]*\s+){0,2}[a-z][a-z'\-]*)", seg):
            words = m.group(1).split()
            if not words or _singular(words[-1]) not in PLACE_HEAD_NOUNS:
                continue
            if any(w in _PHRASE_STOP or w in _PREPOSITIONS for w in words):
                words = words[-1:]
            phrase = " ".join(words)
            if phrase in seen or any(phrase in a or a in phrase for a in accepted):
                continue
            seen.add(phrase)
            ok, why = _validate_place_phrase(words, scene_text=scene_text)
            (accepted.append(phrase) if ok else rejected.append({"phrase": phrase, "reason": why, **classify_place_phrase(phrase, scene_text=scene_text)}))
    # R3: existential locatives like "a forge burned in a hall"
    for m in re.finditer(
        r"(?<![a-z0-9])(?:a|an|the)\s+([a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,2})\s+"
        r"(?:burned|stood|waited|loomed|glowed|opened|rose|lay|sat)\b",
        clean,
        re.I,
    ):
        words = [w for w in m.group(1).lower().split() if w]
        # require a place head noun in the NP
        if not any(_singular(w) in PLACE_HEAD_NOUNS for w in words):
            continue
        phrase = " ".join(words)
        if phrase in seen:
            continue
        seen.add(phrase)
        ok, why = _validate_place_phrase(words, scene_text=scene_text)
        if ok:
            accepted.append(phrase)
        else:
            rejected.append({"phrase": phrase, "reason": why, **classify_place_phrase(phrase, scene_text=scene_text)})
    return accepted, rejected


def _place_from_scene(scene_text: str) -> str:
    """First validated scene-context place phrase, else the neutral sentinel."""
    accepted, _ = extract_place_phrases(scene_text)
    return accepted[0] if accepted else "the immediate scene setting"


# ---- R2 Parts B/C: decontaminated, thresholded Studio Bible location matcher ----------
_GENERIC_DESCRIPTORS = frozenset({
    "flat", "stone", "iron", "elevated", "intact", "n/a", "none", "urban", "small", "low", "medium",
    "high", "dark", "night", "interior", "exterior", "ancient", "ordered", "hidden", "sparse",
})


def _split_field(value: Any) -> List[str]:
    v = str(value or "").replace("_", " ")
    v = re.sub(r"\([^)]*\)", " ", v)
    return [p.strip() for p in re.split(r"[,+/;]", v) if p.strip()]


def location_evidence_terms(loc: Dict[str, Any]) -> Dict[str, List[str]]:
    """Evidence vocabulary for one Bible location, character names removed; history excluded."""
    nov = str(loc.get("novel") or "").lower()
    lid = str(loc.get("id") or "")
    names: List[str] = []
    for seg in _split_field(loc.get("name")):
        clean, _rej = strip_character_tokens(seg)
        if clean and (len(clean.split()) >= 2 or len(clean) >= 5):
            names.append(clean)
    aliases = [c for c, i in PLACE_ALIASES.get(nov, {}).items() if i == lid]
    multi: List[str] = []
    single: List[str] = []
    for fld in ("architecture", "terrain"):
        for seg in _split_field(loc.get(fld)):
            clean, _rej = strip_character_tokens(seg)
            if not clean or clean in _GENERIC_DESCRIPTORS:
                continue
            if len(clean.split()) < 2 and len(clean) < 3:
                continue  # R2 round 3: residue like "a" after name stripping is never place evidence
            (multi if len(clean.split()) >= 2 else single).append(clean)
    env: List[str] = [c for c, i in ENVIRONMENT_CUES.get(nov, {}).items() if i == lid]
    for fld in ("lighting", "weather", "ambient_particles", "magic_effects"):
        for seg in _split_field(loc.get(fld)):
            clean, _rej = strip_character_tokens(seg)
            if clean and clean not in _GENERIC_DESCRIPTORS and (len(clean.split()) >= 2 or len(clean) > 3):
                env.append(clean)
                env.extend(w for w in clean.split() if len(w) > 3 and w not in _GENERIC_DESCRIPTORS)
    dd = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
    return {"canonical_name": dd(names), "place_alias": dd(aliases), "place_descriptor_multi": dd(multi),
            "place_descriptor_single": dd(single), "environment_descriptor": dd(env)}



def _scrub_nonlocative_place_nouns(clean: str, scene_text: str) -> str:
    """Remove non-locative noun uses from matcher text (R3 Phase 3/7)."""
    out = clean
    for rx in (
        re.compile(r"\b(?:maternal|paternal|spiritual|inner)\s+forge\b", re.I),
        re.compile(r"\bforge-heart\b|\bforgeheart\b", re.I),
        re.compile(r"\bchapter\s+\d+\s*[:\-–—]?[^.]*\bforge\b", re.I),
    ):
        out = rx.sub(" ", out)
    if classify_place_phrase("forge", scene_text=scene_text)["PLACE_PHRASE_CLASS"] == "NONLOCATIVE_NOUN":
        out = re.sub(r"\b(?:upper\s+)?forge\b", " ", out, flags=re.I)
    return out


def match_studio_bible_location_detailed(
    scene_text: str,
    locations: Sequence[Dict[str, Any]],
    novel: str,
    character_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Decontaminated novel-scoped location match with evidence threshold (R2 Parts B/C + R3 Phase 2).

    R3: negated / departed / reference-only location mentions cannot positively bind.
    Evidence tokens that appear only inside blocked relation phrases are dropped.
    """
    nov = str(novel).lower()
    clean, rejected_chars = strip_character_tokens(scene_text, character_names)
    # R3: scrub non-locative noun uses so aliases like 'forge' cannot bind on
    # 'maternal forge' / 'forge-heart' / title uses when place extractor rejected them.
    clean = _scrub_nonlocative_place_nouns(clean, scene_text)
    relations = classify_location_relations(scene_text)
    blocked = dict(relations.get("blocked_phrases") or {})
    out: Dict[str, Any] = {
        "matched": None, "candidates": [], "rejected_character_tokens": rejected_chars,
        "score": 0, "decision": "UNRESOLVED_NO_BIBLE_LOCATIONS", "evidence": {},
        "LOCATION_RELATION_CLASS": relations.get("LOCATION_RELATION_CLASS", LOCATION_RELATION_CURRENT),
        "LOCATION_NEGATION_DETECTED": relations.get("LOCATION_NEGATION_DETECTED", False),
        "LOCATION_DEPARTURE_DETECTED": relations.get("LOCATION_DEPARTURE_DETECTED", False),
        "LOCATION_REFERENCE_ONLY": relations.get("LOCATION_REFERENCE_ONLY", False),
        "LOCATION_RELATION_MENTIONS": list(relations.get("LOCATION_RELATION_MENTIONS") or []),
        "LOCATION_RELATION_PRECEDENCE_DEFINED": bool(relations.get("LOCATION_RELATION_PRECEDENCE_DEFINED", True)),
        "PER_MENTION_LOCATION_RELATION": bool(relations.get("PER_MENTION_LOCATION_RELATION", True)),
        "relation_detections": list(relations.get("detections") or []),
    }
    # R21: entries marked legacy_prose_match: false are structured-authority-only; never positive prose-match
    # candidates (missing field == true, existing behavior preserved).
    by_id = [loc for loc in locations if str(loc.get("novel") or "").lower() == nov
             and loc.get("legacy_prose_match", True) is not False]
    if not by_id:
        return out
    best = None
    best_score = 0
    any_weak = False

    def _term_usable(term: str) -> bool:
        cls = _phrase_blocked_by_relation(term, blocked)
        return cls is None

    for loc in by_id:
        terms = location_evidence_terms(loc)
        hits = {k: [t for t in v if _has_phrase(clean, t) and _term_usable(t)] for k, v in terms.items()}
        # Also: if the location's canonical name / id is itself blocked, never bind
        loc_id = str(loc.get("id") or "")
        loc_name = str(loc.get("name") or "")
        blocked_cls = (
            _phrase_blocked_by_relation(loc_name, blocked)
            or _phrase_blocked_by_relation(loc_id.replace("_", " "), blocked)
            or _phrase_blocked_by_relation(loc_id.split("_")[-1] if "_" in loc_id else loc_id, blocked)
        )
        strong = len(hits["canonical_name"]) + len(hits["place_alias"])
        multi = len(hits["place_descriptor_multi"])
        single = len(set(hits["place_descriptor_single"]))
        env = len(set(hits["environment_descriptor"]))
        bindable = (blocked_cls is None) and (strong >= 1 or multi >= 1 or single >= 2)
        # R4: canonical_name outranks place_alias-only (character-home alias conservatism)
        score = (len(hits["canonical_name"]) * 15 + len(hits["place_alias"]) * 8
                 + multi * 6 + single * 2 + env)
        if blocked_cls is not None:
            # Explicitly non-bindable due to relation class
            bindable = False
            score = 0
        if score and not bindable and blocked_cls is None:
            any_weak = True
        out["candidates"].append({
            "location_id": loc_id, "score": score, "bindable": bindable,
            "evidence": {k: v for k, v in hits.items() if v},
            "relation_block": blocked_cls or "",
        })
        if bindable and score > best_score:
            best, best_score = loc, score
    out["candidates"].sort(key=lambda c: -c["score"])
    if best is not None:
        out["matched"] = best
        out["score"] = best_score
        out["decision"] = "BOUND_POSITIVE_PLACE_EVIDENCE"
        out["evidence"] = next(c["evidence"] for c in out["candidates"] if c["location_id"] == best.get("id"))
    else:
        # If the only hits were relation-blocked, say so
        if any(c.get("relation_block") for c in out["candidates"]):
            out["decision"] = "UNRESOLVED_RELATION_BLOCKED"
        else:
            out["decision"] = "UNRESOLVED_WEAK_EVIDENCE_ONLY" if any_weak else "UNRESOLVED_NO_PLACE_EVIDENCE"
        out["score"] = max([c["score"] for c in out["candidates"]] or [0])
    return out


def match_studio_bible_location(
    scene_text: str,
    locations: Sequence[Dict[str, Any]],
    novel: str,
) -> Optional[Dict[str, Any]]:
    """Novel-scoped Studio Bible location match (R2: decontaminated + evidence threshold).

    Character names are never evidence; environment descriptors alone never bind.
    Never returns a location from another novel. Returns None -> UNRESOLVED.
    """
    return match_studio_bible_location_detailed(scene_text, locations, novel)["matched"]


def _extract_scene_action(scene_text: str) -> str:
    """Pull a short action clause from scene text (TEXT_CANON_SCENE). No invention."""
    text = str(scene_text or "").strip()
    if not text:
        return "present in the scene"
    cleaned = re.sub(r"\s+", " ", text)
    if len(cleaned) > 140:
        cleaned = cleaned[:137].rsplit(" ", 1)[0] + "…"
    return cleaned


_HP_CONTEXT_RX = re.compile(r"(?<![a-z0-9])(?:sect|jade altar|formation|qi)(?![a-z0-9])")


def resolve_scene_environment(
    novel: str,
    scene_text: str,
    *,
    locations: Optional[Sequence[Dict[str, Any]]] = None,
    location: Optional[Dict[str, Any]] = None,
    still_index: int = 0,
    still_role: Optional[str] = None,
    composition_goal: Optional[str] = None,
    shots_text: Optional[Sequence[str]] = None,
) -> SceneEnvironmentSpec:
    """Build SceneEnvironmentSpec with documented authority precedence (Part A).

    R2: novel id normalized through tools.novel_id; Bible location only with positive
    place evidence (character names never count); otherwise UNRESOLVED + neutral place.
    """
    try:
        from tools.novel_id import normalize_novel_id

        nov = normalize_novel_id(novel) or str(novel).lower()
    except Exception:
        nov = str(novel).lower()
    role = still_role or STILL_ROLES[min(max(still_index, 0), 2)]
    goal = (composition_goal or "").strip()
    if not goal and shots_text and len(shots_text) > still_index:
        goal = str(shots_text[still_index]).strip()
    if not goal:
        goal = _extract_scene_action(scene_text)

    detail: Dict[str, Any] = {}
    if locations is not None:
        detail = match_studio_bible_location_detailed(scene_text, locations, nov)
    matched = location
    if matched is not None and str(matched.get("novel") or "").lower() not in ("", nov):
        matched = None  # never accept a foreign-novel location object
    if matched is None and detail:
        matched = detail.get("matched")
    if not detail:
        detail = {"candidates": [], "rejected_character_tokens": strip_character_tokens(scene_text)[1],
                  "score": 0, "decision": "CALLER_SUPPLIED" if matched else "UNRESOLVED_NO_LOCATIONS_SUPPLIED",
                  "evidence": {}}

    scene_action = _extract_scene_action(scene_text)
    clean_scene, _rej = strip_character_tokens(scene_text)
    scene_lm = scan_landmarks(clean_scene, HP_HARD_LANDMARKS)
    place_ok, place_rej = extract_place_phrases(scene_text)

    if matched:
        authority = "STUDIO_BIBLE_LOCATION"
        name = str(matched.get("name") or "")
        terms = location_evidence_terms(matched)
        if any(_has_phrase(clean_scene, t) for t in terms["canonical_name"]):
            authority = "TEXT_CANON_SCENE"
        loc_id = str(matched.get("id") or UNRESOLVED)
        place = name or loc_id
        architecture = str(matched.get("architecture") or "").replace("_", " ")
        lighting = str(matched.get("lighting") or "").replace("_", " ")
        damage = str(matched.get("damage_state") or "").replace("_", " ")
        weather = str(matched.get("weather") or "").replace("_", " ")
        particles = str(matched.get("ambient_particles") or "").replace("_", " ")
        magic = str(matched.get("magic_effects") or "").replace("_", " ")
        unknown = False
    else:
        if place_ok:
            authority = "SCENE_CONTEXT"
            place = place_ok[0]
        else:
            authority = "MODEL_PRIOR"
            place = f"a neutral {nov.upper()} setting"
        loc_id = UNRESOLVED
        architecture = lighting = damage = weather = particles = magic = ""
        unknown = True
        name = UNRESOLVED

    # R3 Phase 4: HP landmarks require scene evidence for EACH landmark/template.
    # Matching an HP location or generic "sect" context is not enough to inject
    # altar / broken staircase / gateway formations. Outside-gate scenes may keep
    # exterior gate context only.
    relations_obs = classify_location_relations(scene_text)
    supported_hp_landmarks = list(scene_lm)  # only landmarks literally present in scene
    # Soft landmarks that appear in scene text (not injected)
    for soft in ("broken staircase", "broken stair", "jade altar", "gateway", "formation",
                 "sect gate", "outside the sect", "ruined sect hall", "sect hall"):
        if _has_phrase(clean_scene, soft) and soft not in supported_hp_landmarks:
            # respect negation/departure
            if _phrase_blocked_by_relation(soft, relations_obs.get("blocked_phrases") or {}) is None:
                supported_hp_landmarks.append(soft)
    interior_landmarks = {"jade altar", "broken staircase", "broken stair", "dormant formation",
                          "ruined sect hall", "sect hall", "gateway formations"}
    outside_only = bool(re.search(r"outside.{0,40}(?:sect\s+)?gate", clean_scene)) and not bool(
        re.search(r"(?:inside|entered|entering|within).{0,40}sect", clean_scene)
    )
    if outside_only:
        supported_hp_landmarks = [lm for lm in supported_hp_landmarks if lm not in interior_landmarks
                                  and "altar" not in lm and "stair" not in lm and "formation" not in lm]
        # exterior gate may remain
        if _has_phrase(clean_scene, "gate") or _has_phrase(clean_scene, "sect gate"):
            if "sect gate" not in supported_hp_landmarks:
                supported_hp_landmarks.append("sect gate")
    hp_ok = nov == "hp" and bool(supported_hp_landmarks)

    env_state = _build_environment_state(
        novel=nov,
        location=matched,
        scene_text=scene_text,
        hp_landmarks_allowed=hp_ok,
        damage=damage,
        weather=weather,
        particles=particles,
    )

    if architecture:
        place_phrase = f"{place} ({architecture})" if place else architecture
    else:
        place_phrase = place

    spec = SceneEnvironmentSpec(
        novel=nov,
        location_id=loc_id,
        location_name=name if matched else UNRESOLVED,
        authority=authority,
        place_phrase=place_phrase,
        architecture=architecture,
        lighting=lighting,
        environment_state=env_state,
        damage_state=damage,
        weather=weather,
        ambient_particles=particles,
        magic_effects=magic,
        scene_action=scene_action,
        still_index=int(still_index),
        still_role=role,
        composition_goal=goal,
        hp_landmarks_allowed=hp_ok,
        unknown_location=unknown,
        observability={
            "authority": authority,
            "authority_precedence": list(AUTHORITY_PRECEDENCE),
            "location_id": loc_id,
            "location_name": name if matched else UNRESOLVED,
            "unknown_location": unknown,
            "unresolved_location_policy": UNRESOLVED_LOCATION_POLICY,
            "hp_landmarks_allowed": hp_ok,
            "still_index": int(still_index),
            "still_role": role,
            "composition_goal": goal[:200],
            "scene_action": scene_action[:200],
            "place_phrase": place_phrase,
            "LOCATION_MATCH_CANDIDATES": [
                {"location_id": c["location_id"], "score": c["score"], "bindable": c["bindable"]}
                for c in detail.get("candidates", [])
            ],
            "LOCATION_MATCH_EVIDENCE": detail.get("evidence", {}) if matched else {},
            "LOCATION_MATCH_REJECTED_CHARACTER_TOKENS": list(detail.get("rejected_character_tokens", [])),
            "LOCATION_MATCH_SCORE": detail.get("score", 0),
            "LOCATION_MATCH_DECISION": detail.get("decision", ""),
            "PLACE_TOKENS_EXTRACTED": list(place_ok),
            "PLACE_TOKENS_REJECTED": list(place_rej),
            "LOCATION_RELATION_CLASS": (detail.get("LOCATION_RELATION_CLASS")
                                       or relations_obs.get("LOCATION_RELATION_CLASS")
                                       or LOCATION_RELATION_CURRENT),
            "LOCATION_NEGATION_DETECTED": bool(detail.get("LOCATION_NEGATION_DETECTED")
                                              or relations_obs.get("LOCATION_NEGATION_DETECTED")),
            "LOCATION_DEPARTURE_DETECTED": bool(detail.get("LOCATION_DEPARTURE_DETECTED")
                                               or relations_obs.get("LOCATION_DEPARTURE_DETECTED")),
            "LOCATION_REFERENCE_ONLY": bool(detail.get("LOCATION_REFERENCE_ONLY")
                                           or relations_obs.get("LOCATION_REFERENCE_ONLY")),
            "LOCATION_RELATION_MENTIONS": list(
                detail.get("LOCATION_RELATION_MENTIONS")
                or relations_obs.get("LOCATION_RELATION_MENTIONS")
                or []
            ),
            "LOCATION_RELATION_PRECEDENCE_DEFINED": bool(
                detail.get("LOCATION_RELATION_PRECEDENCE_DEFINED",
                           relations_obs.get("LOCATION_RELATION_PRECEDENCE_DEFINED", True))
            ),
            "PER_MENTION_LOCATION_RELATION": bool(
                detail.get("PER_MENTION_LOCATION_RELATION",
                           relations_obs.get("PER_MENTION_LOCATION_RELATION", True))
            ),
            "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE": bool(
                relations_obs.get("PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE", True)
            ),
            "SUPPORTED_HP_LANDMARKS": list(supported_hp_landmarks),
            "HP_TEMPLATE_REQUIRES_SCENE_EVIDENCE": True,
            "domain": "scene_environment",
            "excluded_domains": ["identity", "wardrobe", "held_prop", "scene_critical_effects"],
        },
    )
    return spec


def _build_environment_state(
    *,
    novel: str,
    location: Optional[Dict[str, Any]],
    scene_text: str,
    hp_landmarks_allowed: bool,
    damage: str,
    weather: str,
    particles: str,
) -> str:
    state_bits: List[str] = []
    skip_vals = {"intact", "n/a", "none", ""}

    def _skip(v: str) -> bool:
        vl = v.lower()
        return vl in skip_vals or "n/a" in vl or "none" in vl

    contradictory = {"ordered", "pristine", "intact", "maintained", "well kept", "polished"}
    if damage and not _skip(damage):
        toks = [t for t in damage.split(",") if t.strip().lower() not in contradictory]
        clean = ", ".join(dict.fromkeys(t.strip() for t in toks if t.strip()))
        if clean:
            state_bits.append(clean)
    if weather and not _skip(weather):
        state_bits.append(weather)
    if particles and not _skip(particles):
        state_bits.append(particles)

    ruin_signals = ("ruin", "ruined", "collaps", "broken", "abandon", "wreck", "decay")
    implies_ruin = any(s in _norm(scene_text) for s in ruin_signals) or (
        location is not None
        and any(s in _norm(str(location.get("damage_state", ""))) for s in ("ruin", "ruined", "collaps", "broken"))
    )
    already = " ".join(state_bits).lower()
    if implies_ruin and not any(s in already for s in ("ruin", "collaps", "broken", "abandon")):
        if hp_landmarks_allowed:
            state_bits.append(
                "abandoned for centuries, partially collapsed, cracked stone stairs, "
                "broken jade railings, fallen roof tiles, faded and torn banners, "
                "dust and mist inside the hall"
            )
        else:
            state_bits.append(
                "abandoned, partially collapsed, cracked stone, fallen debris, dust in the air"
            )
    return ", ".join(dict.fromkeys(state_bits)) if state_bits else ""


def _hp_landmark_context(text: str) -> bool:
    low = _norm(text)
    return bool(re.search(r"(?<![a-z0-9])(?:sect|jade|altar|ruined)(?![a-z0-9])", low))


def build_still_cameras_poses(
    spec: SceneEnvironmentSpec,
    subject: str,
    *,
    identity_on: bool = False,
    has_jian: bool = False,
) -> Tuple[List[str], List[str], List[str]]:
    """Novel-scoped cameras/poses/objectives from SceneEnvironmentSpec (Parts C–E, H).

    No hardcoded HP landmarks unless spec.hp_landmarks_allowed.
    Composition derives from scene action + place + still role.
    """
    subj = subject or "the protagonist"
    place = spec.place_phrase or "the immediate scene setting"
    if not spec.hp_landmarks_allowed:
        for lm in HP_HARD_LANDMARKS:
            place = re.sub(re.escape(lm), "the setting", place, flags=re.I)

    action = spec.composition_goal or spec.scene_action or "present in the scene"
    action_clause = _clause_for_role(action, "establishing", place)
    motion_clause = _clause_for_role(action, "travel", place)
    climax_clause = _clause_for_role(action, "climax", place)
    place_ahead = place

    cameras = [
        _CAMERA_TEMPLATES[0].format(
            subject=subj, action_clause=action_clause, place=place
        ),
        _CAMERA_TEMPLATES[1].format(
            subject=subj, motion_clause=motion_clause, place_ahead=place_ahead
        ),
        _CAMERA_TEMPLATES[2].format(
            subject=subj, climax_clause=climax_clause
        ),
    ]

    poses = list(_POSE_TEMPLATES)
    low = _norm(action)
    if "kneel" in low or "altar" in low:
        poses[2] = (
            "kneeling on one knee at the focal point, one hand pressed to the surface, "
            "attention locked on the awakening moment"
        )
    if "climb" in low or "stair" in low:
        poses[1] = "midway along the ascent, one foot planted higher, body leaning forward"
    if "enter" in low:
        poses[0] = "standing at the entrance, head tilted upward, looking into the space ahead"
    if identity_on:
        poses[1] = (
            "midway through the advance, one foot planted forward, body leaning forward"
            + (", right hand hovering over the sword hilt" if has_jian else "")
        )

    if spec.hp_landmarks_allowed and spec.novel == "hp":
        supported = list((spec.observability or {}).get("SUPPORTED_HP_LANDMARKS") or [])
        # R3 Phase 4: only apply landmark/template content when THAT landmark is supported.
        has_hall = any("sect hall" in s or "ruined sect" in s for s in supported)
        has_stair = any("stair" in s for s in supported)
        has_altar = any("altar" in s for s in supported)
        has_formation = any("formation" in s for s in supported)
        has_gate = any("gate" in s for s in supported)
        if has_hall or has_stair or has_altar or has_formation:
            beat = (spec.composition_goal or spec.scene_action or "").strip()
            beat_short = beat[:110] if beat else "the sect moment"
            # Build from scene beat like other novels; inject landmark text only when supported.
            bg0 = "the ruined sect hall and gateway" if has_hall else (place if not has_gate else "the sect gate exterior")
            ahead1 = "the jade altar rising ahead" if has_altar else f"{place} ahead"
            climb1 = "climbing the broken stair toward the jade altar" if (has_stair and has_altar) else (
                "climbing the broken stair" if has_stair else f"advancing through {place}"
            )
            climax_env = (
                "kneeling on one knee before the altar with the dormant formation glowing on the floor behind"
                if (has_altar and has_formation) else (
                    "kneeling on one knee before the altar" if has_altar else
                    f"at the decisive beat within {place}"
                )
            )
            cameras = [
                (
                    f"full-body medium shot of {subj} {'entering the ruined sect hall' if has_hall else f'at {place}'} "
                    f"for beat [{beat_short}]; "
                    f"{subj} fills approximately 20 to 25 percent of the frame height and is "
                    f"immediately recognizable even at thumbnail size, while {bg0} fill the background"
                ),
                (
                    f"over-the-shoulder tracking shot from behind {subj} {climb1} "
                    f"for beat [{beat_short}]; "
                    f"{subj} fills approximately 20 to 25 percent of the frame height and is clearly "
                    f"visible and prominent, with {ahead1}"
                ),
                (
                    f"three-quarter side view, {subj} clearly the subject {climax_env} "
                    f"for beat [{beat_short}]; {subj} fills approximately 20 to 25 percent of the frame height"
                ),
            ]
            # Force _hp_landmark_context path for poses only when interior evidence exists
            low = low + (" sect altar stair" if (has_altar or has_stair or has_hall) else "")
        if False and _hp_landmark_context(low):
            # retained for diff clarity — disabled; replaced by per-landmark gating above
            beat = (spec.composition_goal or spec.scene_action or "").strip()
            beat_short = beat[:110] if beat else "the sect moment"
            cameras = [
                (
                    f"full-body medium shot of {subj} entering the ruined sect hall for beat [{beat_short}]; "
                    f"{subj} fills approximately 20 to 25 percent of the frame height and is "
                    f"immediately recognizable even at thumbnail size, while the towering "
                    f"ruined sect hall and gateway fill the background"
                ),
                (
                    f"over-the-shoulder tracking shot from behind {subj} climbing the broken stair "
                    f"toward the jade altar for beat [{beat_short}]; "
                    f"{subj} fills approximately 20 to 25 percent of the frame height and is clearly "
                    f"visible and prominent, with the jade altar rising ahead"
                ),
                (
                    f"three-quarter side view from altar height, {subj} clearly the subject kneeling "
                    f"on one knee before the altar with the dormant formation glowing on the floor "
                    f"behind for beat [{beat_short}]; {subj} fills approximately 20 to 25 percent of the frame height"
                ),
            ]
            if has_hall or has_stair or has_altar or has_formation:
                gate_look = (
                    "looking at the ancient formations above the gateway" if (has_formation and has_gate)
                    else ("looking toward the sect gate" if has_gate else f"looking into {place}")
                )
                mid = (
                    (
                        "midway up the broken staircase, one foot planted on a higher step, body leaning forward"
                        + (", right hand hovering over the sword hilt" if has_jian else "")
                    ) if has_stair else (
                        "midway through the advance, one foot planted forward, body leaning forward"
                        + (", right hand hovering over the sword hilt" if has_jian else "")
                    )
                )
                end = (
                    (
                        "kneeling on one knee before the altar, left hand pressed to the cold stone, "
                        "silver qi visibly flowing through the dormant formation lines on the floor"
                    ) if (has_altar and has_formation) else (
                        "kneeling on one knee before the altar, left hand pressed to the cold stone"
                        if has_altar else
                        f"holding at the turning moment within {place}"
                    )
                )
                poses = [
                    f"standing at the entrance, head tilted upward, {gate_look}",
                    mid if identity_on or has_stair else (
                        mid + ", robe trailing behind him, right hand hovering over the sword hilt"
                        if has_stair else mid
                    ),
                    end,
                ]

    # R2 Part E/F: action first so the scene beat survives the 75-token CLIP window of the VD prompt.
    objectives = [
        f"{action} (establishing {subj} at {place})",
        f"{action} (advancing through {place})",
        f"{action} (the turning moment within {place})",
    ]
    return cameras, poses, objectives


def _clause_for_role(action: str, role: str, place: str) -> str:
    a = str(action or "").strip()
    if not a:
        a = f"present at {place}"
    if role == "establishing":
        return f"arriving into frame at {place} — {a}"
    if role == "travel":
        return f"moving deeper through {place} — {a}"
    return f"at the decisive beat within {place} — {a}"


# Identity-governed names are scrubbed case-insensitively; other recurring names only as proper
# nouns (capitalised) so ordinary words such as 'gray sky' are never rewritten.
_GOVERNED_SCRUB_CI = ("Kael Veyra", "Kael", "Veyra", "Liang", "Jarek", "Kai")
_RECURRING_SCRUB_CS = ("Gray", "Elyen", "Marta")


def _scrub_governed_names(text: str) -> str:
    """Remove known character display names from scene fragments embedded in prompts.

    R2: word-boundary matching (no 'Kaiser' -> 'the protagonistser'); governed names
    case-insensitive -> 'the protagonist'; other recurring names (proper noun only) -> 'a companion'.
    """
    out = str(text or "")
    for name in sorted(_GOVERNED_SCRUB_CI, key=len, reverse=True):
        out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", "the protagonist", out, flags=re.I)
    for name in _RECURRING_SCRUB_CS:
        out = re.sub(r"(?<![A-Za-z0-9])(?:" + re.escape(name) + "|" + re.escape(name.upper()) + r")(?![A-Za-z0-9])",
                     "a companion", out)
    out = re.sub(r"\bthe protagonist(?:\s+the protagonist)+\b", "the protagonist", out)
    return out


def still_differentiation_fragment(
    novel: str,
    beat: str,
    *,
    still_index: int = 0,
    still_role: Optional[str] = None,
    composition_goal: Optional[str] = None,
    location_name: Optional[str] = None,
) -> str:
    """AIVSB still differentiation metadata tag (Parts F–G).

    R2: this trailing tag is observability metadata only; effective differentiation is
    carried by aivsb_effective_scene_lead() inside the first 75 CLIP tokens.
    """
    nov = str(novel).lower()
    role = still_role or STILL_ROLES[min(max(int(still_index), 0), 2)]
    goal = (composition_goal or beat or "").strip()
    beat_text = str(beat or "").strip()
    beat_frag = _scrub_governed_names(re.sub(r"\s+", " ", beat_text)[:160])
    goal_frag = _scrub_governed_names(re.sub(r"\s+", " ", goal)[:160])
    place = (location_name or "").strip()
    if not place or place in NO_LOCATION_IDS:
        place = _place_from_scene(beat_text)
    place = _scrub_governed_names(place)
    parts = [
        f"STILL_INDEX={int(still_index)}",
        f"STILL_ROLE={role}",
        f"BEAT={beat_frag}" if beat_frag else "BEAT=",
        f"COMPOSITION_GOAL={goal_frag}" if goal_frag else "COMPOSITION_GOAL=",
        f"LOCATION={place}" if place else f"LOCATION={UNRESOLVED}",
        f"NOVEL={nov}",
    ]
    return "scene_environment[" + " | ".join(parts) + "]"


# ---- R2 Parts E/F: effective-prefix scene lead ---------------------------------------
def role_for_index(still_index: int, still_role: Optional[str] = None) -> str:
    return still_role or STILL_ROLES[min(max(int(still_index), 0), 2)]


def role_camera(still_role: str) -> Dict[str, str]:
    return dict(ROLE_CAMERAS.get(still_role, ROLE_CAMERAS["establishing"]))


def _short_words(text: str, n: int) -> str:
    words = re.sub(r"\s+", " ", str(text or "")).strip().split(" ")
    out = " ".join(words[:n]).strip(" ,;:.")
    return out


def lead_place(spec: SceneEnvironmentSpec) -> str:
    if spec.location_id not in NO_LOCATION_IDS and spec.location_name not in NO_LOCATION_IDS:
        return re.sub(r"\s*\([^)]*\)", "", spec.location_name).strip()
    if spec.authority == "SCENE_CONTEXT" and spec.place_phrase:
        return spec.place_phrase
    return "an unspecified neutral setting"


def aivsb_effective_scene_lead(spec: SceneEnvironmentSpec, beat: str, *, still_index: int, still_role: str,
                               beat_words: int = 22) -> str:
    """Scene lead placed right after the composer camera slot (inside the 75-token window).

    Carries STILL_ROLE, SCENE_BEAT / COMPOSITION_GOAL (action, governed names scrubbed),
    PRIMARY_SUBJECT and LOCATION. Deterministic; no synonym/seed tricks.
    """
    beat_txt = _scrub_governed_names(_short_words(beat or spec.composition_goal or spec.scene_action, beat_words))
    place = _scrub_governed_names(lead_place(spec))
    # Order: STILL_ROLE, LOCATION, SCENE_BEAT/ACTION (camera precedes this lead in the caller).
    return f"{still_role} still {int(still_index) + 1} of 3, setting: {place}, beat: {beat_txt}"


def vd_effective_lead(spec: SceneEnvironmentSpec, camera_text: str, *, still_index: int, still_role: str) -> str:
    """Visual Director effective-prefix lead (R2 Part E/F): STILL_ROLE + CAMERA + LOCATION.

    Placed in the VD genre line so camera and location sit inside the 75-token CLIP window;
    SCENE_BEAT / ACTION / PRIMARY_SUBJECT follow immediately in the 'Depict ...' sentence.
    No character names (place is name-scrubbed); no punctuation that ends the genre sentence.
    """
    cam = compact_camera_label(camera_text)
    place = _scrub_governed_names(lead_place(spec)).replace(".", "")
    return f"{still_role} still {int(still_index) + 1} of 3, {cam}, setting: {place}"


def compact_camera_label(camera_text: str) -> str:
    """Framing phrase of a full camera instruction (e.g. 'over-the-shoulder tracking shot')."""
    c = re.sub(r"\s+", " ", str(camera_text or "")).strip()
    for sep in (" of ", " from ", ",", ";"):
        if sep in c:
            c = c.split(sep, 1)[0]
    return c.strip() or "cinematic shot"


# ---- R2 Part M: per-still observability sink -----------------------------------------
STILL_OBSERVABILITY_FIELDS: Tuple[str, ...] = (
    "INPUT_NOVEL_VALUE", "NORMALIZED_NOVEL_ID", "LOCATION_MATCH_CANDIDATES", "LOCATION_MATCH_EVIDENCE",
    "LOCATION_MATCH_REJECTED_CHARACTER_TOKENS", "LOCATION_MATCH_SCORE", "LOCATION_ID", "PLACE_TOKENS_EXTRACTED",
    "PLACE_TOKENS_REJECTED", "STILL_ROLE", "SCENE_BEAT", "COMPOSITION_GOAL", "FULL_PROMPT_HASH",
    "EFFECTIVE_PROMPT_HASH", "EFFECTIVE_PROMPT_TOKEN_COUNT", "SIBLING_EFFECTIVE_PROMPT_HASHES",
    "EFFECTIVE_DIFFERENT_FROM_SIBLINGS", "LEGACY_FALLBACK_USED", "LEGACY_FALLBACK_REASON",
    # R3 Phase 12
    "LOCATION_RELATION_CLASS", "LOCATION_NEGATION_DETECTED", "LOCATION_DEPARTURE_DETECTED",
    "LOCATION_REFERENCE_ONLY", "LOCATION_RELATION_MENTIONS", "LOCATION_RELATION_PRECEDENCE_DEFINED",
    "PER_MENTION_LOCATION_RELATION", "PLACE_PHRASE_CLASS", "PLACE_REJECTION_REASON",
    "SCENE_PATH_CLASS", "SCENE_AUTHORITY_APPLIED", "GENERATOR_GUARD_ACTIVE", "RUNTIME_STATE_GUARD_ACTIVE",
    "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE",
)
_STILL_OBS: Deque[Dict[str, Any]] = deque(maxlen=2048)


def record_still_observability(records: Sequence[Dict[str, Any]]) -> None:
    for r in records:
        _STILL_OBS.append(dict(r))


def recent_still_observability(clear: bool = False) -> List[Dict[str, Any]]:
    out = list(_STILL_OBS)
    if clear:
        _STILL_OBS.clear()
    return out


def build_still_observability(
    *,
    input_novel: Any,
    normalized_novel: str,
    path: str,
    prompts: Sequence[str],
    specs: Sequence[Optional[SceneEnvironmentSpec]],
    beats: Sequence[str],
    roles: Sequence[str],
    legacy_used: Sequence[bool],
    legacy_reasons: Sequence[str],
    cameras: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Per-still observability records for one package (all R2 Part M fields)."""
    try:
        from tools.clip_effective_prompt import effective_prompt
    except Exception:  # pragma: no cover
        effective_prompt = None  # type: ignore
    effs = []
    for p in prompts:
        e = effective_prompt(p) if effective_prompt else {}
        e = dict(e)
        e.pop("EFFECTIVE_PROMPT_IDS", None)
        effs.append(e)
    recs: List[Dict[str, Any]] = []
    for i, p in enumerate(prompts):
        spec = specs[i] if i < len(specs) else None
        obs = dict(spec.observability) if spec is not None else {}
        sib_eff = [effs[j].get("EFFECTIVE_PROMPT_HASH", "") for j in range(len(prompts)) if j != i]
        sib_full = [effs[j].get("FULL_PROMPT_HASH", "") for j in range(len(prompts)) if j != i]
        mine = effs[i]
        recs.append({
            "PATH": path,
            "INPUT_NOVEL_VALUE": "" if input_novel is None else str(input_novel),
            "NORMALIZED_NOVEL_ID": normalized_novel or "UNRESOLVED",
            "STILL_INDEX": i,
            "LOCATION_MATCH_CANDIDATES": obs.get("LOCATION_MATCH_CANDIDATES", []),
            "LOCATION_MATCH_EVIDENCE": obs.get("LOCATION_MATCH_EVIDENCE", {}),
            "LOCATION_MATCH_REJECTED_CHARACTER_TOKENS": obs.get("LOCATION_MATCH_REJECTED_CHARACTER_TOKENS", []),
            "LOCATION_MATCH_SCORE": obs.get("LOCATION_MATCH_SCORE", 0),
            "LOCATION_MATCH_DECISION": obs.get("LOCATION_MATCH_DECISION", ""),
            "LOCATION_ID": spec.location_id if spec is not None else UNRESOLVED,
            "LOCATION_NAME": spec.location_name if spec is not None else UNRESOLVED,
            "LOCATION_AUTHORITY_SOURCE": spec.authority if spec is not None else "MODEL_PRIOR",
            "PLACE_PHRASE": spec.place_phrase if spec is not None else "",
            "PLACE_TOKENS_EXTRACTED": obs.get("PLACE_TOKENS_EXTRACTED", []),
            "PLACE_TOKENS_REJECTED": obs.get("PLACE_TOKENS_REJECTED", []),
            "HP_LANDMARKS_ALLOWED": bool(spec.hp_landmarks_allowed) if spec is not None else False,
            "STILL_ROLE": roles[i] if i < len(roles) else "",
            "SCENE_BEAT": beats[i] if i < len(beats) else "",
            "COMPOSITION_GOAL": (spec.composition_goal if spec is not None else (beats[i] if i < len(beats) else "")),
            "CAMERA": (cameras[i] if cameras and i < len(cameras) else ""),
            "FULL_PROMPT_HASH": mine.get("FULL_PROMPT_HASH", ""),
            "EFFECTIVE_PROMPT_HASH": mine.get("EFFECTIVE_PROMPT_HASH", ""),
            "EFFECTIVE_PROMPT_TOKEN_COUNT": mine.get("EFFECTIVE_PROMPT_TOKEN_COUNT", 0),
            "FULL_PROMPT_TOKEN_COUNT": mine.get("FULL_PROMPT_TOKEN_COUNT", 0),
            "EFFECTIVE_PROMPT_TOKENIZER": mine.get("EFFECTIVE_PROMPT_TOKENIZER", ""),
            "SIBLING_EFFECTIVE_PROMPT_HASHES": sib_eff,
            "SIBLING_FULL_PROMPT_HASHES": sib_full,
            "EFFECTIVE_DIFFERENT_FROM_SIBLINGS": mine.get("EFFECTIVE_PROMPT_HASH", "") not in sib_eff,
            "FULL_DIFFERENT_FROM_SIBLINGS": mine.get("FULL_PROMPT_HASH", "") not in sib_full,
            "LEGACY_FALLBACK_USED": bool(legacy_used[i]) if i < len(legacy_used) else False,
            "LEGACY_FALLBACK_REASON": (legacy_reasons[i] if i < len(legacy_reasons) else "") or "",
            "LOCATION_RELATION_CLASS": obs.get("LOCATION_RELATION_CLASS", LOCATION_RELATION_CURRENT),
            "LOCATION_NEGATION_DETECTED": bool(obs.get("LOCATION_NEGATION_DETECTED", False)),
            "LOCATION_DEPARTURE_DETECTED": bool(obs.get("LOCATION_DEPARTURE_DETECTED", False)),
            "LOCATION_REFERENCE_ONLY": bool(obs.get("LOCATION_REFERENCE_ONLY", False)),
            "LOCATION_RELATION_MENTIONS": list(obs.get("LOCATION_RELATION_MENTIONS") or []),
            "LOCATION_RELATION_PRECEDENCE_DEFINED": bool(obs.get("LOCATION_RELATION_PRECEDENCE_DEFINED", True)),
            "PER_MENTION_LOCATION_RELATION": bool(obs.get("PER_MENTION_LOCATION_RELATION", True)),
            "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE": bool(
                obs.get("PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE", True)
            ),
            "PLACE_PHRASE_CLASS": obs.get("PLACE_PHRASE_CLASS", "LOCATIVE" if (spec and not spec.unknown_location) else "UNRESOLVED"),
            "PLACE_REJECTION_REASON": obs.get("PLACE_REJECTION_REASON", ""),
            "SCENE_PATH_CLASS": obs.get("SCENE_PATH_CLASS", "SCENE_BEARING_CHARACTER_IMAGE"),
            "SCENE_AUTHORITY_APPLIED": bool(obs.get("SCENE_AUTHORITY_APPLIED", spec is not None)),
            "GENERATOR_GUARD_ACTIVE": bool(obs.get("GENERATOR_GUARD_ACTIVE",
                __import__("os").environ.get("AT_GPU_TEST_BARRIER") == "1")),
            "RUNTIME_STATE_GUARD_ACTIVE": bool(obs.get("RUNTIME_STATE_GUARD_ACTIVE",
                __import__("os").environ.get("AT_RUNTIME_STATE_GUARD") == "1")),
            "SUPPORTED_HP_LANDMARKS": list(obs.get("SUPPORTED_HP_LANDMARKS") or []),
            "HP_TEMPLATE_REQUIRES_SCENE_EVIDENCE": True,
        })
    return recs


def environment_observability(spec: SceneEnvironmentSpec) -> Dict[str, Any]:
    """Full per-still observability payload (Part L)."""
    return dict(spec.observability)


def assert_domain_separation(payload: Dict[str, Any]) -> List[str]:
    """Part K: scene-environment payloads must not claim identity/wardrobe/prop/effects authority."""
    violations: List[str] = []
    forbidden_keys = {
        "identity_contract", "wardrobe_lock", "held_prop", "scene_critical_effect",
        "ENABLE_IDENTITY_PRESERVATION", "ENABLE_WARDROBE_PRESERVATION",
    }
    for k in forbidden_keys:
        if k in payload:
            violations.append(k)
    return violations
