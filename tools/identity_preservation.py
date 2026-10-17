"""Character IDENTITY preservation lane (IDENTITY_PRODUCTION_PLUMBING_20260929).

Modeled on tools/wardrobe_preservation.py. Feature flag ENABLE_IDENTITY_PRESERVATION,
source default OFF (PRODUCTION_DEFAULT="NO"). With the flag OFF, nothing here changes
any GenerationSpec, prompt, workflow payload, Visual Director prompt or image
acceptance: every hook returns its input unchanged / BYPASS without side effects.

With the flag ON (four governed characters: Kai / Kael Veyra / Liang / Jarek):
  * governed TEXT_CANON identity contracts (below) attach to GenerationSpec.identity;
  * the identity lock is identity-only (age, build, hair canon, eye canon, traits);
    wardrobe / held-prop / effect tokens are not part of the identity lock;
  * no canonical sex/gender is derived from scene pronouns (Liang SEX=UNSPECIFIED;
    Jarek male is sealed manuscript canon carried by the contract, not a pronoun
    inference at runtime);
  * the whole milestone still is never attached as identity/style conditioning
    (STYLE_REF_EXPERIMENTAL cannot bypass); milestone records remain audit /
    visual-direction references only and never create canon;
  * a verify-only identity verifier gates acceptance of every generated image at the
    production generation chokepoints (app.generate_promo_image_v2 and the V1
    generator primitives). Absent qualified human observations the decision is
    REJECT_REVIEW (no auto-accept), never PASS;
  * an observability record is emitted for every gate run; emitter failure ->
    FAIL_CLOSED.

Authority precedence: TEXT_CANON > VISUAL_DIRECTION > MILESTONE_REFERENCE. A lower tier
never fills a field a higher tier defines or declares UNSPECIFIED; the milestone tier
never supplies a field value at all.

Automation limits (honest, enforced in code): no qualified automated face-identity
model exists (no InsightFace/ArcFace; DavidsPC Python lacks OpenCV). Automated checks
are limited to spec authority, routing, required/forbidden fields, cross-character
binding, milestone-authority leakage, lighting ambiguity policy and decision
composition. FACE / HAIR / BUILD / AGE / EYE / DISTINCTIVE are human-observed; without
a qualified supplied human observation record HUMAN_REVIEW_REQUIRED=YES and the
verifier never returns PASS.

Scope exclusions: wardrobe, held props, scene-critical effects, generic repair and
style refs as identity authority are owned by other lanes and are not changed here.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Feature flag (dedicated; default OFF) - mirrors ENABLE_WARDROBE_PRESERVATION
# ---------------------------------------------------------------------------
FEATURE_FLAG_NAME = "ENABLE_IDENTITY_PRESERVATION"
PRODUCTION_DEFAULT = "NO"  # never flipped by this module
SCOPE = "IDENTITY_ONLY"
SCOPE_EXCLUSIONS = (
    "WARDROBE",
    "HELD_PROP",
    "SCENE_CRITICAL_EFFECTS",
    "GENERIC_REPAIR",
    "STYLE_REFS_AS_IDENTITY_AUTHORITY",
)
AUTHORITY_SOURCE_REQUIRED = "TEXT_CANON"
IDENTITY_AUTHORITY_SOURCE = "TEXT_CANON"
CANON_PRECEDENCE = ("TEXT_CANON", "VISUAL_DIRECTION", "MILESTONE_REFERENCE")
MILESTONE_CREATES_CANON = False
MILESTONE_IDENTITY_AUTHORITY_CREATED = "NO"
UNSPECIFIED = "UNSPECIFIED"
NONCANON_PLACEHOLDER = "NONCANON_PLACEHOLDER"
VERIFIER_DECISIONS = ("PASS", "UNSPECIFIED_OK", "REJECT_REVIEW", "FAIL_CLOSED")
ACCEPTING_DECISIONS = ("PASS", "UNSPECIFIED_OK")
NOT_APPLICABLE_DECISION = "NOT_APPLICABLE_NO_GOVERNED_CHARACTER"
QUALIFIED_OBSERVATION_METHODS = ("HUMAN_REVIEW",)
AUTOMATED_FACE_IDENTITY_MODEL = "NONE_QUALIFIED"  # no InsightFace / ArcFace / OpenCV on DavidsPC
NO_IDENTITY_REFERENCE_CONDITIONING_REASON = (
    "IDENTITY_PRESERVATION_ON:NO_IDENTITY_REFERENCE_CONDITIONING"
    " (whole milestone never attached as identity/style conditioning)"
)

_TRUTHY = {"1", "true", "yes", "on"}


def is_identity_preservation_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True only when ENABLE_IDENTITY_PRESERVATION is explicitly truthy.

    Unset / empty / falsey -> False (production-safe default OFF). Read from the
    process environment exactly like the wardrobe flag (app.py load_dotenv feeds it).
    """
    env = environ if environ is not None else os.environ
    raw = str(env.get(FEATURE_FLAG_NAME, "") or "").strip().lower()
    return raw in _TRUTHY


def feature_flag_status(environ: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    env = environ if environ is not None else os.environ
    raw = str(env.get(FEATURE_FLAG_NAME, "") or "")
    return {
        "FEATURE_FLAG_NAME": FEATURE_FLAG_NAME,
        "FEATURE_FLAG_RAW": raw if raw != "" else "<unset>",
        "FEATURE_FLAG_ENABLED": "YES" if is_identity_preservation_enabled(env) else "NO",
        "PRODUCTION_DEFAULT": PRODUCTION_DEFAULT,
        "SCOPE": SCOPE,
        "SCOPE_EXCLUSIONS": ",".join(SCOPE_EXCLUSIONS),
    }


# ---------------------------------------------------------------------------
# Governed identity contracts (sealed data; no canon YAML edits)
# ---------------------------------------------------------------------------
# Source: output/studio-bible-four-novel-character-identity-preservation-20260924/
#   contracts/FOUR_NOVEL_IDENTITY_CONTRACTS.json (qualified 2026-09-24 contracts).
# Jarek AGE=16 / SEX=male: JAREK_CANON_GAP_REVIEW.md (same packet, canon_src/) -
#   "Soulforge Era - Revised.docx / Revision Pass 1 prologue: 'On the night the door
#   noticed him back, Jarek was sixteen, starving...'" (TEXT_CANON_MS, priority 1).
# Only fields present in those contracts are carried. Absent traits are not inferred.
CONTRACT_SOURCE = (
    "output/studio-bible-four-novel-character-identity-preservation-20260924/"
    "contracts/FOUR_NOVEL_IDENTITY_CONTRACTS.json"
)
CONTRACT_SOURCE_SHA256 = "939f36d561bc5795e637e7df8c80910b570536c0a47df84c2274984291e4a8d7"
JAREK_AGE_SOURCE = (
    "output/studio-bible-four-novel-character-identity-preservation-20260924/canon_src/"
    "JAREK_CANON_GAP_REVIEW.md (sha256 42007243781748be9fffc4286513cff05e05d74e648b23877f534d102853c8d7): "
    "AGE=16 SOURCE=explicit manuscript text; Soulforge Era - Revised.docx / Revision Pass 1 prologue "
    "\"On the night the door noticed him back, Jarek was sixteen, starving...\""
)


@dataclass(frozen=True)
class IdentityContract:
    character_id: str
    novel_id: str
    contract_id: str
    display_name: str
    aliases: Tuple[str, ...]
    age_required: str
    age_allowed: Tuple[str, ...]
    sex: Optional[str]  # value only when sealed TEXT_CANON (Jarek); else None
    build_required: str
    build_allowed: Tuple[str, ...]
    build_forbidden: str
    face_direction: str
    hair_required: Tuple[str, ...]
    hair_allowed: Tuple[str, ...]
    hair_color: Optional[str]
    eye_color_required: str
    eye_color_allowed: Tuple[str, ...]
    distinctive_traits_required: Tuple[str, ...]
    visual_direction_allowed: Tuple[str, ...]
    unspecified_fields: Tuple[str, ...]
    noncanon_placeholders: Tuple[str, ...]
    scene_dependent_fields: Tuple[str, ...]
    identity_forbidden: Tuple[str, ...]
    field_authority: Tuple[Tuple[str, str], ...]
    milestone_reference_id: str
    lock_tokens: Tuple[str, ...]
    vd_age: str
    source: str = CONTRACT_SOURCE

    def authority(self) -> Dict[str, str]:
        return dict(self.field_authority)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["field_authority"] = dict(self.field_authority)
        return d


_FACE_DIRECTION = "CONTINUITY_DIRECTION_ONLY (FACE_GEOMETRY_CANON=false; milestone may only give identity_direction)"

GOVERNED_IDENTITY_CONTRACTS: Dict[str, IdentityContract] = {
    "kai": IdentityContract(
        character_id="kai",
        novel_id="ha",
        contract_id="IDENTITY:ha:kai:20260924",
        display_name="Kai",
        aliases=("kai",),
        age_required="19",
        age_allowed=(),
        sex=None,
        build_required="sickly_thin",
        build_allowed=("average height", "posture slumped/straightening"),
        build_forbidden="gym_adjacent / milestone athletic overwrite",
        face_direction=_FACE_DIRECTION,
        hair_required=("short",),
        hair_allowed=("tied_back_at_work", "combat loosens"),
        hair_color=None,
        eye_color_required="brown",
        eye_color_allowed=("brief_gold_fleck when awake (scene)",),
        distinctive_traits_required=("brown eyes", "short ordinary hair silhouette", "sickly_thin build read"),
        visual_direction_allowed=("identity_direction", "painterly_style_direction"),
        unspecified_fields=("FACE_SHAPE", "HAIR_COLOR", "SKIN", "EXACT_FACIAL_GEOMETRY"),
        noncanon_placeholders=(),
        scene_dependent_fields=("SEX_PRESENTATION_FROM_SCENE_PRONOUNS_ONLY", "POWER_STATE_EFFECTS", "hair wet/combat behavior"),
        identity_forbidden=(
            "import Kael identity",
            "promote milestone athletic build to canon",
            "promote milestone logo/ember/qi geometry to identity canon",
            "hair_color invention as canon",
            "skin invention as canon",
            "gym_adjacent / milestone athletic overwrite",
        ),
        field_authority=(("AGE", "TEXT_CANON"), ("BUILD", "TEXT_CANON"), ("HAIR_STYLE", "TEXT_CANON"),
                         ("EYE_COLOR", "TEXT_CANON"), ("FACE_CONTINUITY", "MILESTONE_DIRECTION_ONLY"),
                         ("HAIR_COLOR", "UNSPECIFIED"), ("SKIN", "UNSPECIFIED"), ("SEX", "SCENE_DEPENDENT_NOT_BIBLE")),
        milestone_reference_id="kai_ha_milestone",
        lock_tokens=("age 19", "sickly thin build", "average height", "short hair", "brown eyes"),
        vd_age="19",
    ),
    "kael_veyra": IdentityContract(
        character_id="kael_veyra",
        novel_id="en",
        contract_id="IDENTITY:en:kael_veyra:20260924",
        display_name="Kael Veyra",
        aliases=("kael_veyra", "kael veyra", "kael", "veyra"),
        age_required="young_adult",
        age_allowed=(),
        sex=None,
        build_required="lean_gamer",
        build_allowed=("average height", "posture hunched/upright"),
        build_forbidden="power-armor body silhouette as identity; gym_adjacent_body",
        face_direction=_FACE_DIRECTION,
        hair_required=("dark_short", "hair_color=dark"),
        hair_allowed=(),
        hair_color="dark",
        eye_color_required="blue_glyph_tinted",
        eye_color_allowed=("glyph_pulse eyes when awake (scene)",),
        distinctive_traits_required=("blue glyph-tinted eyes", "dark_short gamer hair", "lean_gamer build"),
        visual_direction_allowed=("identity_direction", "style_direction"),
        unspecified_fields=("FACE_SHAPE", "SKIN", "EXACT_FACIAL_GEOMETRY"),
        noncanon_placeholders=(),
        scene_dependent_fields=("SEX_PRESENTATION_FROM_SCENE_PRONOUNS_ONLY", "POWER_STATE_EFFECTS", "glyph eye behavior"),
        identity_forbidden=(
            "import Kai identity",
            "hard_armor as identity signal",
            "helmet identity-erase as identity lock",
            "gym_adjacent_body as canon",
            "eye color drift away from blue without scene power justification",
            "power-armor body silhouette as identity; gym_adjacent_body",
        ),
        field_authority=(("AGE", "TEXT_CANON"), ("BUILD", "TEXT_CANON"), ("HAIR_STYLE", "TEXT_CANON"),
                         ("HAIR_COLOR", "TEXT_CANON"), ("EYE_COLOR", "TEXT_CANON"),
                         ("FACE_CONTINUITY", "MILESTONE_DIRECTION_ONLY"), ("SKIN", "UNSPECIFIED"),
                         ("SEX", "SCENE_DEPENDENT_NOT_BIBLE"), ("ARMOR", "WARDROBE_NOT_IDENTITY")),
        milestone_reference_id="kael_en_milestone",
        lock_tokens=("young adult", "lean gamer build", "average height", "dark short hair", "blue glyph-tinted eyes"),
        vd_age="young adult",
    ),
    "liang": IdentityContract(
        character_id="liang",
        novel_id="hp",
        contract_id="IDENTITY:hp:liang:20260924",
        display_name="Liang",
        aliases=("liang",),
        age_required="reborn_adult",
        age_allowed=("reborn_adult facial presentation direction",),
        sex=None,  # SEX=UNSPECIFIED (never male/female; never from pronouns or milestone)
        build_required="cultivator_lean",
        build_allowed=("average height", "mountain_stance"),
        build_forbidden="build overwrite from milestone pixels",
        face_direction=_FACE_DIRECTION,
        hair_required=("dark_topknot", "hair_color=dark"),
        hair_allowed=("exact topknot/bun geometry NONCANON (variation allowed)",),
        hair_color="dark",
        eye_color_required="",  # EYE_COLOR: VISUAL_DIRECTION_NOT_IRIS_LOCK
        eye_color_allowed=("any iris color (exact eye iris color UNSPECIFIED)", "faint_jade_glint when awake (scene)"),
        distinctive_traits_required=("dark topknot silhouette (style not exact geometry)", "cultivator_lean", "reborn_adult presentation"),
        visual_direction_allowed=("identity_direction", "reborn_adult_facial_presentation", "cultivator_lean_direction"),
        unspecified_fields=("SEX", "FACE_SHAPE", "SKIN", "EXACT_EYE_IRIS_COLOR", "EXACT_TOPKNOT_GEOMETRY"),
        noncanon_placeholders=(),
        scene_dependent_fields=("POWER_STATE_EFFECTS", "qi-sensed eye behavior"),
        identity_forbidden=(
            "sex/gender canon from milestone or prior scorecards",
            "exact_topknot_geometry canon",
            "exact_eye_color canon",
            "exact_skin_tone canon",
            "FAIL on unspecified sex presentation",
            "build overwrite from milestone pixels",
        ),
        field_authority=(("AGE", "TEXT_CANON"), ("BUILD", "TEXT_CANON"), ("HAIR_STYLE", "TEXT_CANON"),
                         ("HAIR_COLOR", "TEXT_CANON"), ("EYE_COLOR", "VISUAL_DIRECTION_NOT_IRIS_LOCK"),
                         ("SEX", "UNSPECIFIED"), ("FACE_CONTINUITY", "MILESTONE_DIRECTION_ONLY"), ("SKIN", "UNSPECIFIED")),
        milestone_reference_id="liang_hp_milestone",
        lock_tokens=("reborn adult", "cultivator lean build", "average height", "dark topknot hair"),
        vd_age="reborn adult",
    ),
    "jarek": IdentityContract(
        character_id="jarek",
        novel_id="sf",
        contract_id="IDENTITY:sf:jarek:20260924",
        display_name="Jarek",
        aliases=("jarek",),
        age_required="16",  # HARD: sealed TEXT_CANON_MS (see JAREK_AGE_SOURCE)
        age_allowed=(),
        sex="male",  # sealed TEXT_CANON_MS (JAREK_CANON_GAP_REVIEW), not runtime pronoun inference
        build_required="scavenger_lean",
        build_allowed=(),
        build_forbidden="heavy muscular adult overwrite of age-16 lean",
        face_direction=_FACE_DIRECTION,
        hair_required=("unkempt/matted/wild/scavenger",),
        hair_allowed=("oil_clumped wet behavior", "hair color variation (HAIR_COLOR NONCANON_PLACEHOLDER)"),
        hair_color=None,
        eye_color_required="gold_soul_forge_awake",
        eye_color_allowed=("gold eyes when awake",),
        distinctive_traits_required=("age-16 male", "scavenger_lean", "unkempt wild hair", "gold awake eyes"),
        visual_direction_allowed=(
            "identity_direction",
            "scavenger_lean_hungry_hardened_direction",
            "unkempt_wild_hair_direction",
            "gold_soul_fire_eyes_awakening_cue_direction",
        ),
        unspecified_fields=("HEIGHT_DIRECTION", "FACE_SHAPE", "HAIR_COLOR", "SKIN"),
        noncanon_placeholders=("HAIR_COLOR", "SKIN"),
        scene_dependent_fields=("SOUL_FIRE_PLACEMENT", "POWER_STATE_EFFECTS", "late-timeline aging (out of awakening baseline scope)"),
        identity_forbidden=(
            "skin color as canon requirement",
            "hair color as canon requirement",
            "Gray identity substitution",
            "muscular adult body as age-16 identity",
            "soot_pattern as identity lock",
            "import Kai/Kael/Liang traits",
            "heavy muscular adult overwrite of age-16 lean",
        ),
        field_authority=(("AGE", "TEXT_CANON_MS"), ("SEX", "TEXT_CANON_MS"), ("BUILD", "TEXT_CANON"),
                         ("HAIR_STYLE", "TEXT_CANON"), ("EYE_COLOR", "TEXT_CANON"),
                         ("HAIR_COLOR", "UNSPECIFIED_PLACEHOLDER"), ("SKIN", "UNSPECIFIED_PLACEHOLDER"),
                         ("FACE_CONTINUITY", "MILESTONE_DIRECTION_ONLY")),
        milestone_reference_id="jarek_sf_milestone",
        lock_tokens=("age 16", "male", "scavenger lean build", "unkempt wild hair", "gold eyes"),
        vd_age="16",
    ),
}

_ALIAS_INDEX: Dict[str, str] = {}
for _key, _c in GOVERNED_IDENTITY_CONTRACTS.items():
    for _a in _c.aliases + (_c.character_id,):
        _ALIAS_INDEX[_a.casefold()] = _key


def normalize_identity_character_key(character_id: Any) -> Optional[str]:
    raw = str(character_id or "").strip().casefold().replace("-", "_")
    if not raw:
        return None
    if raw in _ALIAS_INDEX:
        return _ALIAS_INDEX[raw]
    spaced = raw.replace("_", " ")
    if spaced in _ALIAS_INDEX:
        return _ALIAS_INDEX[spaced]
    return None


def get_identity_contract(character_id: Any) -> Optional[IdentityContract]:
    key = normalize_identity_character_key(character_id)
    return GOVERNED_IDENTITY_CONTRACTS.get(key) if key else None


def list_governed_character_keys() -> Tuple[str, ...]:
    return tuple(GOVERNED_IDENTITY_CONTRACTS)


# Prompt-name binding for V1 primitives (whole-word, case-insensitive).
_NAME_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("kael_veyra", re.compile(r"\b(kael\s+veyra|kael|veyra)\b", re.I)),
    ("kai", re.compile(r"\bkai\b", re.I)),
    ("liang", re.compile(r"\bliang\b", re.I)),
    ("jarek", re.compile(r"\bjarek\b", re.I)),
)


def governed_characters_in_text(text: Any) -> Tuple[str, ...]:
    s = str(text or "")
    return tuple(key for key, pat in _NAME_PATTERNS if pat.search(s))


# V1 prompt binding fallback: novel title in the prompt -> that novel's governed
# protagonist contract (mirrors the V2 adapter's request-novel protagonist fallback;
# never another novel's character). Used only when no governed name and no spec.
_NOVEL_TITLE_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("ha", re.compile(r"\bheavenly\s+ascension\b", re.I)),
    ("en", re.compile(r"\beternal\s+nexus\b", re.I)),
    ("hp", re.compile(r"\bhundredfold\s+path\b", re.I)),
    ("sf", re.compile(r"\bsoul\s*forge\b", re.I)),
)


def novel_protagonist_keys_in_text(text: Any) -> Tuple[str, ...]:
    s = str(text or "")
    novels = [nid for nid, pat in _NOVEL_TITLE_PATTERNS if pat.search(s)]
    return tuple(k for nid in novels for k, c in GOVERNED_IDENTITY_CONTRACTS.items() if c.novel_id == nid)


# ---------------------------------------------------------------------------
# IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929
# Part E: production novel alias mapping (derived from existing production code;
# no invented aliases). Part B: structured governed identity-context carrier.
# Part D: binding precedence + fail-closed attribution.
# ---------------------------------------------------------------------------
def identity_contract_version(contract: Optional[IdentityContract]) -> str:
    """Contract version = the dated suffix of the sealed contract id (e.g. 20260924)."""
    if contract is None:
        return ""
    return str(contract.contract_id).rsplit(":", 1)[-1]


# Accepted production aliases -> Studio Bible short novel id. Every entry is cited to the
# production source that already uses it (see ALIAS_MAPPING.md). Case/whitespace/underscore
# insensitive. Unknown values map to nothing (never guessed).
PRODUCTION_NOVEL_ALIASES: Dict[str, str] = {
    # tools/studio_bible_adapter.py _SHORT_NOVEL_IDS (en|ha|hp|sf) and app.py / app_config.py
    # NOVEL_NAMES keys ("EN","HA","SF","HP") -> story_key() abbreviations used by every V1 caller.
    "en": "en",
    "ha": "ha",
    "hp": "hp",
    "sf": "sf",
    # app.py / app_config.py NOVEL_NAMES values + studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID.
    "eternal nexus": "en",
    "heavenly ascension system": "ha",
    "hundredfold path": "hp",
    "the hundredfold path": "hp",
    "soul forge era": "sf",
    "soulforge era": "sf",
    # chapter_cron_handoff.normalize_daily_abbr aliases {"HFP","HUNDREDFOLD","HUNDREDFOLD_PATH"} -> "HP".
    "hfp": "hp",
    "hundredfold": "hp",
    "hundredfold_path": "hp",
}
PRODUCTION_NOVEL_ALIAS_SOURCES: Dict[str, str] = {
    "en": "app.py NOVEL_NAMES['EN']; app_config.NOVEL_NAMES; studio_bible_adapter._SHORT_NOVEL_IDS",
    "ha": "app.py NOVEL_NAMES['HA']; app_config.NOVEL_NAMES; studio_bible_adapter._SHORT_NOVEL_IDS",
    "hp": "app.py NOVEL_NAMES['HP']; app_config.NOVEL_NAMES; studio_bible_adapter._SHORT_NOVEL_IDS",
    "sf": "app.py NOVEL_NAMES['SF']; app_config.NOVEL_NAMES; studio_bible_adapter._SHORT_NOVEL_IDS",
    "eternal nexus": "app.py NOVEL_NAMES['EN']; studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "heavenly ascension system": "app.py NOVEL_NAMES['HA']; studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "hundredfold path": "app.py NOVEL_NAMES['HP']; studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "the hundredfold path": "studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "soul forge era": "app.py NOVEL_NAMES['SF']; studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "soulforge era": "studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID",
    "hfp": "chapter_cron_handoff.normalize_daily_abbr aliases['HFP']",
    "hundredfold": "chapter_cron_handoff.normalize_daily_abbr aliases['HUNDREDFOLD']",
    "hundredfold_path": "chapter_cron_handoff.normalize_daily_abbr aliases['HUNDREDFOLD_PATH']",
}
# Searched and NOT found in production code/config (therefore NOT accepted): "HAS", "SFE".


def _alias_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def resolve_production_novel_alias(value: Any) -> Optional[str]:
    """Map a structured novel id / abbreviation / production title to its short novel id.

    Returns None for empty or unknown values (never guesses)."""
    key = _alias_key(value)
    if not key:
        return None
    if key in PRODUCTION_NOVEL_ALIASES:
        return PRODUCTION_NOVEL_ALIASES[key]
    alt = key.replace("-", "_")
    if alt in PRODUCTION_NOVEL_ALIASES:
        return PRODUCTION_NOVEL_ALIASES[alt]
    alt2 = key.replace("_", " ").replace("-", " ")
    if alt2 in PRODUCTION_NOVEL_ALIASES:
        return PRODUCTION_NOVEL_ALIASES[alt2]
    return None


def governed_character_keys_for_novel(novel_id: Any) -> Tuple[str, ...]:
    nid = str(novel_id or "").strip().casefold()
    return tuple(k for k, c in GOVERNED_IDENTITY_CONTRACTS.items() if c.novel_id == nid)


GOVERNED_NOVEL_IDS: Tuple[str, ...] = tuple(sorted({c.novel_id for c in GOVERNED_IDENTITY_CONTRACTS.values()}))


@dataclass(frozen=True)
class IdentityProductionContext:
    """Structured governed-character context carried from the upstream caller to the
    generation / acceptance boundary (Part B). Prompt text is never part of it."""
    novel_id: str = ""
    novel_abbreviation: str = ""
    character_id: str = ""
    character_name: str = ""
    identity_contract_id: str = ""
    source: str = ""

    def is_empty(self) -> bool:
        return not (self.novel_id or self.novel_abbreviation or self.character_id
                    or self.character_name or self.identity_contract_id)

    def to_dict(self) -> Dict[str, str]:
        return dataclasses.asdict(self)


def build_identity_context(
    *,
    novel: Any = "",
    abbr: Any = "",
    character: Any = "",
    character_id: Any = "",
    identity_contract_id: Any = "",
    source: str = "",
) -> IdentityProductionContext:
    """Build a context from caller-structured values (novel title/id, abbreviation, character)."""
    n_raw = str(novel or "").strip()
    a_raw = str(abbr or "").strip()
    nid = resolve_production_novel_alias(n_raw) or ""
    cid_raw = str(character_id or "").strip()
    cname = str(character or "").strip()
    return IdentityProductionContext(
        novel_id=nid if nid else (n_raw if n_raw else ""),
        novel_abbreviation=a_raw,
        character_id=cid_raw,
        character_name=cname,
        identity_contract_id=str(identity_contract_id or "").strip(),
        source=str(source or ""),
    )


import contextvars as _contextvars  # noqa: E402

_IDENTITY_CONTEXT: "_contextvars.ContextVar[Optional[IdentityProductionContext]]" = _contextvars.ContextVar(
    "identity_production_context", default=None)


def current_identity_context() -> Optional[IdentityProductionContext]:
    return _IDENTITY_CONTEXT.get()


def _context_novel(ctx: Optional[IdentityProductionContext]) -> Optional[str]:
    if ctx is None:
        return None
    return resolve_production_novel_alias(ctx.novel_id) or resolve_production_novel_alias(ctx.novel_abbreviation)


def merge_identity_context(outer: Optional[IdentityProductionContext],
                           inner: Optional[IdentityProductionContext]) -> Optional[IdentityProductionContext]:
    """Inner (more specific) non-empty fields win. If the inner context names a different
    novel than the outer one, the outer character fields are dropped (never carried across)."""
    if inner is None or inner.is_empty():
        return outer
    if outer is None or outer.is_empty():
        return inner
    on, inn = _context_novel(outer), _context_novel(inner)
    base = outer
    if inn and on and inn != on:
        base = IdentityProductionContext()
    return IdentityProductionContext(
        novel_id=inner.novel_id or base.novel_id,
        novel_abbreviation=inner.novel_abbreviation or base.novel_abbreviation,
        character_id=inner.character_id or base.character_id,
        character_name=inner.character_name or base.character_name,
        identity_contract_id=inner.identity_contract_id or base.identity_contract_id,
        source=inner.source or base.source,
    )


class identity_production_context:  # noqa: N801 - used as a context manager
    """``with identity_production_context(build_identity_context(abbr="SF")):`` - sets the
    ambient structured context for the duration of the block (merged with any outer one).
    Has no effect on behaviour while ENABLE_IDENTITY_PRESERVATION is OFF (the gate bypasses)."""

    def __init__(self, ctx: Optional[IdentityProductionContext] = None, **fields: Any):
        self._ctx = ctx if ctx is not None else (build_identity_context(**fields) if fields else None)
        self._token = None

    def __enter__(self) -> Optional[IdentityProductionContext]:
        merged = merge_identity_context(_IDENTITY_CONTEXT.get(), self._ctx)
        self._token = _IDENTITY_CONTEXT.set(merged)
        return merged

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _IDENTITY_CONTEXT.reset(self._token)
            self._token = None


# Binding sources / results (validated in every observability record).
BINDING_SOURCES: Tuple[str, ...] = (
    "SPEC_IDENTITY", "STRUCTURED_CHARACTER_ID", "STRUCTURED_NOVEL_ID", "STRUCTURED_NOVEL_ALIAS",
    "PROMPT_GOVERNED_NAME", "PROMPT_NOVEL_TITLE", "PROMPT_GOVERNED_NAME_SUPPLEMENTAL",
    "GOVERNED_CONTEXT_BINDING_FAILED", "NONE",
)
BINDING_RESULTS: Tuple[str, ...] = ("BOUND", "FAILED", "NO_GOVERNED_CONTEXT", "OUTSIDE_GOVERNED_SCOPE", "ERROR",
                                    # IDENTITY_FINAL_COVERAGE_HARDENING_20260930: structured non-depiction intent,
                                    # governed contract deliberately not bound (scenery bypass).
                                    "NOT_REQUIRED_NON_DEPICTION_INTENT")
GOVERNED_CONTEXT_BINDING_FAILED = "GOVERNED_CONTEXT_BINDING_FAILED"
_LEGACY_BINDING_METHOD = {
    "SPEC_IDENTITY": "SPEC_IDENTITY",
    "STRUCTURED_CHARACTER_ID": "REQUEST_CHARACTER_ID",
    "STRUCTURED_NOVEL_ID": "NOVEL_PROTAGONIST_FALLBACK",
    "STRUCTURED_NOVEL_ALIAS": "NOVEL_PROTAGONIST_FALLBACK",
    "PROMPT_GOVERNED_NAME": "PROMPT_GOVERNED_NAME",
    "PROMPT_GOVERNED_NAME_SUPPLEMENTAL": "PROMPT_GOVERNED_NAME",
    "PROMPT_NOVEL_TITLE": "NOVEL_PROTAGONIST_FALLBACK",
}


@dataclass
class BindingResolution:
    keys: List[str]
    sources: Dict[str, str]
    governed_context_present: bool
    result: str
    no_governed_reason: str = ""
    fail_reason: str = ""
    structured_character_id: str = ""
    structured_novel_id: str = ""
    structured_novel_alias: str = ""
    prompt_fallback_used: bool = False
    request_novel: str = ""
    # IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Parts A/B/E): structured character validation.
    structured_character_status: str = "NOT_APPLICABLE"
    malformed_character_id: bool = False
    structured_character_conflict: bool = False
    structured_governed_keys: List[str] = field(default_factory=list)
    structured_nongoverned_cast: List[str] = field(default_factory=list)
    structured_character_origin: str = ""
    spec_only_character: bool = False


def resolve_governed_binding(
    *,
    spec: Any = None,
    prompt: str = "",
    novel: Any = "",
    character_id: Any = "",
    context: Optional[IdentityProductionContext] = None,
    depicted_characters: Sequence[Any] = (),
) -> BindingResolution:
    """Binding precedence (Part B/D):
      1. structured character (spec.identity.character_id, explicit character_id, context
         character_id / character_name);
      2. structured novel id (explicit novel, context novel_id) + that novel's single governed
         character;
      3. structured novel abbreviation uniquely mapped by PRODUCTION_NOVEL_ALIASES;
      4. prompt fallback (governed names, then novel titles) only when NO structured context.
    Governed names in the prompt are always added as supplemental bindings (never removed).
    Known governed context that cannot be resolved -> FAIL (GOVERNED_CONTEXT_BINDING_FAILED),
    never NO_GOVERNED_CHARACTER.

    IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Parts A/B): every structured character
    (spec / explicit / context id, and ImageIntent depicted characters) is validated
    against the sealed Studio Bible cast of the structured governed novel
    (GOVERNED_NOVEL_CAST). A governed novel + an id that is not a cast member (typo,
    sentinel such as "scenery"/"none") -> FAIL (STRUCTURED_CHARACTER_NOT_IN_NOVEL_CAST);
    a cast member of a different governed novel -> FAIL (STRUCTURED_CHARACTER_NOVEL_CONFLICT);
    two structured character sources naming different characters -> FAIL
    (CONFLICTING_STRUCTURED_CHARACTER). No fuzzy correction; prompt text never repairs it."""
    ctx = context if context is not None else IdentityProductionContext()
    ident = getattr(spec, "identity", None) if spec is not None else None
    spec_cid_raw = str(getattr(ident, "character_id", "") or "") if ident is not None else ""
    explicit_cid_raw = str(character_id or "").strip()
    ctx_cid_raw = ctx.character_id or ctx.character_name
    char_raw = spec_cid_raw or explicit_cid_raw or ctx_cid_raw
    char_origin = "SPEC_IDENTITY" if spec_cid_raw else "STRUCTURED_CHARACTER_ID" if char_raw else ""
    char_key = normalize_identity_character_key(char_raw) if char_raw else None
    novel_raw = str(novel or "").strip() or ctx.novel_id
    abbr_raw = ctx.novel_abbreviation
    novel_from_id = resolve_production_novel_alias(novel_raw) if novel_raw else None
    novel_from_abbr = resolve_production_novel_alias(abbr_raw) if abbr_raw else None
    res = BindingResolution(keys=[], sources={}, governed_context_present=False, result="NO_GOVERNED_CONTEXT",
                            structured_character_id=char_raw,
                            structured_novel_id=novel_from_id or novel_from_abbr or novel_raw,
                            structured_novel_alias=abbr_raw)
    res.request_novel = novel_from_id or novel_from_abbr or ""
    depicted_raw = [str(d or "").strip() for d in (depicted_characters or ()) if str(d or "").strip()]
    structured_present = bool(char_raw or novel_raw or abbr_raw or ctx.identity_contract_id or depicted_raw)
    governed_novel = [n for n in (novel_from_id, novel_from_abbr) if n and governed_character_keys_for_novel(n)]
    res.governed_context_present = bool(char_key or governed_novel or ctx.identity_contract_id)

    def fail(why: str) -> BindingResolution:
        res.keys, res.sources = [], {}
        res.result = "FAILED"
        res.fail_reason = f"{GOVERNED_CONTEXT_BINDING_FAILED}:{why}"
        res.governed_context_present = True
        return res

    if novel_from_id and novel_from_abbr and novel_from_id != novel_from_abbr and governed_novel:
        return fail(f"CONFLICTING_STRUCTURED_NOVEL:{novel_from_id}!={novel_from_abbr}")
    req_novel = novel_from_id or novel_from_abbr
    # Part B: two structured character sources that name different characters conflict.
    _singular = [(o, r) for o, r in (("SPEC_IDENTITY", spec_cid_raw), ("EXPLICIT_CHARACTER_ID", explicit_cid_raw),
                                     ("CONTEXT_CHARACTER", ctx_cid_raw)) if r]
    if len({structured_character_token(r) for _o, r in _singular}) > 1:
        res.structured_character_conflict = True
        res.structured_character_status = "NO_CONFLICTING_STRUCTURED_CHARACTER"
        return fail("CONFLICTING_STRUCTURED_CHARACTER:" + ",".join(f"{o}={r}" for o, r in _singular))
    res.structured_character_origin = _singular[0][0] if _singular else ("INTENT_DEPICTED_CHARACTER" if depicted_raw else "")
    res.spec_only_character = bool(spec_cid_raw) and not explicit_cid_raw and not ctx_cid_raw
    primary: Optional[str] = None
    primary_src = ""
    chk = validate_structured_character(req_novel, char_raw) if char_raw else None
    if chk is not None:
        res.structured_character_status = chk.status
    if char_key:
        c = GOVERNED_IDENTITY_CONTRACTS[char_key]
        primary, primary_src = char_key, char_origin
        res.structured_governed_keys.append(char_key)
        if req_novel and req_novel != c.novel_id:
            # Keep the structured character bound so the verifier's routing check also fires
            # (ROUTING_NOVEL_MATCHES_CONTRACT -> FAIL_CLOSED); the gate forces FAIL_CLOSED.
            res.structured_character_conflict = True
            res.fail_reason = (f"{GOVERNED_CONTEXT_BINDING_FAILED}:CROSS_CHARACTER_NOVEL_MISMATCH:"
                               f"character={char_key}:novel={req_novel}")
    elif char_raw and chk is not None and chk.status == "NO_NOT_IN_NOVEL_CAST":
        # Part A: governed novel context + a structured id that is not a member of that
        # novel's cast (misspelling / sentinel label) -> fail closed, never NO_GOVERNED_CHARACTER.
        res.malformed_character_id = True
        return fail(f"STRUCTURED_CHARACTER_NOT_IN_NOVEL_CAST:{req_novel}:{char_raw}")
    elif char_raw and chk is not None and chk.status == "NO_CAST_MEMBER_OF_OTHER_NOVEL":
        res.structured_character_conflict = True
        return fail(f"STRUCTURED_CHARACTER_NOVEL_CONFLICT:character={char_raw}:cast_novel={chk.cast_novel}:novel={req_novel}")
    elif char_raw:
        # Structured character present but outside the four governed characters (a valid
        # non-governed cast member of the governed novel, or no governed novel context).
        res.result = "OUTSIDE_GOVERNED_SCOPE"
        res.no_governed_reason = f"STRUCTURED_CHARACTER_OUTSIDE_GOVERNED_SCOPE:{char_raw}"
        res.governed_context_present = bool(ctx.identity_contract_id)
        if chk is not None and chk.status == "YES_NON_GOVERNED_CAST_MEMBER":
            res.structured_nongoverned_cast.append(chk.cast_name)
    elif req_novel:
        cand = governed_character_keys_for_novel(req_novel)
        if len(cand) == 1:
            primary = cand[0]
            primary_src = "STRUCTURED_NOVEL_ID" if novel_from_id else "STRUCTURED_NOVEL_ALIAS"
        elif len(cand) > 1:
            return fail(f"AMBIGUOUS_GOVERNED_CHARACTER_FOR_NOVEL:{req_novel}:{','.join(cand)}")
        else:
            res.result = "OUTSIDE_GOVERNED_SCOPE"
            res.no_governed_reason = f"STRUCTURED_NOVEL_NOT_GOVERNED:{req_novel}"
    elif novel_raw or abbr_raw:
        res.no_governed_reason = f"STRUCTURED_NOVEL_UNRESOLVED:{novel_raw or abbr_raw}"
    if ctx.identity_contract_id:
        if primary is None:
            return fail(f"IDENTITY_CONTRACT_ID_UNBOUND:{ctx.identity_contract_id}")
        if GOVERNED_IDENTITY_CONTRACTS[primary].contract_id != ctx.identity_contract_id:
            return fail(f"IDENTITY_CONTRACT_ID_MISMATCH:{ctx.identity_contract_id}")
    depicted_keys: List[str] = []
    for d in depicted_raw:
        dchk = validate_structured_character(req_novel, d)
        if dchk.status == "NO_NOT_IN_NOVEL_CAST":
            res.malformed_character_id = True
            res.structured_character_status = dchk.status
            return fail(f"STRUCTURED_CHARACTER_NOT_IN_NOVEL_CAST:{req_novel}:{d}")
        if dchk.status in ("NO_CAST_MEMBER_OF_OTHER_NOVEL", "NO_GOVERNED_CHARACTER_OF_OTHER_NOVEL"):
            res.structured_character_conflict = True
            res.structured_character_status = dchk.status
            return fail(f"STRUCTURED_CHARACTER_NOVEL_CONFLICT:character={d}:cast_novel={dchk.cast_novel}:novel={req_novel}")
        if dchk.governed_key:
            depicted_keys.append(dchk.governed_key)
            if dchk.governed_key not in res.structured_governed_keys:
                res.structured_governed_keys.append(dchk.governed_key)
        elif dchk.status == "YES_NON_GOVERNED_CAST_MEMBER" and dchk.cast_name not in res.structured_nongoverned_cast:
            res.structured_nongoverned_cast.append(dchk.cast_name)
        if res.structured_character_status == "NOT_APPLICABLE" or dchk.governed_key:
            res.structured_character_status = dchk.status
    if primary is not None:
        res.keys.append(primary)
        res.sources[primary] = primary_src
    for dk in depicted_keys:
        if dk not in res.keys:
            res.keys.append(dk)
            res.sources[dk] = "STRUCTURED_CHARACTER_ID"
    structured_resolved = primary is not None or bool(depicted_keys) or res.result == "OUTSIDE_GOVERNED_SCOPE"
    for k in governed_characters_in_text(prompt):
        if k not in res.keys:
            res.keys.append(k)
            if structured_resolved or structured_present:
                res.sources[k] = "PROMPT_GOVERNED_NAME_SUPPLEMENTAL"
            else:
                res.sources[k] = "PROMPT_GOVERNED_NAME"
                res.prompt_fallback_used = True
    if not res.keys and spec is None and not structured_present:
        for k in novel_protagonist_keys_in_text(prompt):
            if k not in res.keys:
                res.keys.append(k)
                res.sources[k] = "PROMPT_NOVEL_TITLE"
                res.prompt_fallback_used = True
    if not res.keys and spec is None and structured_present and not structured_resolved:
        # Structured context present but unresolved (e.g. unknown abbreviation): prompt
        # titles are still honoured as a fallback so an unresolvable id never weakens binding.
        for k in novel_protagonist_keys_in_text(prompt):
            if k not in res.keys:
                res.keys.append(k)
                res.sources[k] = "PROMPT_NOVEL_TITLE"
                res.prompt_fallback_used = True
    if res.keys:
        res.result = "BOUND"
        res.no_governed_reason = ""
        res.governed_context_present = True
    elif not res.no_governed_reason:
        res.no_governed_reason = ("NO_STRUCTURED_CONTEXT_AND_NO_GOVERNED_NAME_OR_TITLE_IN_PROMPT"
                                  if not structured_present else "STRUCTURED_CONTEXT_NOT_GOVERNED")
    return res


# ---------------------------------------------------------------------------
# IDENTITY_FINAL_COVERAGE_HARDENING_20260930
# Part A: governed-novel cast (sealed from existing Studio Bible data; no invented cast).
# ---------------------------------------------------------------------------
# Source: the Studio Bible character profiles read by tools.studio_bible_adapter.load_character_profiles()
# (BIBLE_DIR/characters/*.yaml, BIBLE_DIR = C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb),
# entry fields `name` + `novel`, verified on DavidsPC 2026-09-30:
#   kael.yaml            sha256 3f1719f23d30dec0930f511d5ccb26316b1b75c6ebd8098294c9c29deeab5320  Kael Veyra / en
#   kai.yaml             sha256 9279e827bac3338a52a3d09193ea1a14668a8528e2f760f50a1bc43db088f7ae  Kai / ha
#   liang.yaml           sha256 00890add23efc0ca04a4ef2dac4fb794273b0b18f59fae373c5ab8ddd71c0b62  Liang / hp
#   sf_protagonists.yaml sha256 3021ceb1eea9be651e45bbc8e106fbea61014dad364026c9af93e20d5379bbfa  Jarek / sf, Gray / sf
# (tests/test_identity_final_hardening.py re-checks this table against the live profiles.)
# Sealed (not re-read at runtime) so a missing / unreadable Bible can never weaken validation.
GOVERNED_NOVEL_CAST: Dict[str, Tuple[str, ...]] = {
    "en": ("Kael Veyra",),
    "ha": ("Kai",),
    "hp": ("Liang",),
    "sf": ("Jarek", "Gray"),
}
GOVERNED_NOVEL_CAST_SOURCE = (
    "Studio Bible characters/*.yaml via tools.studio_bible_adapter.load_character_profiles() "
    "(kael.yaml, kai.yaml, liang.yaml, sf_protagonists.yaml; name+novel fields)"
)


def _cast_token(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " ").replace("-", " ")).strip()


def _cast_index() -> Dict[str, Tuple[str, str]]:
    """token -> (novel_id, canonical cast name). Full name + first token (the same
    first-name alias load_character_profiles registers), exact only (no fuzzy match)."""
    idx: Dict[str, Tuple[str, str]] = {}
    for nid, names in GOVERNED_NOVEL_CAST.items():
        for name in names:
            t = _cast_token(name)
            idx.setdefault(t, (nid, name))
            first = t.split(" ")[0]
            if first:
                idx.setdefault(first, (nid, name))
    return idx


_CAST_INDEX: Dict[str, Tuple[str, str]] = _cast_index()


def governed_novel_cast_members(novel_id: Any) -> Tuple[str, ...]:
    return GOVERNED_NOVEL_CAST.get(str(novel_id or "").strip().casefold(), ())


def structured_character_token(value: Any) -> str:
    """Canonical identity of a structured character value (for conflict detection):
    the governed contract key, else the canonical cast name, else the normalised raw text."""
    key = normalize_identity_character_key(value)
    if key:
        return f"GOVERNED:{key}"
    hit = _CAST_INDEX.get(_cast_token(value))
    if hit:
        return f"CAST:{hit[0]}:{hit[1].casefold()}"
    return f"RAW:{_cast_token(value)}"


@dataclass(frozen=True)
class StructuredCharacterCheck:
    status: str
    governed_key: Optional[str] = None
    cast_name: str = ""
    cast_novel: str = ""


STRUCTURED_CHARACTER_STATUSES: Tuple[str, ...] = (
    "YES_GOVERNED", "YES_NON_GOVERNED_CAST_MEMBER", "NO_NOT_IN_NOVEL_CAST", "NO_CAST_MEMBER_OF_OTHER_NOVEL",
    "NO_GOVERNED_CHARACTER_OF_OTHER_NOVEL", "NO_CONFLICTING_STRUCTURED_CHARACTER",
    "UNVERIFIED_NO_GOVERNED_NOVEL_CONTEXT", "NOT_APPLICABLE",
)


def validate_structured_character(novel_id: Any, character: Any) -> StructuredCharacterCheck:
    """Part A: deterministic validation of a structured character against the governed cast
    of its (structured) novel. Exact tokens only; never corrects a misspelling."""
    raw = str(character or "").strip()
    nid = resolve_production_novel_alias(novel_id) if novel_id else None
    governed_novel = nid if (nid and nid in GOVERNED_NOVEL_CAST) else None
    if not raw:
        return StructuredCharacterCheck("NOT_APPLICABLE")
    key = normalize_identity_character_key(raw)
    if key:
        c = GOVERNED_IDENTITY_CONTRACTS[key]
        if governed_novel and governed_novel != c.novel_id:
            return StructuredCharacterCheck("NO_GOVERNED_CHARACTER_OF_OTHER_NOVEL", key, c.display_name, c.novel_id)
        return StructuredCharacterCheck("YES_GOVERNED", key, c.display_name, c.novel_id)
    hit = _CAST_INDEX.get(_cast_token(raw))
    if governed_novel is None:
        if hit:
            return StructuredCharacterCheck("UNVERIFIED_NO_GOVERNED_NOVEL_CONTEXT", None, hit[1], hit[0])
        return StructuredCharacterCheck("UNVERIFIED_NO_GOVERNED_NOVEL_CONTEXT")
    if hit and hit[0] == governed_novel:
        return StructuredCharacterCheck("YES_NON_GOVERNED_CAST_MEMBER", None, hit[1], hit[0])
    if hit:
        return StructuredCharacterCheck("NO_CAST_MEMBER_OF_OTHER_NOVEL", None, hit[1], hit[0])
    return StructuredCharacterCheck("NO_NOT_IN_NOVEL_CAST", None, "", governed_novel)


# ---------------------------------------------------------------------------
# IDENTITY_FINAL_COVERAGE_HARDENING_20260930 - Part C/D/E/F: ImageIntent contract.
# ---------------------------------------------------------------------------
INTENT_GOVERNED = "GOVERNED_CHARACTER_DEPICTION"
IMAGE_INTENT_CLASSES: Tuple[str, ...] = (
    INTENT_GOVERNED, "SCENERY_ONLY", "ENVIRONMENT_ONLY", "OBJECT_ONLY", "ABSTRACT", "NON_CANON_SILHOUETTE",
)
# Documented extensions (INTENT_CONTRACT.md): a structured non-governed character subject
# (e.g. SF Gray) and "no governed context and no evidence" (never used as a bypass: nothing
# governed is bound in that case).
IMAGE_INTENT_EXTENDED_CLASSES: Tuple[str, ...] = ("NON_GOVERNED_CHARACTER_DEPICTION", "UNDETERMINED")
ALL_IMAGE_INTENT_CLASSES: Tuple[str, ...] = IMAGE_INTENT_CLASSES + IMAGE_INTENT_EXTENDED_CLASSES
NON_DEPICTION_INTENT_CLASSES: Tuple[str, ...] = ("SCENERY_ONLY", "ENVIRONMENT_ONLY", "OBJECT_ONLY", "ABSTRACT")
# Part F precedence (highest first). Prompt heuristics only below every structured level.
IMAGE_INTENT_PRECEDENCE: Tuple[str, ...] = (
    "STRUCTURED_DEPICTED_CHARACTER", "STRUCTURED_SCENE_SUBJECT", "STRUCTURED_ASSET_ROLE",
    "STRUCTURED_BACKGROUND_MARKER", "LEGACY_PROMPT_HEURISTIC",
)
IMAGE_INTENT_SOURCES: Tuple[str, ...] = IMAGE_INTENT_PRECEDENCE + (
    "FORCED_GOVERNED_SIGNAL", "PROCEDURAL_GENERATOR", "SAFE_DEFAULT_NO_STRUCTURED_INTENT",
    # reuse request without structured intent: the reused asset's intact sha-bound structured
    # non-depiction record is the original intent (Part I/J); never used for fresh generation.
    "REUSED_ASSET_SHA_BOUND_RECORD",
)
# Structured scene-subject vocabulary (anything else is read as a CHARACTER claim and
# validated against the cast - an unknown subject can never become a scenery escape).
SCENE_SUBJECT_CLASSES: Dict[str, str] = {
    "scenery": "SCENERY_ONLY", "scenery only": "SCENERY_ONLY", "landscape": "SCENERY_ONLY",
    "establishing": "SCENERY_ONLY", "establishing shot": "SCENERY_ONLY",
    "environment": "ENVIRONMENT_ONLY", "environment only": "ENVIRONMENT_ONLY", "background": "ENVIRONMENT_ONLY",
    "location": "ENVIRONMENT_ONLY", "interior": "ENVIRONMENT_ONLY",
    "object": "OBJECT_ONLY", "object only": "OBJECT_ONLY", "prop": "OBJECT_ONLY", "item": "OBJECT_ONLY",
    "still life": "OBJECT_ONLY",
    "abstract": "ABSTRACT", "pattern": "ABSTRACT", "title card": "ABSTRACT", "typography": "ABSTRACT",
    "character": INTENT_GOVERNED, "person": INTENT_GOVERNED, "people": INTENT_GOVERNED,
    "portrait": INTENT_GOVERNED, "protagonist": INTENT_GOVERNED, "figure": INTENT_GOVERNED,
}
# Structured asset roles / requested asset types. Roles not listed carry no intent evidence
# (character-capable production roles -> safe default: potentially governed).
ASSET_ROLE_CLASSES: Dict[str, str] = {
    "environment background": "ENVIRONMENT_ONLY", "background plate": "ENVIRONMENT_ONLY",
    "environment plate": "ENVIRONMENT_ONLY", "location plate": "ENVIRONMENT_ONLY",
    "establishing shot": "SCENERY_ONLY", "landscape": "SCENERY_ONLY", "scenery": "SCENERY_ONLY",
    "object insert": "OBJECT_ONLY", "prop insert": "OBJECT_ONLY", "product shot": "OBJECT_ONLY",
    "title card": "ABSTRACT", "abstract pattern": "ABSTRACT", "texture": "ABSTRACT",
    "character portrait": INTENT_GOVERNED, "character scene": INTENT_GOVERNED,
    "character thumbnail": INTENT_GOVERNED, "character cover": INTENT_GOVERNED,
}
# Character-capable production roles recorded by the app.py path decorators (evidence only).
CHARACTER_CAPABLE_ASSET_ROLES: Tuple[str, ...] = (
    "img2img regeneration", "weak image regeneration", "social post image", "variant short image",
    "tiktok scene image", "tiktok outro promo card", "deep tiktok scene image", "weekend post image",
    "youtube background keyframe", "youtube chapter pack", "chapter still prompt", "campaign image",
    "story hook image", "story hook thumbnail", "youtube thumbnail", "prompt fallback image",
    "browser imported image", "tiktok pack reuse",
)


@dataclass(frozen=True)
class ImageIntentRequest:
    """Structured upstream intent evidence (never free-text labels in the prompt)."""
    depicted_characters: Tuple[str, ...] = ()
    scene_subject: str = ""
    asset_role: str = ""
    background_only: Optional[bool] = None
    requested_asset_type: str = ""
    origin: str = ""
    # Free scene text of the request: used ONLY for forcing (upgrade to governed), never to downgrade.
    scene_text: str = ""

    def has_evidence(self) -> bool:
        return bool(self.depicted_characters or self.scene_subject or self.asset_role
                    or self.background_only is not None or self.requested_asset_type)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["depicted_characters"] = list(self.depicted_characters)
        return d


def coerce_image_intent_request(value: Any) -> Optional[ImageIntentRequest]:
    if value is None:
        return None
    if isinstance(value, ImageIntentRequest):
        return value
    if isinstance(value, Mapping):
        chars = value.get("depicted_characters", value.get("character_ids", value.get("characters", ())))
        if isinstance(chars, (str, bytes)):
            chars = [chars]
        bg = value.get("background_only", None)
        return ImageIntentRequest(
            depicted_characters=tuple(str(c) for c in (chars or ()) if str(c or "").strip()),
            scene_subject=str(value.get("scene_subject", value.get("shot_subject", value.get("subject", ""))) or ""),
            asset_role=str(value.get("asset_role", value.get("campaign_asset_role", value.get("thumbnail_role", ""))) or ""),
            background_only=(None if bg is None else bool(bg)),
            requested_asset_type=str(value.get("requested_asset_type", value.get("asset_type", "")) or ""),
            origin=str(value.get("origin", "") or ""),
            scene_text=str(value.get("scene_text", "") or ""),
        )
    raise TypeError(f"unsupported image intent type {type(value).__name__}")


_IMAGE_INTENT: "_contextvars.ContextVar[Optional[ImageIntentRequest]]" = _contextvars.ContextVar(
    "identity_image_intent", default=None)


def current_image_intent() -> Optional[ImageIntentRequest]:
    return _IMAGE_INTENT.get()


class image_intent_scope:  # noqa: N801 - context manager
    """Bind structured ImageIntent evidence for the duration of a block. ``only_if_unset``
    keeps an already-bound (more specific upstream) intent. No effect while the flag is OFF."""

    def __init__(self, request: Any = None, *, only_if_unset: bool = False, **fields: Any):
        self._req = coerce_image_intent_request(request if request is not None else (fields or None))
        self._only_if_unset = only_if_unset
        self._token = None

    def __enter__(self) -> Optional[ImageIntentRequest]:
        cur = _IMAGE_INTENT.get()
        if self._req is None or (self._only_if_unset and cur is not None and cur.has_evidence()):
            return cur
        self._token = _IMAGE_INTENT.set(self._req)
        return self._req

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _IMAGE_INTENT.reset(self._token)
            self._token = None


# Prompt -> structured intent registry (Visual Director scene structure; Part G). A VD package
# registers each emitted prompt with the intent derived from its scene structure; the gate looks
# the prompt up (exact match, or the exact prompt + app's appended learned-feedback guidance).
# In-process only: an unknown / restarted process simply falls back to the safe default.
_PROMPT_INTENT_REGISTRY: Dict[str, ImageIntentRequest] = {}
_PROMPT_INTENT_ORDER: List[str] = []
_PROMPT_INTENT_MAX = 1024
_APPENDED_GUIDANCE_PREFIX = "Learned image feedback guidance:"


def _prompt_norm(prompt: Any) -> str:
    return re.sub(r"\s+", " ", str(prompt or "")).strip()


def register_prompt_image_intent(prompt: Any, request: Any) -> None:
    req = coerce_image_intent_request(request)
    norm = _prompt_norm(prompt)
    if req is None or not norm:
        return
    k = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    if k not in _PROMPT_INTENT_REGISTRY:
        _PROMPT_INTENT_ORDER.append(k)
    _PROMPT_INTENT_REGISTRY[k] = req
    while len(_PROMPT_INTENT_ORDER) > _PROMPT_INTENT_MAX:
        _PROMPT_INTENT_REGISTRY.pop(_PROMPT_INTENT_ORDER.pop(0), None)


def lookup_prompt_image_intent(prompt: Any) -> Optional[ImageIntentRequest]:
    raw = str(prompt or "")
    candidates = [raw]
    if _APPENDED_GUIDANCE_PREFIX in raw:
        candidates.append(raw.split(_APPENDED_GUIDANCE_PREFIX, 1)[0])
    for c in candidates:
        norm = _prompt_norm(c)
        if norm:
            hit = _PROMPT_INTENT_REGISTRY.get(hashlib.sha256(norm.encode("utf-8")).hexdigest())
            if hit is not None:
                return hit
    return None


# AIVSB_IDENTITY_PATH_REMEDIATION_20261004: AIVSB-composed prompt evidence carrier.
# The AIVSB reasoning composer (app.compose_aivsb_scene_prompt, chapter path) emits prompts that do
# NOT contain character names, so the Part E anti-spoof forcing (a governed name in the prompt /
# scene text) would never fire downstream and a caller scenery label could auto-accept SCENERY_ONLY
# for governed chapter text. Decision (simplest safe option): every image whose prompt or scene
# text carries an AIVSB-composed prompt is POTENTIALLY_GOVERNED; any non-governed intent class is
# force-upgraded to GOVERNED_CHARACTER_DEPICTION (human review), and the governed character names
# found in the SOURCE chapter text (captured before composition stripped them) are carried to the
# gate as forcing / prompt-equivalent evidence. Structured scenery is NOT expressible on the AIVSB
# path (caller labels alone never bypass). Evidence only ever upgrades; never downgrades.
# Primary carrier: in-process registry (exact normalized composed prompt, matched as a substring of
# the gate prompt / scene text). Backstop for prompts persisted across processes: a format signature
# of the chapter-path composer output ("<novel_id>, [expressing <emotion>, ]<camera> shot").
@dataclass(frozen=True)
class AivsbComposedEvidence:
    novel_id: str = ""
    source_governed_names: Tuple[str, ...] = ()
    origin: str = ""
    matched_by: str = ""  # REGISTRY | SIGNATURE


_AIVSB_COMPOSED_REGISTRY: Dict[str, AivsbComposedEvidence] = {}
_AIVSB_COMPOSED_ORDER: List[str] = []
_AIVSB_COMPOSED_MAX = 1024
_AIVSB_COMPOSED_SIGNATURE = re.compile(
    r"(?<![A-Za-z0-9_])(?:en|ha|hp|sf), (?:expressing [^,]{1,120}, )?[A-Za-z0-9_]+ shot\b")


def register_aivsb_composed_prompt(prompt: Any, *, source_text: Any = "", novel_id: Any = "",
                                   origin: str = "") -> Optional[AivsbComposedEvidence]:
    """Record an AIVSB-composed prompt with the governed names found in its SOURCE chapter text
    (forcing-only evidence). Identical composed prompts merge evidence (union = stricter)."""
    norm = _prompt_norm(prompt)
    if not norm:
        return None
    names = set(governed_characters_in_text(source_text))
    prev = _AIVSB_COMPOSED_REGISTRY.get(norm)
    if prev is not None:
        names |= set(prev.source_governed_names)
    ordered = tuple(k for k in GOVERNED_IDENTITY_CONTRACTS if k in names)
    nid = str(novel_id or "").strip().casefold() or (prev.novel_id if prev is not None else "")
    ev = AivsbComposedEvidence(nid, ordered, origin or (prev.origin if prev is not None else ""), "REGISTRY")
    if norm not in _AIVSB_COMPOSED_REGISTRY:
        _AIVSB_COMPOSED_ORDER.append(norm)
    _AIVSB_COMPOSED_REGISTRY[norm] = ev
    while len(_AIVSB_COMPOSED_ORDER) > _AIVSB_COMPOSED_MAX:
        _AIVSB_COMPOSED_REGISTRY.pop(_AIVSB_COMPOSED_ORDER.pop(0), None)
    return ev


def lookup_aivsb_composed_evidence(*texts: Any) -> Optional[AivsbComposedEvidence]:
    """AIVSB evidence for a gate call: registry hit (composed prompt contained in any text), else the
    composer format signature, else None."""
    norms = [n for n in (_prompt_norm(t) for t in texts) if n]
    if not norms:
        return None
    hits = [ev for k, ev in list(_AIVSB_COMPOSED_REGISTRY.items()) if any(k in n for n in norms)]
    if hits:
        names = {nm for ev in hits for nm in ev.source_governed_names}
        return AivsbComposedEvidence(
            ",".join(sorted({ev.novel_id for ev in hits if ev.novel_id})),
            tuple(k for k in GOVERNED_IDENTITY_CONTRACTS if k in names),
            ",".join(sorted({ev.origin for ev in hits if ev.origin})), "REGISTRY")
    # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: the format detector is ADVISORY only (it may
    # upgrade to review; a non-match never establishes NOT_AIVSB / SCENERY_ONLY / auto-accept, which
    # is now decided by durable provenance in run_identity_acceptance_gate). Tolerant to case, comma
    # emotions, whitespace, hyphenated cameras, removed / renamed headers and truncation.
    from tools.aivsb_prompt_provenance import detect_aivsb_format
    if detect_aivsb_format(*norms)[0] != "NO_MATCH":
        return AivsbComposedEvidence("", (), "aivsb_composer_signature", "SIGNATURE")
    return None


def _vocab_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " ").replace("-", " ")).strip()


@dataclass
class ImageIntent:
    intent_class: str
    source: str
    governed_depiction: bool
    upstream_character_assigned: bool
    evidence: List[str] = field(default_factory=list)
    origin: str = ""
    request: Optional[ImageIntentRequest] = None
    forced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"IMAGE_INTENT_CLASS": self.intent_class, "IMAGE_INTENT_SOURCE": self.source,
                "GOVERNED_CHARACTER_DEPICTION": "YES" if self.governed_depiction else "NO",
                "UPSTREAM_CHARACTER_ASSIGNED": "YES" if self.upstream_character_assigned else "NO",
                "evidence": list(self.evidence), "origin": self.origin, "forced": self.forced}


def resolve_image_intent(
    request: Optional[ImageIntentRequest],
    *,
    binding: Optional[BindingResolution] = None,
    prompt: str = "",
    spec: Any = None,
    emitted_block_key: Optional[str] = None,
    reused_asset_governed: Optional[bool] = None,
    procedural: bool = False,
    aivsb_evidence: Optional[AivsbComposedEvidence] = None,
    provenance_force: Optional[Tuple[str, Tuple[str, ...]]] = None,
) -> ImageIntent:
    """Deterministic ImageIntent (Part C) with Part F precedence and Part E forcing.

    Precedence: STRUCTURED_DEPICTED_CHARACTER > STRUCTURED_SCENE_SUBJECT > STRUCTURED_ASSET_ROLE >
    STRUCTURED_BACKGROUND_MARKER > LEGACY_PROMPT_HEURISTIC; no evidence -> SAFE_DEFAULT (potentially
    governed whenever governed context exists; never "scenery"). Forcing signals only ever UPGRADE
    to GOVERNED_CHARACTER_DEPICTION: a governed name in the prompt / request scene text (documented
    decision), a Visual Director Character Identity block naming a governed character, a GenerationSpec
    identity for a governed character that the prompt / scene names, a reused asset whose sha-bound
    record depicts a governed character."""
    req = request or ImageIntentRequest()
    b = binding
    ev: List[str] = []
    governed_ctx = bool(b is not None and b.governed_context_present) or bool(b is not None and b.keys)
    if procedural:
        return ImageIntent("NON_CANON_SILHOUETTE", "PROCEDURAL_GENERATOR", False, False,
                           ["FALLBACK_ASSET_CLASS=PROCEDURAL_EMERGENCY_ART"], req.origin, req)
    text_names = set(governed_characters_in_text(prompt)) | set(governed_characters_in_text(req.scene_text))
    if aivsb_evidence is not None:
        # AIVSB_IDENTITY_PATH_REMEDIATION_20261004: names from the SOURCE chapter text, captured before
        # AIVSB composition stripped them, count exactly like a governed name in the legacy prompt.
        ev.append(f"AIVSB_COMPOSED_PROMPT={aivsb_evidence.matched_by}")
        if aivsb_evidence.source_governed_names:
            text_names |= set(aivsb_evidence.source_governed_names)
            ev.append("AIVSB_SOURCE_CHAPTER_GOVERNED_NAME=" + ",".join(aivsb_evidence.source_governed_names))
    if provenance_force is not None and provenance_force[1]:
        # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: governed names captured from the SOURCE text
        # before AIVSB rewrote it, recovered from durable provenance (forcing-only evidence).
        text_names |= set(provenance_force[1])
        ev.append("AIVSB_PROVENANCE_PRE_AIVSB_GOVERNED_NAME=" + ",".join(provenance_force[1]))
    gov_struct = list(b.structured_governed_keys) if b is not None else []
    nongov_struct = list(b.structured_nongoverned_cast) if b is not None else []
    spec_key = normalize_identity_character_key(
        getattr(getattr(spec, "identity", None), "character_id", "") if spec is not None else "")
    explicit_nondepiction = False
    cls = src = ""
    # --- level 1: structured depicted character. A GenerationSpec identity that ONLY the V2 adapter
    # supplied (no explicit / context / intent assignment) and that the prompt / scene text does not
    # name is the adapter's novel-protagonist default: novel membership, not depiction evidence.
    depicted_govs = {normalize_identity_character_key(d) for d in req.depicted_characters} - {None}
    spec_is_adapter_default = bool(spec_key and b is not None and b.spec_only_character
                                   and spec_key not in text_names and spec_key not in depicted_govs)
    struct_govs = [k for k in gov_struct if not (spec_is_adapter_default and k == spec_key)]
    if b is not None and (b.malformed_character_id or b.structured_character_conflict):
        cls, src = INTENT_GOVERNED, "STRUCTURED_DEPICTED_CHARACTER"
        ev.append("STRUCTURED_CHARACTER_INVALID_OR_CONFLICTING")
    elif struct_govs:
        cls, src = INTENT_GOVERNED, "STRUCTURED_DEPICTED_CHARACTER"
        ev.append("STRUCTURED_GOVERNED_CHARACTER=" + ",".join(struct_govs))
    # --- level 2: structured scene subject
    subj = _vocab_key(req.scene_subject)
    subj_cls = ""
    if subj:
        if subj in SCENE_SUBJECT_CLASSES:
            subj_cls = SCENE_SUBJECT_CLASSES[subj]
            if subj_cls == INTENT_GOVERNED and not governed_ctx:
                subj_cls = "NON_GOVERNED_CHARACTER_DEPICTION"
        else:
            # a character claim: governed -> governed depiction; valid non-governed cast member ->
            # non-governed; anything else was already failed by the binding (malformed).
            sk = normalize_identity_character_key(req.scene_subject)
            subj_cls = INTENT_GOVERNED if sk else "NON_GOVERNED_CHARACTER_DEPICTION"
    role_cls = ""
    for rv in (req.asset_role, req.requested_asset_type):
        rk = _vocab_key(rv)
        if rk in ASSET_ROLE_CLASSES:
            role_cls = ASSET_ROLE_CLASSES[rk]
            if role_cls == INTENT_GOVERNED and not governed_ctx:
                role_cls = "NON_GOVERNED_CHARACTER_DEPICTION"
            break
        if rk:
            ev.append(f"ASSET_ROLE_NO_INTENT_EVIDENCE={rk}")
    if not cls and subj_cls == INTENT_GOVERNED:
        cls, src = INTENT_GOVERNED, "STRUCTURED_SCENE_SUBJECT"
    elif not cls and nongov_struct:
        cls, src = "NON_GOVERNED_CHARACTER_DEPICTION", "STRUCTURED_DEPICTED_CHARACTER"
        ev.append("STRUCTURED_NON_GOVERNED_CAST=" + ",".join(nongov_struct))
    elif not cls and subj_cls:
        cls, src = subj_cls, "STRUCTURED_SCENE_SUBJECT"
    elif not cls and role_cls:
        cls, src = role_cls, "STRUCTURED_ASSET_ROLE"
    elif not cls and req.background_only is True:
        cls, src = "ENVIRONMENT_ONLY", "STRUCTURED_BACKGROUND_MARKER"
    explicit_nondepiction = cls in NON_DEPICTION_INTENT_CLASSES
    if spec_is_adapter_default and not cls:
        cls, src = INTENT_GOVERNED, "SAFE_DEFAULT_NO_STRUCTURED_INTENT"
        ev.append(f"SPEC_IDENTITY_ADAPTER_NOVEL_DEFAULT={spec_key}")
    elif spec_is_adapter_default:
        ev.append(f"SPEC_IDENTITY_ADAPTER_NOVEL_DEFAULT_IGNORED={spec_key}")
    # --- level 5: legacy prompt heuristic (only when nothing structured exists)
    if not cls and text_names:
        cls, src = INTENT_GOVERNED, "LEGACY_PROMPT_HEURISTIC"
        ev.append("PROMPT_GOVERNED_NAME=" + ",".join(sorted(text_names)))
    if not cls and b is not None and b.prompt_fallback_used and b.keys:
        cls, src = INTENT_GOVERNED, "LEGACY_PROMPT_HEURISTIC"
        ev.append("PROMPT_NOVEL_TITLE")
    if not cls:
        src = "SAFE_DEFAULT_NO_STRUCTURED_INTENT"
        cls = INTENT_GOVERNED if governed_ctx else "UNDETERMINED"
        ev.append("NO_STRUCTURED_INTENT_EVIDENCE")
    # --- Part E forcing: stronger evidence of a governed subject can never be relabelled away
    forced = False
    if cls != INTENT_GOVERNED:
        force: List[str] = []
        if text_names:
            force.append("PROMPT_OR_SCENE_TEXT_GOVERNED_NAME=" + ",".join(sorted(text_names)))
        if emitted_block_key:
            force.append(f"VD_CHARACTER_IDENTITY_BLOCK={emitted_block_key}")
        if reused_asset_governed:
            force.append("REUSED_ASSET_RECORD_GOVERNED_OR_UNKNOWN")
        if aivsb_evidence is not None:
            # AIVSB output is always POTENTIALLY_GOVERNED: no caller label can bypass review on it.
            force.append(f"AIVSB_COMPOSED_PROMPT_POTENTIALLY_GOVERNED={aivsb_evidence.matched_by}")
        if provenance_force is not None:
            force.append(provenance_force[0])
        if force:
            cls, src, forced = INTENT_GOVERNED, "FORCED_GOVERNED_SIGNAL", True
            ev.extend(force)
    upstream = bool(struct_govs or nongov_struct or (subj and subj not in SCENE_SUBJECT_CLASSES)
                    or (b is not None and (b.malformed_character_id or b.structured_character_conflict
                                           or b.structured_character_status == "UNVERIFIED_NO_GOVERNED_NOVEL_CONTEXT")))
    if explicit_nondepiction and not forced:
        ev.append("EXPLICIT_STRUCTURED_NON_DEPICTION_INTENT")
    return ImageIntent(cls, src, cls == INTENT_GOVERNED, upstream, ev, req.origin, req, forced)


def _intent_record_hash(rec: Mapping[str, Any]) -> str:
    canon = {k: str(rec.get(k, "") or "") for k in (
        "IMAGE_SHA256", "IMAGE_INTENT_CLASS", "IMAGE_INTENT_SOURCE", "GOVERNED_CHARACTER_DEPICTION",
        "SCENERY_BYPASS_APPLIED", "NOVEL", "CHARACTER", "AUTO_ACCEPT_ALLOWED")}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def reused_asset_recorded_governed(image_path: Optional[Path], image_sha256: str) -> Tuple[Optional[bool], str]:
    """Part I: what do the reused pixels depict, per their own sha-bound identity record?
    (False, why) only when the asset's sidecar records an accepted structured scenery bypass for
    exactly these bytes (IMAGE_SHA256 + IMAGE_INTENT_RECORD_HASH intact); (True, why) when a record
    shows a governed depiction or a prior identity review exists; (None, why) when unknown."""
    if image_path is None:
        return None, "NO_IMAGE"
    try:
        prior = load_prior_review_records(None, image_path)
    except Exception:
        prior = []
    if any(str(r.get("CHARACTER_ID") or "").strip() for r in prior if isinstance(r, Mapping)):
        return True, "PRIOR_REVIEW_RECORD_NAMES_CHARACTER"
    side = image_path.with_name(image_path.name + ".identity_preservation.json")
    try:
        rec = json.loads(side.read_text(encoding="utf-8")) if side.exists() else None
    except Exception:
        return None, "IDENTITY_SIDECAR_UNREADABLE"
    if not isinstance(rec, Mapping):
        return None, "NO_IDENTITY_SIDECAR"
    if str(rec.get("IMAGE_SHA256") or "").lower() != str(image_sha256 or "").lower() or not image_sha256:
        return None, "IDENTITY_SIDECAR_SHA_MISMATCH"
    if str(rec.get("IMAGE_INTENT_RECORD_HASH") or "") != _intent_record_hash(rec):
        return None, "IDENTITY_SIDECAR_INTENT_HASH_MISMATCH"
    if rec.get("GOVERNED_CHARACTER_DEPICTION") == "YES" or str(rec.get("CHARACTER") or ""):
        return True, "IDENTITY_SIDECAR_GOVERNED_DEPICTION"
    if (rec.get("SCENERY_BYPASS_APPLIED") == "YES" and rec.get("IMAGE_INTENT_CLASS") in NON_DEPICTION_INTENT_CLASSES
            and rec.get("AUTO_ACCEPT_ALLOWED") == "YES"
            and rec.get("IMAGE_INTENT_SOURCE") in IMAGE_INTENT_PRECEDENCE[:4]):
        return False, "IDENTITY_SIDECAR_STRUCTURED_NON_DEPICTION:" + str(rec.get("IMAGE_INTENT_CLASS"))
    return None, "IDENTITY_SIDECAR_NOT_A_STRUCTURED_SCENERY_RECORD"


# Visual Director emitted identity block (Part A: the verifier audits the actually
# emitted text, not only the contract phrase).
_VD_BLOCK_RE = re.compile(r"Character Identity:\s*(.+?)\.(?=\s+[A-Z][A-Za-z ()/\-]*:|\s*$)", re.S)


def extract_emitted_identity_block(prompt: Any) -> str:
    m = _VD_BLOCK_RE.search(str(prompt or ""))
    return m.group(1).strip() if m else ""


def emitted_block_character(block: str) -> Optional[str]:
    m = re.search(r"Name:\s*([^;]+)", block or "")
    return normalize_identity_character_key(m.group(1).strip()) if m else None


def contract_sex_for_record(character_id: Any) -> str:
    """Record gender under flag ON: sealed TEXT_CANON only (Jarek male); never pronouns."""
    c = get_identity_contract(character_id)
    if c is None or not c.sex:
        return ""
    if not c.authority().get("SEX", "").startswith("TEXT_CANON"):
        return ""
    return c.sex


def contract_age_presentation(character_id: Any) -> str:
    c = get_identity_contract(character_id)
    if c is None:
        return ""
    return c.age_required.replace("_", " ")


# ---------------------------------------------------------------------------
# Identity-only lock + denylist
# ---------------------------------------------------------------------------
# Terms that belong to wardrobe / accessories / weapons / props / HUD / effects /
# environment lanes and must never appear in the identity lock.
IDENTITY_LOCK_DENYLIST: Tuple[str, ...] = (
    "shirt", "pants", "trousers", "robe", "robes", "armor", "armour", "shell", "jacket",
    "coat", "rags", "wear", "trim", "logo", "emblem", "badge", "accessory", "accessories",
    "necklace", "amulet", "belt", "cloak", "hood", "helmet", "weapon", "sword", "jian",
    "blade", "soulblade", "staff", "spear", "prop", "banner", "banners", "chains",
    "hud", "holo", "ui", "glow", "glowing", "qi", "ember", "aura", "lightning", "frost",
    "soul fire", "flame", "glyphs", "blueprints", "choir", "music",
    "alley", "city", "courtyard", "forge", "undercity", "mountain", "sect", "rain", "neon",
    "environment", "background",
)
_DENY_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in IDENTITY_LOCK_DENYLIST) + r")\b", re.I)


def identity_lock_denylist_hits(text: Any) -> List[str]:
    return sorted({m.group(0).lower() for m in _DENY_RE.finditer(str(text or ""))})


def identity_only_lock_phrase(contract: Optional[IdentityContract]) -> str:
    """Identity-only CLIP lock from the governed contract (no wardrobe/effects/props/env)."""
    if contract is None:
        return ""
    return ", ".join(contract.lock_tokens)


def record_identity_only_lock(hair: str, eyes: str, build: str) -> str:
    """Identity-only lock for a NON-governed character under flag ON (hair/eyes/build only)."""
    bits: List[str] = []
    if hair:
        bits.append(hair if "hair" in hair.lower() else f"{hair} hair")
    if eyes:
        bits.append(eyes if "eye" in eyes.lower() else f"{eyes} eyes")
    if build:
        bits.append(build)
    return ", ".join(b for b in bits if not identity_lock_denylist_hits(b))


# ---------------------------------------------------------------------------
# Authority resolver (TEXT_CANON > VISUAL_DIRECTION > MILESTONE_REFERENCE)
# ---------------------------------------------------------------------------
_FIELD_FROM_REQUIRED = {"AGE": "age_required", "BUILD": "build_required", "EYE_COLOR": "eye_color_required"}


def text_canon_identity(contract: IdentityContract) -> Dict[str, Any]:
    tc: Dict[str, Any] = {
        "AGE": contract.age_required,
        "BUILD": contract.build_required,
        "HAIR_STYLE": contract.hair_required[0] if contract.hair_required else "",
    }
    if contract.hair_color:
        tc["HAIR_COLOR"] = contract.hair_color
    if contract.eye_color_required:
        tc["EYE_COLOR"] = contract.eye_color_required
    if contract.sex:
        tc["SEX"] = contract.sex
    auth = contract.authority()
    return {k: {"value": v, "source": auth.get(k, "TEXT_CANON")} for k, v in tc.items() if v}


def resolve_identity_constraint(
    contract: IdentityContract,
    *,
    visual_direction: Iterable[Any] = (),
    milestone_proposals: Iterable[Tuple[str, Any, str]] = (),
) -> Dict[str, Any]:
    """Resolve FINAL_IDENTITY_CONSTRAINT. Milestone proposals are always BLOCKED.

    ``visual_direction`` items are direction tokens; they are kept only if listed in
    the contract's VISUAL_DIRECTION_ALLOWED and never become field values. A
    (field, value) visual proposal for a TEXT_CANON or UNSPECIFIED field is blocked.
    """
    final = text_canon_identity(contract)
    unspecified = set(contract.unspecified_fields)
    for f in sorted(unspecified):
        if f in final:
            continue
        src = NONCANON_PLACEHOLDER if f in contract.noncanon_placeholders else UNSPECIFIED
        final[f] = {"value": None, "source": src}
    final["FACE_CONTINUITY"] = {"value": "direction_only", "source": "MILESTONE_DIRECTION_ONLY"}
    blocked: List[Dict[str, Any]] = []
    direction: List[str] = []
    for item in visual_direction or ():
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            fld, val = str(item[0]).upper(), item[1]
            reason = ("TEXT_CANON_WINS" if fld in final and final[fld]["value"] is not None
                      else "UNSPECIFIED_STAYS_UNSPECIFIED" if fld in unspecified
                      else "VISUAL_DIRECTION_IS_DIRECTION_ONLY")
            blocked.append({"field": fld, "proposed_value": val, "proposal_source": "VISUAL_DIRECTION",
                            "decision": "BLOCKED", "reason": reason})
            continue
        tok = str(item)
        if tok in contract.visual_direction_allowed:
            direction.append(tok)
    for prop in milestone_proposals or ():
        fld, val, why = (list(prop) + ["", "", ""])[:3]
        fld = str(fld).upper()
        if fld in final and final[fld]["value"] is not None:
            reason = "TEXT_CANON_WINS"
        elif fld in unspecified or final.get(fld, {}).get("source") in (UNSPECIFIED, NONCANON_PLACEHOLDER):
            reason = "UNSPECIFIED_STAYS_UNSPECIFIED"
        elif fld in ("FACE_GEOMETRY", "FACE_SHAPE"):
            reason = "FACE_GEOMETRY_CANON_FALSE"
        elif fld in ("ARMOR_AS_IDENTITY", "WARDROBE_AS_IDENTITY", "WARDROBE", "ARMOR"):
            reason = "WARDROBE_NOT_IDENTITY"
        else:
            reason = "MILESTONE_NOT_IDENTITY_AUTHORITY"
        blocked.append({"field": fld, "proposed_value": val, "proposal_source": why or "MILESTONE_REFERENCE",
                        "decision": "BLOCKED", "reason": reason})
    return {
        "CHARACTER": contract.character_id,
        "NOVEL": contract.novel_id,
        "IDENTITY_CONTRACT_ID": contract.contract_id,
        "AUTHORITY_SOURCE": IDENTITY_AUTHORITY_SOURCE,
        "CANON_PRECEDENCE": list(CANON_PRECEDENCE),
        "FINAL_IDENTITY_CONSTRAINT": final,
        "VISUAL_DIRECTION": direction or list(contract.visual_direction_allowed),
        "MILESTONE_REFERENCE_ID": contract.milestone_reference_id,
        "MILESTONE_CREATES_CANON": False,
        "BLOCKED_PROPOSALS": blocked,
        "IDENTITY_LOCK": identity_only_lock_phrase(contract),
    }


# ---------------------------------------------------------------------------
# GenerationSpec integration (flag-gated; OFF returns input unchanged)
# ---------------------------------------------------------------------------

def identity_spec_fields(contract: IdentityContract) -> Dict[str, Any]:
    unspec = tuple(
        (f"{f}:{NONCANON_PLACEHOLDER}" if f in contract.noncanon_placeholders else f)
        for f in contract.unspecified_fields
    )
    return {
        "character_id": contract.character_id,
        "novel_id": contract.novel_id,
        "contract_id": contract.contract_id,
        "age_required": contract.age_required,
        "age_allowed": tuple(contract.age_allowed),
        "build_required": contract.build_required,
        "build_allowed": tuple(contract.build_allowed),
        "face_direction": contract.face_direction,
        "hair_required": tuple(contract.hair_required),
        "hair_allowed": tuple(contract.hair_allowed),
        "eye_color_required": contract.eye_color_required,
        "eye_color_allowed": tuple(contract.eye_color_allowed),
        "distinctive_traits_required": tuple(contract.distinctive_traits_required),
        "visual_direction_allowed": tuple(contract.visual_direction_allowed),
        "unspecified_fields": unspec,
        "scene_dependent_fields": tuple(contract.scene_dependent_fields),
        "identity_forbidden": tuple(contract.identity_forbidden),
        "authority_source": IDENTITY_AUTHORITY_SOURCE,
        "milestone_reference_id": contract.milestone_reference_id,
    }


def apply_identity_to_generation_spec(
    spec: Any,
    *,
    character_id: str = "",
    novel_id: str = "",
    environ: Optional[Mapping[str, str]] = None,
) -> Any:
    """Flag-gated: attach governed identity contract + strip whole-milestone style_refs.

    OFF -> the same spec object is returned (byte/field identical).
    ON + governed character -> IdentitySpec expanded with TEXT_CANON identity fields;
    references.style_refs emptied (NO_IDENTITY_REFERENCE_CONDITIONING).
    ON + non-governed character -> only style_refs are emptied.
    ``novel_id`` is the REQUEST novel; the contract's own novel is recorded on the
    spec, and a mismatch is caught by the acceptance gate (cross-character route).
    """
    env = environ if environ is not None else os.environ
    if not is_identity_preservation_enabled(env):
        return spec
    ident = getattr(spec, "identity", None)
    refs = getattr(spec, "references", None)
    cid = character_id or getattr(ident, "character_id", "") or ""
    contract = get_identity_contract(cid)
    changes: Dict[str, Any] = {}
    if refs is not None and tuple(getattr(refs, "style_refs", ()) or ()):
        changes["references"] = dataclasses.replace(refs, style_refs=())
    if contract is not None and ident is not None:
        changes["identity"] = dataclasses.replace(ident, **identity_spec_fields(contract))
    if not changes:
        return spec
    return dataclasses.replace(spec, **changes)


def identity_spec_is_populated(identity: Any) -> bool:
    return bool(getattr(identity, "contract_id", "") or getattr(identity, "authority_source", ""))


def milestone_style_refs_blocked(environ: Optional[Mapping[str, str]] = None) -> bool:
    return is_identity_preservation_enabled(environ)


# ---------------------------------------------------------------------------
# Verifier (VERIFY-ONLY; never mutates images)
# ---------------------------------------------------------------------------
METHOD_SPEC = "DETERMINISTIC_SPEC_AUDIT"
METHOD_HUMAN = "HUMAN_REVIEW"
METHOD_NONE = "NOT_ASSESSED_HUMAN_REVIEW_REQUIRED"

_COLORED_LIGHT_RE = re.compile(
    r"\b(neon|magenta|cyan|colou?red light|rgb|forge[- ]fire|firelight|fire light|red light|"
    r"green light|blue light|purple|violet|ultraviolet|holo(graphic)? glow|glow(ing)?)\b",
    re.I,
)


def lighting_confound_from_text(text: Any) -> bool:
    return bool(_COLORED_LIGHT_RE.search(str(text or "")))


@dataclass
class IdentityVerification:
    character_id: str
    decision: str
    fail_reasons: List[str]
    human_review_required: bool
    confidence: str
    automated_checks: List[Dict[str, Any]]
    fields: Dict[str, Dict[str, Any]]
    observation_method: str
    lighting_confound: bool
    constraint: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


_TRAIT_KEYS = (("face", "FACE_MATCH"), ("hair", "HAIR_MATCH"), ("build", "BUILD_MATCH"),
               ("age", "AGE_MATCH"), ("eyes", "EYE_COLOR_MATCH"), ("distinctive", "DISTINCTIVE_TRAITS_MATCH"))


def _automated_spec_checks(
    contract: IdentityContract,
    *,
    spec: Any,
    request_character_id: str,
    request_novel_id: str,
    identity_lock_text: Optional[str],
    milestone_conditioning_used: bool,
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "method": METHOD_SPEC})

    req_key = normalize_identity_character_key(request_character_id) if request_character_id else None
    add("ROUTING_REQUEST_MATCHES_CONTRACT", (not request_character_id) or req_key == contract.character_id,
        {"request": request_character_id, "contract": contract.character_id})
    rn = str(request_novel_id or "").strip().casefold()
    add("ROUTING_NOVEL_MATCHES_CONTRACT", (not rn) or rn == contract.novel_id,
        {"request_novel": request_novel_id, "contract_novel": contract.novel_id})
    ident = getattr(spec, "identity", None) if spec is not None else None
    if spec is not None:
        expected = identity_spec_fields(contract)
        populated = identity_spec_is_populated(ident)
        add("SPEC_IDENTITY_CONTRACT_ATTACHED", populated, getattr(ident, "contract_id", ""))
        add("SPEC_AUTHORITY_TEXT_CANON", getattr(ident, "authority_source", "") == IDENTITY_AUTHORITY_SOURCE,
            getattr(ident, "authority_source", ""))
        mismatched = []
        for k, v in expected.items():
            actual = getattr(ident, k, None)
            if isinstance(v, tuple):
                actual = tuple(actual or ())
            if actual != v:
                mismatched.append(k)
        add("SPEC_REQUIRED_FIELDS_MATCH_CONTRACT", not mismatched, mismatched)
        spec_cid = normalize_identity_character_key(getattr(ident, "character_id", ""))
        add("CROSS_CHARACTER_BINDING", spec_cid == contract.character_id,
            {"spec_character": getattr(ident, "character_id", ""), "contract": contract.character_id})
        # UNSPECIFIED must stay valueless (e.g. Liang iris / sex).
        filled = []
        if "EXACT_EYE_IRIS_COLOR" in contract.unspecified_fields and getattr(ident, "eye_color_required", ""):
            filled.append("EYE_COLOR")
        add("UNSPECIFIED_FIELDS_NOT_FILLED", not filled, filled)
        style_refs = tuple(getattr(getattr(spec, "references", None), "style_refs", ()) or ())
        add("MILESTONE_NOT_ATTACHED_AS_CONDITIONING", not style_refs,
            [getattr(b, "asset_path", "") for b in style_refs])
        lock = identity_lock_text if identity_lock_text is not None else str(
            getattr(getattr(spec, "composition", None), "focal_point", "") or "")
    else:
        lock = identity_lock_text if identity_lock_text is not None else identity_only_lock_phrase(contract)
    hits = identity_lock_denylist_hits(lock)
    add("IDENTITY_LOCK_FORBIDDEN_TERMS_ABSENT", not hits, hits)
    other = [k for k in governed_characters_in_text(lock) if k != contract.character_id]
    add("IDENTITY_LOCK_NO_OTHER_CHARACTER", not other, other)
    add("MILESTONE_CONDITIONING_NOT_USED", not milestone_conditioning_used, bool(milestone_conditioning_used))
    add("MILESTONE_IDENTITY_AUTHORITY_NOT_CREATED", True, "milestone supplies identity_direction only")
    return checks


def verify_identity(
    contract: Optional[IdentityContract],
    *,
    spec: Any = None,
    request_character_id: str = "",
    request_novel_id: str = "",
    identity_lock_text: Optional[str] = None,
    milestone_conditioning_used: bool = False,
    lighting_text: str = "",
    observations: Optional[Mapping[str, Any]] = None,
    image_sha256: str = "",
    milestone_proposals: Iterable[Tuple[str, Any, str]] = (),
) -> IdentityVerification:
    """Compose an identity decision. Never mutates image bytes; never auto-accepts
    visual traits without a qualified HUMAN_REVIEW observation record."""
    if contract is None:
        return IdentityVerification("", "FAIL_CLOSED", ["NO_GOVERNED_CONTRACT"], True, "HIGH", [], {}, "NONE", False, {})
    constraint = resolve_identity_constraint(contract, milestone_proposals=milestone_proposals)
    checks = _automated_spec_checks(
        contract, spec=spec, request_character_id=request_character_id, request_novel_id=request_novel_id,
        identity_lock_text=identity_lock_text, milestone_conditioning_used=milestone_conditioning_used,
    )
    lc_text = lighting_text
    if not lc_text and spec is not None:
        lc_text = " ".join(str(x or "") for x in (
            getattr(getattr(spec, "style", None), "lighting_design", ""),
            getattr(getattr(spec, "conditioning", None), "lighting", ""),
        ))
    obs = dict(observations or {})
    lighting_confound = bool(obs.get("lighting_confound")) or lighting_confound_from_text(lc_text)
    fields: Dict[str, Dict[str, Any]] = {
        name: {"status": METHOD_NONE, "method": METHOD_NONE} for _, name in _TRAIT_KEYS
    }
    fields["AGE_MATCH"]["expected"] = contract.age_required
    fields["SEX"] = ({"status": "NOT_ASSESSED_UNSPECIFIED", "method": METHOD_SPEC, "note": "SEX=UNSPECIFIED; never a violation, never canon"}
                     if "SEX" in contract.unspecified_fields else
                     {"status": METHOD_NONE, "method": METHOD_NONE, "expected": contract.sex} if contract.sex else
                     {"status": "NOT_REQUIRED", "method": METHOD_SPEC, "note": "SCENE_DEPENDENT_NOT_BIBLE"})
    fields["SKIN"] = {"status": "NOT_ASSESSED_PLACEHOLDER" if "SKIN" in contract.noncanon_placeholders else "NOT_ASSESSED_UNSPECIFIED",
                      "method": METHOD_SPEC}
    fields["HAIR_COLOR"] = ({"status": "NOT_ASSESSED_PLACEHOLDER", "method": METHOD_SPEC} if "HAIR_COLOR" in contract.noncanon_placeholders
                            else {"status": "NOT_ASSESSED_UNSPECIFIED", "method": METHOD_SPEC} if "HAIR_COLOR" in contract.unspecified_fields
                            else {"status": "PART_OF_HAIR_MATCH", "method": METHOD_SPEC, "canon": contract.hair_color})
    if "EXACT_EYE_IRIS_COLOR" in contract.unspecified_fields:
        fields["EYE_COLOR_MATCH"] = {"status": "NOT_REQUIRED", "method": METHOD_SPEC, "note": "exact iris color UNSPECIFIED"}

    failed = [c["check"] for c in checks if not c["ok"]]
    if failed:
        return IdentityVerification(contract.character_id, "FAIL_CLOSED", [f"AUTOMATED_CHECK_FAILED:{f}" for f in failed],
                                    True, "HIGH", checks, fields, "NONE", lighting_confound, constraint)
    if not obs:
        return IdentityVerification(contract.character_id, "REJECT_REVIEW", ["HUMAN_REVIEW_OBSERVATIONS_ABSENT",
                                    "NO_QUALIFIED_AUTOMATED_FACE_IDENTITY_MODEL"], True, "NONE", checks, fields,
                                    "NONE", lighting_confound, constraint)
    method = str(obs.get("method") or "").strip().upper()
    reviewer = str(obs.get("reviewer") or "").strip()
    obs_sha = str(obs.get("image_sha256") or "").strip().lower()
    obs_char = normalize_identity_character_key(obs.get("character_id") or contract.character_id)
    if not method or not reviewer or not obs_sha:
        return IdentityVerification(contract.character_id, "FAIL_CLOSED", ["OBSERVATION_PROVENANCE_MISSING"], True,
                                    "HIGH", checks, fields, method or "NONE", lighting_confound, constraint)
    if image_sha256 and obs_sha != image_sha256.lower():
        return IdentityVerification(contract.character_id, "FAIL_CLOSED", ["OBSERVATION_IMAGE_SHA_MISMATCH"], True,
                                    "HIGH", checks, fields, method, lighting_confound, constraint)
    if obs_char != contract.character_id:
        return IdentityVerification(contract.character_id, "FAIL_CLOSED", ["OBSERVATION_CHARACTER_MISMATCH"], True,
                                    "HIGH", checks, fields, method, lighting_confound, constraint)
    if method not in QUALIFIED_OBSERVATION_METHODS:
        return IdentityVerification(contract.character_id, "REJECT_REVIEW", [f"UNQUALIFIED_OBSERVATION_METHOD:{method}"],
                                    True, "LOW", checks, fields, method, lighting_confound, constraint)
    # Qualified human observation record: shadow-qualified decision composition.
    for key, name in _TRAIT_KEYS:
        if name == "EYE_COLOR_MATCH" and fields[name].get("status") == "NOT_REQUIRED":
            continue
        o = obs.get(key)
        if isinstance(o, Mapping):
            fields[name] = {"status": str(o.get("status") or "NOT_ASSESSABLE").upper(), "observed": o.get("observed"),
                            "conf": o.get("conf"), "method": METHOD_HUMAN}
        else:
            fields[name] = {"status": "NOT_ASSESSABLE", "method": METHOD_HUMAN}
    fields["AGE_MATCH"]["expected"] = contract.age_required
    if contract.sex:
        o = obs.get("sex")
        fields["SEX"] = ({"status": str(o.get("status") or "NOT_ASSESSABLE").upper(), "observed": o.get("observed"),
                          "method": METHOD_HUMAN, "expected": contract.sex} if isinstance(o, Mapping)
                         else {"status": "NOT_ASSESSABLE", "method": METHOD_HUMAN, "expected": contract.sex})
    if not bool(obs.get("face_readable")) or str(obs.get("view", "")).lower() in ("rear", "back", "uncertain"):
        return IdentityVerification(contract.character_id, "FAIL_CLOSED", ["FACE_NOT_READABLE_IDENTITY_UNVERIFIABLE"], True,
                                    "HIGH", checks, fields, method, lighting_confound, constraint)
    reasons: List[str] = []
    confirmed: List[str] = []
    ambiguous: List[str] = []
    if fields["FACE_MATCH"]["status"] in ("MATERIAL_DRIFT", "MISMATCH", "DRIFT"):
        reasons.append("FACE_DRIFT_VS_IDENTITY_DIRECTION")
        ambiguous.append("FACE")  # never definite: FACE_GEOMETRY_CANON=false, no face-ID model
    elif fields["FACE_MATCH"]["status"] not in ("MATCH", "CONSISTENT"):
        reasons.append("FACE_NOT_ASSESSABLE")
        ambiguous.append("FACE")
    required = [("HAIR_MATCH", "HAIR"), ("BUILD_MATCH", "BUILD"), ("AGE_MATCH", "AGE"),
                ("EYE_COLOR_MATCH", "EYE_COLOR"), ("DISTINCTIVE_TRAITS_MATCH", "DISTINCTIVE")]
    if contract.sex:
        required.append(("SEX", "SEX"))
    drift_name = {"AGE": "AGE_DRIFT", "BUILD": "BUILD_DRIFT", "EYE_COLOR": "EYE_COLOR_DRIFT", "HAIR": "HAIR_DRIFT",
                  "DISTINCTIVE": "DISTINCTIVE_TRAIT_DRIFT", "SEX": "SEX_CANON_DRIFT"}
    for key, name in required:
        st = fields[key]["status"]
        if st in ("MATCH", "NOT_REQUIRED"):
            continue
        if st == "MISMATCH":
            if name == "EYE_COLOR" and lighting_confound:
                fields[key]["status"] = "AMBIGUOUS"
                reasons.append("EYE_COLOR_AMBIGUOUS_LIGHTING_CONFOUND")
                ambiguous.append(name)
            else:
                reasons.append(drift_name[name])
                confirmed.append(name)
        elif st == "AMBIGUOUS":
            reasons.append(f"{name}_AMBIGUOUS" + ("_LIGHTING_CONFOUND" if (lighting_confound and name == "EYE_COLOR") else ""))
            ambiguous.append(name)
        else:
            reasons.append(f"{name}_NOT_ASSESSABLE")
            ambiguous.append(name)
    unauthorized = list(obs.get("unauthorized_traits") or [])
    if unauthorized and not reasons:
        reasons.append("UNAUTHORIZED_IDENTITY_TRAIT")
        ambiguous.append("UNAUTHORIZED")
    if str(obs.get("cross_character_resemblance", "NONE") or "NONE").upper() != "NONE":
        reasons.append("CROSS_CHARACTER_SIMILARITY")
        confirmed.append("CROSS_CHARACTER")
    if reasons:
        tag = ("VIOLATION_CONFIRMED:" + ",".join(confirmed)) if confirmed else "AMBIGUOUS_NO_DEFINITE_VIOLATION"
        return IdentityVerification(contract.character_id, "REJECT_REVIEW", reasons + [tag], True,
                                    "HIGH" if confirmed else "LOW", checks, fields, method, lighting_confound, constraint)
    variance = list(obs.get("unspecified_variance") or [])
    if variance:
        return IdentityVerification(contract.character_id, "UNSPECIFIED_OK", [], False, "MED", checks, fields, method,
                                    lighting_confound, constraint)
    return IdentityVerification(contract.character_id, "PASS", [], False, "MED", checks, fields, method,
                                lighting_confound, constraint)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
REQUIRED_LOG_FIELDS: List[str] = [
    "RUN_ID", "TIMESTAMP", "NOVEL", "CHARACTER", "IDENTITY_CONTRACT_ID", "AUTHORITY_SOURCE",
    "TEXT_CANON_IDENTITY", "VISUAL_DIRECTION", "UNSPECIFIED_FIELDS", "FINAL_IDENTITY_CONSTRAINT",
    "MILESTONE_REF_PRESENT", "MILESTONE_CONDITIONING_USED", "AGE_EXPECTED", "AGE_OBSERVED",
    "FACE_MATCH", "HAIR_MATCH", "BUILD_MATCH", "EYE_COLOR_MATCH", "DISTINCTIVE_TRAITS_MATCH",
    "AUTOMATED_EVIDENCE_AVAILABLE", "HUMAN_REVIEW_REQUIRED", "VERIFIER_CONFIDENCE", "VERIFIER_DECISION",
    "FAIL_REASON", "AUTO_ACCEPT_ALLOWED", "FEATURE_FLAG_ENABLED",
    # plumbing fields
    "PATH_ID", "IMAGE_PATH", "IMAGE_SHA256", "QUARANTINE_PATH", "OBSERVATION_METHOD",
    "AUTOMATED_CHECKS", "PRODUCTION_DEFAULT", "SCOPE", "IMAGE_BYTES_MUTATED_BY_IDENTITY_SYSTEM",
    # coverage-remediation fields (IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929, Part L)
    "IDENTITY_CONTRACT_VERSION", "CHARACTER_BINDING_SOURCE", "STRUCTURED_CHARACTER_ID", "STRUCTURED_NOVEL_ID",
    "STRUCTURED_NOVEL_ALIAS", "PROMPT_FALLBACK_USED", "GOVERNED_CONTEXT_PRESENT",
    "GOVERNED_CONTEXT_BINDING_RESULT", "NO_GOVERNED_CHARACTER_REASON", "FALLBACK_IMAGE_USED",
    "FALLBACK_SOURCE", "FALLBACK_ASSET_CLASS", "FALLBACK_IMAGE_SHA256", "FALLBACK_IDENTITY_VERIFIED",
    "PRIOR_REVIEW_RECORD_USED", "PRIOR_REVIEW_RECORD_COMPATIBLE", "IDENTITY_GATE_EXECUTED",
    "IDENTITY_VERIFIER_DECISION", "CANON_DEPICTION_STATUS", "APPROVED_CHARACTER_PORTRAIT",
    "IDENTITY_LOCK_TEXT_SOURCE",
    # final-hardening fields (IDENTITY_FINAL_COVERAGE_HARDENING_20260930, Part L). IDENTITY_GATE_EXECUTED
    # (above) stays on every record; the 15 below are new.
    "IMAGE_INTENT_CLASS", "IMAGE_INTENT_SOURCE", "GOVERNED_CHARACTER_DEPICTION", "UPSTREAM_CHARACTER_ASSIGNED",
    "STRUCTURED_CHARACTER_VALID", "STRUCTURED_CHARACTER_CONFLICT", "MALFORMED_CHARACTER_ID",
    "BINDING_FAILURE_REASON", "SCENERY_BYPASS_APPLIED", "SCENERY_BYPASS_REASON", "IDENTITY_GATE_REQUIRED",
    "FALLBACK_ORIGINAL_INTENT_CLASS", "FALLBACK_INTENT_PRESERVED", "TIKTOK_REUSE_USED",
    "TIKTOK_REUSE_IDENTITY_VERIFIED",
]
# AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004 (Phase 9): on EVERY gate record (validated below;
# a missing field is an observability failure -> FAIL_CLOSED). Kept out of REQUIRED_LOG_FIELDS so
# the frozen coverage / final-hardening field tuples are unchanged.
DURABLE_PROVENANCE_LOG_FIELDS: Tuple[str, ...] = (
    "AIVSB_COMPOSED", "PROVENANCE_ID", "PROVENANCE_SCHEMA_VERSION", "PROVENANCE_SOURCE_RUN",
    "PROVENANCE_SOURCE_ASSET", "PROVENANCE_PRESENT", "PROVENANCE_INTEGRITY_VALID",
    "PROVENANCE_PROMPT_ASSOCIATION_VALID", "PROVENANCE_RECOVERED_FROM", "REGISTRY_AVAILABLE",
    "FORMAT_DETECTOR_RESULT", "PRE_AIVSB_CHARACTER_IDS", "PERSISTED_CHARACTER_IDS", "FINAL_GOVERNED_CONTEXT",
    "PROMPT_FORMAT_DRIFT_DETECTED", "PROVENANCE_MISMATCH_REASON", "PROVENANCE_REQUIRED", "PROVENANCE_STATUS",
    "PROVENANCE_EFFECT", "PROMPT_FORMAT_UNRECOGNISED", "FORMAT_DETECTOR_AUTHORITY",
)
COVERAGE_LOG_FIELDS: Tuple[str, ...] = tuple(REQUIRED_LOG_FIELDS[REQUIRED_LOG_FIELDS.index("IDENTITY_CONTRACT_VERSION"):
                                                                REQUIRED_LOG_FIELDS.index("IDENTITY_LOCK_TEXT_SOURCE") + 1])
FINAL_HARDENING_LOG_FIELDS: Tuple[str, ...] = tuple(REQUIRED_LOG_FIELDS[REQUIRED_LOG_FIELDS.index("IMAGE_INTENT_CLASS"):]) + (
    "IDENTITY_GATE_EXECUTED",)
_YES_NO = ("YES", "NO")
_ENUM_FIELDS: Dict[str, Tuple[str, ...]] = {
    "PROMPT_FALLBACK_USED": _YES_NO,
    "GOVERNED_CONTEXT_PRESENT": _YES_NO,
    "FALLBACK_IMAGE_USED": _YES_NO,
    "PRIOR_REVIEW_RECORD_USED": _YES_NO,
    "PRIOR_REVIEW_RECORD_COMPATIBLE": ("YES", "NO", "NOT_APPLICABLE"),
    "FALLBACK_IDENTITY_VERIFIED": ("YES", "NO", "NOT_APPLICABLE", "EXEMPT_NON_CANON"),
    "IDENTITY_GATE_EXECUTED": _YES_NO,
    "AUTO_ACCEPT_ALLOWED": _YES_NO,
    "HUMAN_REVIEW_REQUIRED": _YES_NO,
    "APPROVED_CHARACTER_PORTRAIT": _YES_NO,
    "GOVERNED_CHARACTER_DEPICTION": _YES_NO,
    "UPSTREAM_CHARACTER_ASSIGNED": _YES_NO,
    "STRUCTURED_CHARACTER_CONFLICT": _YES_NO,
    "MALFORMED_CHARACTER_ID": _YES_NO,
    "SCENERY_BYPASS_APPLIED": _YES_NO,
    "IDENTITY_GATE_REQUIRED": _YES_NO,
    "FALLBACK_INTENT_PRESERVED": ("YES", "NO", "NOT_APPLICABLE"),
    "TIKTOK_REUSE_USED": _YES_NO,
    "TIKTOK_REUSE_IDENTITY_VERIFIED": ("YES", "NO", "NOT_REQUIRED", "NOT_APPLICABLE"),
}


class IdentityObservabilityError(Exception):
    """Observability could not be completed (fail-closed)."""


def _now_pt_label() -> str:
    # Box / DavidsPC Automation tool convention: America/Phoenix wall clock (as wardrobe lane).
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S PT")


def validate_observability_record(record: Mapping[str, Any]) -> List[str]:
    """Missing required fields, plus (for coverage fields) invalid / inconsistent values."""
    problems = [k for k in REQUIRED_LOG_FIELDS if k not in record]
    problems += [k for k in DURABLE_PROVENANCE_LOG_FIELDS if k not in record]
    if problems:
        return problems
    if record.get("FORMAT_DETECTOR_AUTHORITY") != "ADVISORY_ONLY":
        problems.append("INVALID:FORMAT_DETECTOR_AUTHORITY")
    if record.get("AUTO_ACCEPT_ALLOWED") == "YES" and record.get("PROVENANCE_STATUS") in ("INVALID", "MISMATCH", "CONFLICT") \
            and record.get("VERIFIER_DECISION") != NON_CANON_DECISION:
        problems.append("INCONSISTENT:PROVENANCE_MISMATCH_BUT_ACCEPTED")
    for k, allowed in _ENUM_FIELDS.items():
        if str(record.get(k)) not in allowed:
            problems.append(f"INVALID:{k}={record.get(k)!r}")
    if str(record.get("CHARACTER_BINDING_SOURCE")) not in BINDING_SOURCES:
        problems.append(f"INVALID:CHARACTER_BINDING_SOURCE={record.get('CHARACTER_BINDING_SOURCE')!r}")
    if str(record.get("GOVERNED_CONTEXT_BINDING_RESULT")) not in BINDING_RESULTS:
        problems.append(f"INVALID:GOVERNED_CONTEXT_BINDING_RESULT={record.get('GOVERNED_CONTEXT_BINDING_RESULT')!r}")
    if str(record.get("CANON_DEPICTION_STATUS")) not in CANON_DEPICTION_STATUSES:
        problems.append(f"INVALID:CANON_DEPICTION_STATUS={record.get('CANON_DEPICTION_STATUS')!r}")
    fac = str(record.get("FALLBACK_ASSET_CLASS"))
    if record.get("FALLBACK_IMAGE_USED") == "YES":
        if fac not in FALLBACK_ASSET_CLASSES or not str(record.get("FALLBACK_SOURCE") or ""):
            problems.append("INCONSISTENT:FALLBACK_IMAGE_USED=YES_WITHOUT_SOURCE_OR_CLASS")
    elif fac != "NONE":
        problems.append(f"INCONSISTENT:FALLBACK_ASSET_CLASS={fac!r}_WITHOUT_FALLBACK")
    if record.get("VERIFIER_DECISION") == NOT_APPLICABLE_DECISION and not str(record.get("NO_GOVERNED_CHARACTER_REASON") or ""):
        problems.append("INCONSISTENT:NO_GOVERNED_CHARACTER_WITHOUT_REASON")
    if record.get("GOVERNED_CONTEXT_BINDING_RESULT") == "BOUND" and not str(record.get("CHARACTER") or ""):
        problems.append("INCONSISTENT:BOUND_WITHOUT_CHARACTER")
    if record.get("CHARACTER_BINDING_SOURCE") == "GOVERNED_CONTEXT_BINDING_FAILED" and record.get("AUTO_ACCEPT_ALLOWED") == "YES":
        problems.append("INCONSISTENT:BINDING_FAILED_BUT_ACCEPTED")
    problems.extend(_final_hardening_problems(record))
    return problems


def _final_hardening_problems(record: Mapping[str, Any]) -> List[str]:
    """IDENTITY_FINAL_COVERAGE_HARDENING_20260930 Part L value / consistency rules."""
    p: List[str] = []
    cls = str(record.get("IMAGE_INTENT_CLASS"))
    accepted = record.get("AUTO_ACCEPT_ALLOWED") == "YES"
    verdict = str(record.get("VERIFIER_DECISION"))
    if cls not in ALL_IMAGE_INTENT_CLASSES:
        p.append(f"INVALID:IMAGE_INTENT_CLASS={cls!r}")
    if str(record.get("IMAGE_INTENT_SOURCE")) not in IMAGE_INTENT_SOURCES:
        p.append(f"INVALID:IMAGE_INTENT_SOURCE={record.get('IMAGE_INTENT_SOURCE')!r}")
    if str(record.get("STRUCTURED_CHARACTER_VALID")) not in STRUCTURED_CHARACTER_STATUSES:
        p.append(f"INVALID:STRUCTURED_CHARACTER_VALID={record.get('STRUCTURED_CHARACTER_VALID')!r}")
    if (record.get("GOVERNED_CHARACTER_DEPICTION") == "YES") != (cls == INTENT_GOVERNED):
        p.append("INCONSISTENT:GOVERNED_CHARACTER_DEPICTION_VS_INTENT_CLASS")
    if record.get("SCENERY_BYPASS_APPLIED") == "YES":
        if (cls not in NON_DEPICTION_INTENT_CLASSES or record.get("GOVERNED_CHARACTER_DEPICTION") != "NO"
                or record.get("UPSTREAM_CHARACTER_ASSIGNED") != "NO" or record.get("IDENTITY_GATE_REQUIRED") != "NO"
                or record.get("MALFORMED_CHARACTER_ID") != "NO" or record.get("STRUCTURED_CHARACTER_CONFLICT") != "NO"
                or str(record.get("CHARACTER") or "") or str(record.get("BINDING_FAILURE_REASON") or "")
                or not str(record.get("SCENERY_BYPASS_REASON") or "")):
            p.append("INCONSISTENT:SCENERY_BYPASS_WITH_GOVERNED_OR_INVALID_EVIDENCE")
    elif str(record.get("SCENERY_BYPASS_REASON") or ""):
        p.append("INCONSISTENT:SCENERY_BYPASS_REASON_WITHOUT_BYPASS")
    if accepted and verdict not in ACCEPTING_DECISIONS and (
            record.get("GOVERNED_CHARACTER_DEPICTION") == "YES" or record.get("IDENTITY_GATE_REQUIRED") == "YES"):
        p.append("INCONSISTENT:GOVERNED_DEPICTION_ACCEPTED_WITHOUT_IDENTITY_VERIFICATION")
    if (record.get("MALFORMED_CHARACTER_ID") == "YES" or record.get("STRUCTURED_CHARACTER_CONFLICT") == "YES") and (
            accepted or verdict != "FAIL_CLOSED"):
        p.append("INCONSISTENT:MALFORMED_OR_CONFLICTING_STRUCTURED_CHARACTER_NOT_FAIL_CLOSED")
    if str(record.get("BINDING_FAILURE_REASON") or "") and accepted:
        p.append("INCONSISTENT:BINDING_FAILURE_BUT_ACCEPTED")
    orig = str(record.get("FALLBACK_ORIGINAL_INTENT_CLASS"))
    pres = str(record.get("FALLBACK_INTENT_PRESERVED"))
    if record.get("FALLBACK_IMAGE_USED") == "YES":
        if orig not in ALL_IMAGE_INTENT_CLASSES or pres not in _YES_NO:
            p.append("INCONSISTENT:FALLBACK_WITHOUT_ORIGINAL_INTENT")
        if orig == INTENT_GOVERNED and cls not in (INTENT_GOVERNED, "NON_CANON_SILHOUETTE"):
            p.append("INCONSISTENT:GOVERNED_FALLBACK_INTENT_DOWNGRADED")
        if pres == "NO" and accepted:
            p.append("INCONSISTENT:FALLBACK_INTENT_NOT_PRESERVED_BUT_ACCEPTED")
    elif orig != "NOT_APPLICABLE" or pres != "NOT_APPLICABLE":
        p.append("INCONSISTENT:FALLBACK_INTENT_FIELDS_WITHOUT_FALLBACK")
    if record.get("TIKTOK_REUSE_USED") == "YES":
        if record.get("FALLBACK_IMAGE_USED") != "YES" or record.get("TIKTOK_REUSE_IDENTITY_VERIFIED") == "NOT_APPLICABLE":
            p.append("INCONSISTENT:TIKTOK_REUSE_WITHOUT_FALLBACK_OR_VERIFICATION_STATUS")
        if accepted and record.get("TIKTOK_REUSE_IDENTITY_VERIFIED") == "NO":
            p.append("INCONSISTENT:TIKTOK_REUSE_UNVERIFIED_BUT_ACCEPTED")
    elif record.get("TIKTOK_REUSE_IDENTITY_VERIFIED") != "NOT_APPLICABLE":
        p.append("INCONSISTENT:TIKTOK_REUSE_VERIFIED_WITHOUT_REUSE")
    return p


def default_log_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    env = environ if environ is not None else os.environ
    override = str(env.get("IDENTITY_OBSERVABILITY_LOG", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "logs" / "identity_preservation" / "identity_observability.jsonl"


def write_observability(record: Mapping[str, Any], sidecar_path: Optional[Path], log_path: Path) -> None:
    missing = validate_observability_record(record)
    if missing:
        raise IdentityObservabilityError(f"incomplete identity observability record; missing={missing}")
    text = json.dumps(dict(record), ensure_ascii=False, default=str)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    if sidecar_path is not None:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(dict(record), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929 - fallback asset classes,
# prior identity-review records (Part I) and the Visual Director identity-only block (Part A)
# ---------------------------------------------------------------------------
FALLBACK_ASSET_CLASSES: Tuple[str, ...] = (
    "BANKED_GENERATED_IMAGE", "PREVIOUS_RUN_IMAGE", "DAILY_PROMO_IMAGE", "CHAPTER_PACK_IMAGE",
    "REUSABLE_PACK_IMAGE", "STOCK_IMAGE", "BROWSER_IMPORTED_IMAGE", "PROCEDURAL_EMERGENCY_ART",
    # IDENTITY_FINAL_COVERAGE_HARDENING_20260930 Part J: promo_builder.make_tiktok_pack asset-group reuse.
    "TIKTOK_ASSET_GROUP_IMAGE",
)
NON_CANON_DECISION = "NON_CANON_CHARACTER_DEPICTION"
CANON_DEPICTION_STATUSES: Tuple[str, ...] = (
    "CANONICAL_IDENTITY_GOVERNED", NON_CANON_DECISION, "NO_GOVERNED_CHARACTER", "UNVERIFIED_GOVERNED_DEPICTION",
)
PRIOR_REVIEW_RECORD_FIELDS: Tuple[str, ...] = (
    "IMAGE_SHA256", "CHARACTER_ID", "IDENTITY_CONTRACT_ID", "IDENTITY_CONTRACT_VERSION",
    "VERIFIER_DECISION", "HUMAN_REVIEW_STATUS", "TIMESTAMP",
)
PRIOR_REVIEW_APPROVED_STATUS = "APPROVED"
PRIOR_REVIEW_SIDECAR_SUFFIX = ".identity_review_record.json"
# IDENTITY_FINAL_COVERAGE_HARDENING_20260930 Part K: lightweight integrity hash. An UNKEYED sha256
# over the canonicalised bound fields: it detects accidental / naive mutation of a sidecar (a field
# edited without recomputing the hash), NOT a deliberate forger who recomputes it. No keys, no signing.
PRIOR_REVIEW_HASH_FIELDS: Tuple[str, ...] = (
    "IMAGE_SHA256", "CHARACTER_ID", "IDENTITY_CONTRACT_ID", "IDENTITY_CONTRACT_VERSION",
    "VERIFIER_DECISION", "HUMAN_REVIEW_STATUS", "TIMESTAMP", "REVIEWER",
)


def prior_review_record_hash(record: Mapping[str, Any]) -> str:
    canon = {k: str(record.get(k, "") or "").strip() for k in PRIOR_REVIEW_HASH_FIELDS}
    canon["IMAGE_SHA256"] = canon["IMAGE_SHA256"].lower()
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prior_review_sidecar_path(image_path: Any) -> Path:
    p = Path(str(image_path))
    return p.with_name(p.name + PRIOR_REVIEW_SIDECAR_SUFFIX)


def build_prior_review_record(*, image_sha256: str, character_id: str, verifier_decision: str,
                              human_review_status: str, timestamp: str = "",
                              reviewer: str = "") -> Dict[str, Any]:
    c = get_identity_contract(character_id)
    rec = {
        "IMAGE_SHA256": str(image_sha256 or "").lower(),
        "CHARACTER_ID": c.character_id if c else str(character_id or ""),
        "IDENTITY_CONTRACT_ID": c.contract_id if c else "",
        "IDENTITY_CONTRACT_VERSION": identity_contract_version(c),
        "VERIFIER_DECISION": str(verifier_decision or ""),
        "HUMAN_REVIEW_STATUS": str(human_review_status or ""),
        "TIMESTAMP": timestamp or _now_pt_label(),
        "REVIEWER": str(reviewer or ""),
    }
    rec["PRIOR_REVIEW_RECORD_HASH"] = prior_review_record_hash(rec)
    return rec


def load_prior_review_records(value: Any = None, image_path: Any = None) -> List[Dict[str, Any]]:
    """Explicit record(s) (mapping / list) or the sidecar next to the image."""
    if value is None and image_path:
        side = prior_review_sidecar_path(image_path)
        if side.exists():
            try:
                value = json.loads(side.read_text(encoding="utf-8"))
            except Exception:
                return [{"__invalid__": f"UNREADABLE_PRIOR_REVIEW_RECORD:{side.name}"}]
    if value is None:
        return []
    if isinstance(value, Mapping):
        if "records" in value and isinstance(value.get("records"), list):
            return [dict(r) for r in value["records"] if isinstance(r, Mapping)]
        return [dict(value)]
    if isinstance(value, (list, tuple)):
        return [dict(r) for r in value if isinstance(r, Mapping)]
    return [{"__invalid__": "UNSUPPORTED_PRIOR_REVIEW_RECORD_TYPE"}]


def prior_review_record_compatibility(record: Optional[Mapping[str, Any]], *, image_sha256: str,
                                      character_id: str) -> Tuple[bool, str]:
    """Part I: a prior review may be reused only if bytes, character, contract id and
    contract version all match and the review was an accepting, human-APPROVED decision."""
    if not record:
        return False, "PRIOR_REVIEW_RECORD_MISSING"
    if "__invalid__" in record:
        return False, str(record["__invalid__"])
    missing = [f for f in PRIOR_REVIEW_RECORD_FIELDS if not str(record.get(f, "") or "").strip()]
    if missing:
        return False, "PRIOR_REVIEW_RECORD_FIELDS_MISSING:" + ",".join(missing)
    contract = get_identity_contract(character_id)
    if contract is None:
        return False, "NO_GOVERNED_CONTRACT"
    if not image_sha256 or str(record["IMAGE_SHA256"]).strip().lower() != image_sha256.lower():
        return False, "IMAGE_SHA256_MISMATCH_REVERIFY"
    if normalize_identity_character_key(record["CHARACTER_ID"]) != contract.character_id:
        return False, "CHARACTER_MISMATCH_REVERIFY"
    if str(record["IDENTITY_CONTRACT_ID"]).strip() != contract.contract_id:
        return False, "IDENTITY_CONTRACT_ID_MISMATCH_REVERIFY"
    if str(record["IDENTITY_CONTRACT_VERSION"]).strip() != identity_contract_version(contract):
        return False, "IDENTITY_CONTRACT_VERSION_MISMATCH_REVERIFY"
    if str(record["VERIFIER_DECISION"]).strip().upper() not in ACCEPTING_DECISIONS:
        return False, "PRIOR_VERIFIER_DECISION_NOT_ACCEPTING"
    if str(record["HUMAN_REVIEW_STATUS"]).strip().upper() != PRIOR_REVIEW_APPROVED_STATUS:
        return False, "PRIOR_HUMAN_REVIEW_NOT_APPROVED"
    # Part K (checked last so the specific field reasons above stay reported first).
    stored = str(record.get("PRIOR_REVIEW_RECORD_HASH", "") or "").strip().lower()
    if not stored:
        return False, "PRIOR_REVIEW_RECORD_HASH_MISSING_REVERIFY"
    if stored != prior_review_record_hash(record):
        return False, "PRIOR_REVIEW_RECORD_HASH_MISMATCH_REVERIFY"
    return True, "COMPATIBLE"


def _best_prior_record(records: Sequence[Mapping[str, Any]], *, image_sha256: str,
                       character_id: str) -> Tuple[Optional[Mapping[str, Any]], bool, str]:
    if not records:
        return None, False, "PRIOR_REVIEW_RECORD_MISSING"
    first_reason = ""
    for r in records:
        ok, why = prior_review_record_compatibility(r, image_sha256=image_sha256, character_id=character_id)
        if ok:
            return r, True, why
        first_reason = first_reason or why
    return records[0], False, first_reason


def visual_director_identity_bits(contract: Optional[IdentityContract]) -> List[str]:
    """Part A: identity-only 'Label: value' bits for the VD Character Identity block under
    ENABLE_IDENTITY_PRESERVATION=ON (age, sex only where TEXT_CANON, build, height direction,
    hair canon, eye canon, face continuity direction). No wardrobe / weapons / effects / env."""
    if contract is None:
        return []
    bits: List[str] = []
    sex = contract_sex_for_record(contract.character_id)
    if sex:
        bits.append(f"Gender: {sex}")
    bits.append(f"Age: {contract.vd_age}")
    for tok in contract.lock_tokens:
        t = tok.lower()
        if t.startswith("age ") or t in ("male", "female") or t == contract.vd_age.lower():
            continue
        if "build" in t:
            bits.append(f"Build: {tok}")
        elif "height" in t:
            bits.append(f"Height: {tok}")
        elif "hair" in t:
            bits.append(f"Hair: {tok}")
        elif "eye" in t:
            bits.append(f"Eyes: {tok}")
    bits.append("Face: same recognizable face in every shot (continuity direction only)")
    return [b for b in bits if not identity_lock_denylist_hits(b)]


# ---------------------------------------------------------------------------
# Acceptance gate (production boundary): generation -> verify -> decision -> persistence
# ---------------------------------------------------------------------------
class IdentityAcceptanceBlocked(RuntimeError):
    """Raised by production callers when the identity decision forbids auto-accept."""

    def __init__(self, message: str, result: "IdentityGateResult"):
        super().__init__(message)
        self.result = result


@dataclass
class IdentityGateResult:
    feature_flag_enabled: str
    decision: str
    auto_accept_allowed: bool
    human_review_required: bool
    fail_reason: str
    path_id: str
    image_path: str = ""
    quarantine_path: str = ""
    records: List[Dict[str, Any]] = field(default_factory=list)
    image_bytes_mutated: str = "NO"

    @property
    def accepted(self) -> bool:
        return self.auto_accept_allowed

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


_DECISION_RANK = {"PASS": 0, NOT_APPLICABLE_DECISION: 0, "UNSPECIFIED_OK": 1, "REJECT_REVIEW": 2, "FAIL_CLOSED": 3}


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quarantine_path_for(image_path: Path) -> Path:
    """Sibling review path; never overwrites an earlier quarantined candidate."""
    q = image_path.with_name(f"{image_path.stem}.identity-review{image_path.suffix}")
    n = 2
    while q.exists():
        q = image_path.with_name(f"{image_path.stem}.identity-review.{n}{image_path.suffix}")
        n += 1
    return q


_QUARANTINE_TAG_RE = re.compile(r"\.identity-review(\.\d+)?(?=\.[^.]*$|$)")


def _obs_for(observations: Any, character_key: str) -> Optional[Mapping[str, Any]]:
    if not observations:
        return None
    if isinstance(observations, Mapping) and character_key in observations and isinstance(observations[character_key], Mapping):
        return observations[character_key]
    if isinstance(observations, Mapping) and ("method" in observations or "face_readable" in observations):
        return observations
    return None


def run_identity_acceptance_gate(
    image_path: Any,
    *,
    path_id: str,
    spec: Any = None,
    prompt: str = "",
    novel: str = "",
    character_id: str = "",
    milestone_conditioning_used: bool = False,
    observations: Any = None,
    environ: Optional[Mapping[str, str]] = None,
    writer: Optional[Callable[[Mapping[str, Any], Optional[Path], Path], Any]] = None,
    log_path: Optional[Path] = None,
    quarantine: bool = True,
    run_id: Optional[str] = None,
    identity_context: Optional[IdentityProductionContext] = None,
    use_ambient_context: bool = True,
    fallback: Optional[Mapping[str, Any]] = None,
    prior_review_record: Any = None,
    write_sidecar: bool = True,
    image_intent: Any = None,
    prompt_provenance: Any = None,
) -> IdentityGateResult:
    """Identity acceptance boundary. Flag OFF -> BYPASS with zero side effects.

    Flag ON: binds governed contracts by structured context first (spec.identity, explicit
    character_id / novel, ambient IdentityProductionContext), prompt parsing only for truly
    contextless legacy calls (see resolve_governed_binding); verifies (auditing the emitted
    Visual Director identity block when present); applies the governed fallback policy for
    reused / stock / imported / procedural candidates; emits an observability record
    (failure -> FAIL_CLOSED) and, when auto-accept is not allowed and ``quarantine`` is set,
    moves the image to a sibling ``*.identity-review.<ext>`` path (bytes unchanged).
    """
    env = environ if environ is not None else os.environ
    img = Path(str(image_path)) if image_path else None
    if not is_identity_preservation_enabled(env):
        return IdentityGateResult("NO", "BYPASS", True, False, "FEATURE_FLAG_OFF", path_id, str(img or ""))
    rid = run_id or f"IDENTITY_{uuid.uuid4().hex[:12]}"
    wr = writer or write_observability
    lp = log_path or default_log_path(env)
    records: List[Dict[str, Any]] = []
    decision = "FAIL_CLOSED"
    reasons: List[str] = []
    image_sha = ""
    fb = dict(fallback) if fallback else None
    ctx = merge_identity_context(current_identity_context() if use_ambient_context else None, identity_context)
    binding: Optional[BindingResolution] = None
    intent: Optional[ImageIntent] = None
    orig_intent_class = "NOT_APPLICABLE"
    bypass_reason = ""
    pa = None  # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: durable prompt provenance assessment
    aivsb_ev: Optional[AivsbComposedEvidence] = None
    prov_force: Optional[Tuple[str, Tuple[str, ...]]] = None
    prov_effect = "NONE"
    try:
        if img is not None and img.exists():
            image_sha = _sha256_file(img)
        if fb is not None:
            if fb.get("asset_class") not in FALLBACK_ASSET_CLASSES:
                raise ValueError(f"unknown fallback asset class {fb.get('asset_class')!r}")
            if img is None or not img.exists():
                raise FileNotFoundError(f"fallback candidate missing: {img}")
        # IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Part C): structured intent evidence =
        # ambient upstream scope < Visual Director prompt registry < explicit argument.
        intent_req = _merge_intent_requests(
            current_image_intent() if use_ambient_context else None,
            lookup_prompt_image_intent(prompt),
            coerce_image_intent_request(image_intent),
        )
        subj_claims = ()
        if intent_req is not None and _vocab_key(intent_req.scene_subject) and \
                _vocab_key(intent_req.scene_subject) not in SCENE_SUBJECT_CLASSES:
            subj_claims = (intent_req.scene_subject,)  # a character claim: validated like a character id
        binding = resolve_governed_binding(
            spec=spec, prompt=prompt, novel=novel, character_id=character_id, context=ctx,
            depicted_characters=tuple(intent_req.depicted_characters if intent_req is not None else ()) + subj_claims)
        request_novel = binding.request_novel
        if not request_novel and novel:
            try:
                from tools.studio_bible_adapter import normalize_novel_id
                request_novel = normalize_novel_id(novel, empty_ok=True)
            except Exception:
                request_novel = str(novel).strip().casefold()
        style_refs_present = bool(tuple(getattr(getattr(spec, "references", None), "style_refs", ()) or ())) if spec is not None else False
        mc_used = bool(milestone_conditioning_used or style_refs_present)
        emitted_block = extract_emitted_identity_block(prompt) if spec is None else ""
        block_key = emitted_block_character(emitted_block) if emitted_block else None
        procedural = fb is not None and fb.get("asset_class") == "PROCEDURAL_EMERGENCY_ART"
        _scene_text = intent_req.scene_text if intent_req is not None else ""
        # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: durable structured provenance (persisted with the
        # prompt / image, associated by prompt hash / asset id / image sha) decides AIVSB governance;
        # the format detector is advisory only. See DECISION_TABLE.md.
        from tools import aivsb_prompt_provenance as _prov
        pa = _prov.assess(
            prompt=str(prompt or ""), scene_text=str(_scene_text or ""), image_path=img, image_sha256=image_sha,
            is_fallback=fb is not None, explicit=prompt_provenance,
            aivsb_env_enabled=_aivsb_reasoning_enabled(env), request_novel=str(request_novel or ""),
            structured_keys=tuple(binding.structured_governed_keys),
            ctx_contract_id=str(getattr(ctx, "identity_contract_id", "") or ""))
        # AIVSB_IDENTITY_PATH_REMEDIATION_20261004: in-process registry evidence (upgrade-only).
        aivsb_ev = lookup_aivsb_composed_evidence(prompt, _scene_text)
        if aivsb_ev is not None and aivsb_ev.matched_by == "SIGNATURE" and pa.status == "VALID" and not pa.aivsb_composed:
            aivsb_ev = None  # valid durable provenance (aivsb_composed=false) outranks the advisory detector
        if procedural:
            prov_effect = "PROCEDURAL_NON_CANON_UNCHANGED"
        elif pa.status in ("INVALID", "MISMATCH", "CONFLICT"):
            prov_effect = f"FAIL_CLOSED:AIVSB_PROVENANCE_{pa.status}"
            if binding.result != "FAILED":
                binding = _provenance_failed_binding(binding, f"AIVSB_PROVENANCE_{pa.status}:{pa.mismatch_reason}")
        elif pa.status == "VALID":
            if (len(pa.novel_ids) == 1 and not request_novel and not binding.keys and binding.result == "NO_GOVERNED_CONTEXT"
                    and str(binding.no_governed_reason or "").startswith("NO_STRUCTURED_CONTEXT")):
                # Contextless reuse of a persisted prompt: the provenance's canonical novel is the
                # structured context the original request had (never weaker than the original).
                ctx = merge_identity_context(ctx, build_identity_context(novel=pa.novel_ids[0], source="AIVSB_PROMPT_PROVENANCE"))
                binding = resolve_governed_binding(
                    spec=spec, prompt=prompt, novel=novel, character_id=character_id, context=ctx,
                    depicted_characters=tuple(intent_req.depicted_characters if intent_req is not None else ()) + subj_claims)
                request_novel = binding.request_novel or request_novel
                prov_effect = "REBOUND_FROM_PROVENANCE_NOVEL"
            names = tuple(pa.depicted_character_ids)
            if pa.aivsb_composed:
                prov_force = ("AIVSB_PROVENANCE_COMPOSED_POTENTIALLY_GOVERNED", names)
            elif pa.character_ids and not binding.keys:
                prov_force = ("AIVSB_PROVENANCE_GOVERNED_CONTEXT_UNBOUND", names)
            elif names:
                prov_force = ("AIVSB_PROVENANCE_PRE_AIVSB_GOVERNED_NAME", names)
            if prov_force is not None:
                prov_effect = (prov_effect + ";" if prov_effect != "NONE" else "") + "FORCE:" + prov_force[0]
            elif prov_effect == "NONE":
                prov_effect = "VALID_NON_AIVSB_PRIOR_RULES"
        elif pa.required:
            exempt = ""
            if lookup_prompt_image_intent(prompt) is not None:
                exempt = "VISUAL_DIRECTOR_REGISTRY_INTENT_NON_AIVSB_SOURCE"
            elif (not binding.keys and not binding.governed_context_present and binding.result != "FAILED"
                  and str(binding.no_governed_reason or "").startswith(
                      ("STRUCTURED_NOVEL_NOT_GOVERNED", "STRUCTURED_NOVEL_UNRESOLVED",
                       "STRUCTURED_CHARACTER_OUTSIDE_GOVERNED_SCOPE"))
                  and pa.detector == "NO_MATCH"):
                exempt = "OUT_OF_GOVERNED_SCOPE_STRUCTURED_CONTEXT"
            elif (not str(prompt or "").strip() and not str(_scene_text or "").strip() and intent_req is None
                  and binding.result == "NO_GOVERNED_CONTEXT" and not binding.governed_context_present
                  and pa.image_binding == "ABSENT" and _prov.current_scope() is None):
                exempt = "NO_PROMPT_NO_CONTEXT_INHERITED_CONTRACT"
            # (No contextless exemption: with AIVSB enabled, a contextless prompt without provenance may be a
            # persisted AIVSB composition whose wording drifted; the advisory detector's non-match must not
            # decide that, so it stays POTENTIALLY_GOVERNED -> review.)
            if exempt:
                prov_effect = "ABSENT_EXEMPT:" + exempt
            else:
                # Phase 4: absence != non-AIVSB. Missing provenance in a provenance-required context is
                # POTENTIALLY_GOVERNED (review); never inferred SCENERY_ONLY from labels or wording.
                prov_force = ("AIVSB_PROVENANCE_ABSENT_POTENTIALLY_GOVERNED", ())
                prov_effect = "FORCE:" + prov_force[0]
        else:
            prov_effect = "NOT_REQUIRED_PRIOR_RULES"
        intent = resolve_image_intent(intent_req, binding=binding, prompt=prompt, spec=spec,
                                      emitted_block_key=block_key, aivsb_evidence=aivsb_ev,
                                      provenance_force=prov_force)
        if fb is not None:
            # Part I: the ORIGINAL request intent is preserved; the reused asset's own sha-bound record
            # can only make evaluation stricter (unknown content in a non-depiction slot -> governed).
            orig_intent_class = intent.intent_class
            if procedural:
                intent = resolve_image_intent(intent_req, binding=binding, prompt=prompt, spec=spec,
                                              emitted_block_key=block_key, procedural=True,
                                              aivsb_evidence=aivsb_ev, provenance_force=prov_force)
            elif intent.intent_class in NON_DEPICTION_INTENT_CLASSES + ("NON_GOVERNED_CHARACTER_DEPICTION",):
                rg, why = reused_asset_recorded_governed(img, image_sha)
                intent = resolve_image_intent(intent_req, binding=binding, prompt=prompt, spec=spec,
                                              emitted_block_key=block_key,
                                              reused_asset_governed=(True if rg is None else rg),
                                              aivsb_evidence=aivsb_ev, provenance_force=prov_force)
                intent.evidence.append(f"REUSED_ASSET:{why}")
            elif (intent.source == "SAFE_DEFAULT_NO_STRUCTURED_INTENT" and not intent.forced
                  and not binding.fail_reason and binding.result != "FAILED"):
                # No structured intent on the reuse request (e.g. TikTok pack reuse): the ORIGINAL intent
                # is the reused asset's own sha-bound structured record, if (and only if) it is an intact
                # structured non-depiction record for exactly these bytes. Otherwise the safe default
                # (potentially governed) stays.
                rg, why = reused_asset_recorded_governed(img, image_sha)
                rec_cls = why.split(":", 1)[1] if (rg is False and ":" in why) else ""
                if rec_cls in NON_DEPICTION_INTENT_CLASSES:
                    intent = ImageIntent(rec_cls, "REUSED_ASSET_SHA_BOUND_RECORD", False, False,
                                         intent.evidence + [f"REUSED_ASSET:{why}"],
                                         intent.origin, intent.request, False)
                    orig_intent_class = rec_cls
                else:
                    intent.evidence.append(f"REUSED_ASSET:{why}")
        scenery_bypass = (not procedural and binding.result != "FAILED" and not binding.fail_reason
                          and intent.intent_class in NON_DEPICTION_INTENT_CLASSES and not intent.governed_depiction
                          and not intent.upstream_character_assigned)
        non_governed_subject = (not procedural and binding.result != "FAILED" and not binding.fail_reason
                                and intent.intent_class == "NON_GOVERNED_CHARACTER_DEPICTION")
        if scenery_bypass:
            bypass_reason = f"SCENERY_BYPASS:{intent.intent_class}:{intent.source}"
        if procedural:
            decision = NON_CANON_DECISION
            # Record the governed SLOT (if any) so downstream sees "Jarek slot, non-canon art",
            # never an approved portrait (APPROVED_CHARACTER_PORTRAIT=NO).
            slot = binding.keys[0] if binding.keys else None
            rec = _record(rid, path_id, GOVERNED_IDENTITY_CONTRACTS[slot] if slot else None, None, decision, [], True,
                          img, image_sha, request_novel, mc_used)
            _augment(rec, binding=binding, key=slot, fb=fb, fb_verified="EXEMPT_NON_CANON",
                     canon_status=NON_CANON_DECISION)
            records.append(rec)
        elif binding.result == "FAILED":
            decision = "FAIL_CLOSED"
            reasons.append(binding.fail_reason)
            rec = _record(rid, path_id, None, None, decision, [binding.fail_reason], False, img, image_sha,
                          request_novel, mc_used)
            _augment(rec, binding=binding, key=None, fb=fb, fb_verified="NO" if fb else "NOT_APPLICABLE",
                     canon_status="UNVERIFIED_GOVERNED_DEPICTION")
            records.append(rec)
        elif scenery_bypass or non_governed_subject:
            # Part D: structured non-depiction intent (or a structured NON-governed character subject)
            # with no governed character assigned / named / emitted -> identity visual verification
            # NOT required. Novel membership alone never binds a governed contract here.
            decision = NOT_APPLICABLE_DECISION
            rec = _record(rid, path_id, None, None, decision, [], True, img, image_sha, request_novel, mc_used)
            _augment(rec, binding=binding, key=None, fb=fb, fb_verified="NOT_APPLICABLE",
                     canon_status="NO_GOVERNED_CHARACTER")
            rec["CHARACTER_BINDING_SOURCE"] = "NONE"
            rec["PROMPT_FALLBACK_USED"] = "NO"
            if scenery_bypass:
                rec["GOVERNED_CONTEXT_BINDING_RESULT"] = "NOT_REQUIRED_NON_DEPICTION_INTENT"
                rec["NO_GOVERNED_CHARACTER_REASON"] = bypass_reason
            else:
                rec["GOVERNED_CONTEXT_BINDING_RESULT"] = "OUTSIDE_GOVERNED_SCOPE"
                rec["NO_GOVERNED_CHARACTER_REASON"] = (binding.no_governed_reason or
                                                       "STRUCTURED_NON_GOVERNED_CHARACTER_SUBJECT:" +
                                                       ",".join(binding.structured_nongoverned_cast))
            records.append(rec)
        elif intent.governed_depiction and not binding.keys:
            # Governed depiction evidence without a bindable governed contract -> review (never accept).
            decision = "REJECT_REVIEW"
            why = "GOVERNED_DEPICTION_WITHOUT_BOUND_CONTRACT_REVIEW_REQUIRED"
            reasons.append(why)
            rec = _record(rid, path_id, None, None, decision, [why], False, img, image_sha, request_novel, mc_used)
            _augment(rec, binding=binding, key=None, fb=fb, fb_verified="NO" if fb else "NOT_APPLICABLE",
                     canon_status="UNVERIFIED_GOVERNED_DEPICTION")
            records.append(rec)
        elif not binding.keys:
            decision = NOT_APPLICABLE_DECISION
            rec = _record(rid, path_id, None, None, decision, [], True, img, image_sha, request_novel, mc_used)
            _augment(rec, binding=binding, key=None, fb=fb, fb_verified="NOT_APPLICABLE",
                     canon_status="NO_GOVERNED_CHARACTER")
            records.append(rec)
        else:
            worst = "PASS"
            prior_list = load_prior_review_records(prior_review_record, img) if fb is not None else []
            spec_cid = str(getattr(getattr(spec, "identity", None), "character_id", "") or "") if spec is not None else ""
            for k in binding.keys:
                contract = GOVERNED_IDENTITY_CONTRACTS[k]
                primary = (k == binding.keys[0])
                lock_text = emitted_block if (emitted_block and block_key == k) else None
                ver = verify_identity(
                    contract,
                    spec=spec if (spec is not None and primary) else None,
                    request_character_id=(character_id or spec_cid or k) if primary else k,
                    request_novel_id=request_novel if primary else "",
                    identity_lock_text=lock_text,
                    milestone_conditioning_used=mc_used,
                    observations=_obs_for(observations, k),
                    image_sha256=image_sha,
                )
                k_decision = ver.decision
                k_reasons = list(ver.fail_reasons)
                prior_used, prior_compat = "NO", "NOT_APPLICABLE"
                fb_verified = "NOT_APPLICABLE"
                if fb is not None:
                    rec_p, ok, why = _best_prior_record(prior_list, image_sha256=image_sha, character_id=k)
                    if rec_p is not None:
                        prior_used = "YES"
                        prior_compat = "YES" if ok else "NO"
                    if ok and k_decision == "REJECT_REVIEW" and set(k_reasons) <= {
                            "HUMAN_REVIEW_OBSERVATIONS_ABSENT", "NO_QUALIFIED_AUTOMATED_FACE_IDENTITY_MODEL"}:
                        k_decision = str(rec_p.get("VERIFIER_DECISION")).strip().upper()
                        k_reasons = []
                    elif not ok:
                        k_reasons.append(f"PRIOR_REVIEW:{why}")
                        if fb.get("asset_class") == "STOCK_IMAGE" and k_decision not in ACCEPTING_DECISIONS:
                            k_reasons.append("STOCK_IN_GOVERNED_SLOT_NOT_CANONICAL_WITHOUT_IDENTITY_REVIEW")
                    fb_verified = "YES" if k_decision in ACCEPTING_DECISIONS else "NO"
                if _DECISION_RANK.get(k_decision, 3) > _DECISION_RANK.get(worst, 3):
                    worst = k_decision
                reasons.extend(f"{k}:{r}" for r in k_reasons)
                rec = _record(rid, path_id, contract, ver, k_decision, k_reasons, k_decision in ACCEPTING_DECISIONS,
                              img, image_sha, request_novel, mc_used)
                rec["BINDING_METHOD"] = _LEGACY_BINDING_METHOD.get(binding.sources.get(k, ""), "UNKNOWN")
                _augment(rec, binding=binding, key=k, fb=fb, fb_verified=fb_verified, prior_used=prior_used,
                         prior_compat=prior_compat,
                         canon_status=("CANONICAL_IDENTITY_GOVERNED" if k_decision in ACCEPTING_DECISIONS
                                       else "UNVERIFIED_GOVERNED_DEPICTION"),
                         lock_source=("EMITTED_PROMPT_IDENTITY_BLOCK" if lock_text is not None else
                                      "SPEC_FOCAL_POINT" if (spec is not None and primary) else "CONTRACT_PHRASE"))
                records.append(rec)
            decision = worst
            if binding.fail_reason:
                decision = "FAIL_CLOSED"
                reasons.append(binding.fail_reason)
                for r in records:
                    r["FAIL_REASON"] = sorted(set((r.get("FAIL_REASON") or []) + [binding.fail_reason]))
                    r["GOVERNED_CONTEXT_BINDING_RESULT"] = "FAILED"
    except Exception as exc:  # noqa: BLE001 - any verifier error fails closed
        decision = "FAIL_CLOSED"
        reasons.append(f"IDENTITY_GATE_ERROR:{type(exc).__name__}:{exc}")
        rec = _record(rid, path_id, None, None, decision, reasons, False, img, image_sha, "", bool(milestone_conditioning_used))
        _augment(rec, binding=binding, key=None, fb=fb, fb_verified="NO" if fb else "NOT_APPLICABLE",
                 canon_status="UNVERIFIED_GOVERNED_DEPICTION", error=True)
        records.append(rec)

    for r in records:
        _augment_intent(r, intent=intent, binding=binding, fb=fb, orig_intent_class=orig_intent_class,
                        bypass_reason=bypass_reason)
        _augment_provenance(r, pa=pa, aivsb_ev=aivsb_ev, prov_effect=prov_effect, prompt=prompt)
    accepted = decision in ACCEPTING_DECISIONS or decision in (NOT_APPLICABLE_DECISION, NON_CANON_DECISION)
    qpath: Optional[Path] = None
    if not accepted and quarantine and img is not None and img.exists():
        try:
            qpath = quarantine_path_for(img)
            os.replace(str(img), str(qpath))
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"QUARANTINE_MOVE_FAILED:{exc}")
            qpath = None
    for r in records:
        r["QUARANTINE_PATH"] = str(qpath) if qpath else ""
        if not accepted:
            r["AUTO_ACCEPT_ALLOWED"] = "NO"
            r["HUMAN_REVIEW_REQUIRED"] = "YES"
            r["APPROVED_CHARACTER_PORTRAIT"] = "NO"
            if decision == "FAIL_CLOSED" and r["VERIFIER_DECISION"] != "FAIL_CLOSED" and reasons:
                r["FAIL_REASON"] = sorted(set((r.get("FAIL_REASON") or []) + reasons))
            if r.get("TIKTOK_REUSE_USED") == "YES" and r.get("TIKTOK_REUSE_IDENTITY_VERIFIED") != "NOT_REQUIRED":
                r["TIKTOK_REUSE_IDENTITY_VERIFIED"] = "NO"
        r["IMAGE_INTENT_RECORD_HASH"] = _intent_record_hash(r)
    # Emit (fail closed on any logger failure). IDENTITY_FINAL_COVERAGE_HARDENING_20260930: this also
    # blocks scenery-bypass / NO_GOVERNED_CHARACTER acceptance (an unauditable decision is never accepted).
    try:
        sidecar_base = qpath or img
        for i, r in enumerate(records):
            sidecar = None
            if sidecar_base is not None and (write_sidecar or qpath is not None):
                suffix = f".identity_preservation{'' if i == 0 else '.' + str(i)}.json"
                sidecar = sidecar_base.with_name(sidecar_base.name + suffix)
            wr(r, sidecar, lp)
    except Exception as exc:  # noqa: BLE001
        reason = f"OBSERVABILITY_LOG_FAILURE:{type(exc).__name__}:{exc}"
        reasons.append(reason)
        decision = "FAIL_CLOSED"
        if accepted and quarantine and img is not None and img.exists():
            try:
                qpath = quarantine_path_for(img)
                os.replace(str(img), str(qpath))
            except Exception:
                qpath = None
        accepted = False
        for r in records:
            r["VERIFIER_DECISION"] = "FAIL_CLOSED"
            r["IDENTITY_VERIFIER_DECISION"] = "FAIL_CLOSED"
            r["AUTO_ACCEPT_ALLOWED"] = "NO"
            r["HUMAN_REVIEW_REQUIRED"] = "YES"
            r["APPROVED_CHARACTER_PORTRAIT"] = "NO"
            r["FAIL_REASON"] = sorted(set((r.get("FAIL_REASON") or []) + [reason]))
            r["QUARANTINE_PATH"] = str(qpath) if qpath else ""
            if r.get("TIKTOK_REUSE_USED") == "YES":
                r["TIKTOK_REUSE_IDENTITY_VERIFIED"] = "NO"
            if r.get("SCENERY_BYPASS_APPLIED") == "YES":
                r["SCENERY_BYPASS_APPLIED"] = "NO"
                r["SCENERY_BYPASS_REASON"] = ""
                r["SCENERY_BYPASS_BLOCKED_BY"] = "OBSERVABILITY_LOG_FAILURE"
    return IdentityGateResult(
        feature_flag_enabled="YES",
        decision=decision,
        auto_accept_allowed=accepted,
        human_review_required=not accepted,
        fail_reason=";".join(reasons),
        path_id=path_id,
        image_path=str(img or ""),
        quarantine_path=str(qpath) if qpath else "",
        records=records,
    )


def _augment(rec: Dict[str, Any], *, binding: Optional[BindingResolution], key: Optional[str],
             fb: Optional[Mapping[str, Any]], fb_verified: str, prior_used: str = "NO",
             prior_compat: str = "NOT_APPLICABLE", canon_status: str = "", lock_source: str = "",
             error: bool = False) -> None:
    """Part L coverage fields on EVERY record (bound, NO_GOVERNED_CHARACTER, fail-closed, error)."""
    b = binding
    if key is not None and b is not None:
        src = b.sources.get(key, "NONE")
    elif b is not None and b.result == "FAILED":
        src = "GOVERNED_CONTEXT_BINDING_FAILED"
    else:
        src = "NONE"
    if error:
        result = "ERROR"
    elif b is None:
        result = "ERROR"
    else:
        result = b.result
    contract = GOVERNED_IDENTITY_CONTRACTS.get(key) if key else None
    accepted = rec.get("AUTO_ACCEPT_ALLOWED") == "YES"
    rec.update({
        "IDENTITY_CONTRACT_VERSION": identity_contract_version(contract),
        "CHARACTER_BINDING_SOURCE": src,
        "STRUCTURED_CHARACTER_ID": (b.structured_character_id if b else ""),
        "STRUCTURED_NOVEL_ID": (b.structured_novel_id if b else ""),
        "STRUCTURED_NOVEL_ALIAS": (b.structured_novel_alias if b else ""),
        "PROMPT_FALLBACK_USED": "YES" if (b is not None and key is not None and src in ("PROMPT_GOVERNED_NAME", "PROMPT_NOVEL_TITLE")) else "NO",
        "GOVERNED_CONTEXT_PRESENT": "YES" if (b is not None and b.governed_context_present) else "NO",
        "GOVERNED_CONTEXT_BINDING_RESULT": result,
        "NO_GOVERNED_CHARACTER_REASON": ((b.no_governed_reason if b is not None else "")
                                         if rec.get("VERIFIER_DECISION") == NOT_APPLICABLE_DECISION else ""),
        "FALLBACK_IMAGE_USED": "YES" if fb is not None else "NO",
        "FALLBACK_SOURCE": str(fb.get("source", "")) if fb is not None else "",
        "FALLBACK_ASSET_CLASS": str(fb.get("asset_class", "")) if fb is not None else "NONE",
        "FALLBACK_IMAGE_SHA256": rec.get("IMAGE_SHA256", "") if fb is not None else "",
        "FALLBACK_IDENTITY_VERIFIED": fb_verified if fb is not None else "NOT_APPLICABLE",
        "PRIOR_REVIEW_RECORD_USED": prior_used,
        "PRIOR_REVIEW_RECORD_COMPATIBLE": prior_compat,
        "IDENTITY_GATE_EXECUTED": "YES",
        "IDENTITY_VERIFIER_DECISION": rec.get("VERIFIER_DECISION", ""),
        "CANON_DEPICTION_STATUS": canon_status or "NO_GOVERNED_CHARACTER",
        "APPROVED_CHARACTER_PORTRAIT": "YES" if (accepted and canon_status == "CANONICAL_IDENTITY_GOVERNED") else "NO",
        "IDENTITY_LOCK_TEXT_SOURCE": lock_source or "NONE",
    })


def _aivsb_reasoning_enabled(env: Optional[Mapping[str, str]]) -> bool:
    """Same parser as app.make_chapter_image_prompts (AIVSB_REASONING_ENABLED, default off)."""
    e = env if env is not None else os.environ
    return str(e.get("AIVSB_REASONING_ENABLED", "0") or "").strip().lower() not in ("", "0", "false", "no", "off")


def _provenance_failed_binding(b: BindingResolution, why: str) -> BindingResolution:
    """AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: invalid / mismatched / conflicting provenance
    -> GOVERNED_CONTEXT_BINDING_FAILED (fail closed; never auto-accept, never NO_GOVERNED)."""
    nb = dataclasses.replace(b)
    nb.keys, nb.sources = [], {}
    nb.result = "FAILED"
    nb.fail_reason = f"{GOVERNED_CONTEXT_BINDING_FAILED}:{why}"
    nb.governed_context_present = True
    nb.no_governed_reason = ""
    return nb


def _augment_provenance(rec: Dict[str, Any], *, pa: Any, aivsb_ev: Optional[AivsbComposedEvidence],
                        prov_effect: str, prompt: str) -> None:
    """AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004 Phase 9 fields on EVERY record."""
    recs = list(getattr(pa, "records", []) or [])
    status = str(getattr(pa, "status", "NOT_ASSESSED") if pa is not None else "NOT_ASSESSED")
    detector = str(getattr(pa, "detector", "NO_MATCH") if pa is not None else "NOT_ASSESSED")
    registry = aivsb_ev is not None and aivsb_ev.matched_by == "REGISTRY"
    composed = getattr(pa, "aivsb_composed", None) if pa is not None else None
    rec.update({
        "AIVSB_COMPOSED": "YES" if (composed or registry) else ("NO" if (status == "VALID" and composed is False) else "UNKNOWN"),
        "PROVENANCE_ID": ",".join(str(r.get("provenance_id") or "") for r in recs),
        "PROVENANCE_SCHEMA_VERSION": ",".join(sorted({str(r.get("schema_version") or "") for r in recs})),
        "PROVENANCE_SOURCE_RUN": ",".join(sorted({str(r.get("source_run_id") or "") for r in recs if r.get("source_run_id")})),
        "PROVENANCE_SOURCE_ASSET": ",".join(sorted({str(r.get("source_asset_id") or "") for r in recs if r.get("source_asset_id")})),
        "PROVENANCE_PRESENT": "YES" if (pa is not None and pa.present) else "NO",
        "PROVENANCE_INTEGRITY_VALID": str(getattr(pa, "integrity_valid", "NOT_APPLICABLE")),
        "PROVENANCE_PROMPT_ASSOCIATION_VALID": str(getattr(pa, "association_valid", "NOT_APPLICABLE")),
        "PROVENANCE_ASSOCIATION_METHOD": str(getattr(pa, "association_method", "")),
        "PROVENANCE_RECOVERED_FROM": str(getattr(pa, "recovered_from", "NONE")),
        "PROVENANCE_REQUIRED": "YES" if (pa is not None and pa.required) else "NO",
        "PROVENANCE_STATUS": status,
        "PROVENANCE_EFFECT": prov_effect,
        "PROVENANCE_NOTES": list(getattr(pa, "notes", []) or []),
        "IMAGE_PROVENANCE_BINDING": str(getattr(pa, "image_binding", "ABSENT")),
        "REGISTRY_AVAILABLE": "YES" if registry else "NO",
        "FORMAT_DETECTOR_RESULT": detector,
        "FORMAT_DETECTOR_PATTERN": str(getattr(pa, "detector_pattern", "")),
        "FORMAT_DETECTOR_AUTHORITY": "ADVISORY_ONLY",
        "PROMPT_FORMAT_UNRECOGNISED": "YES" if (detector == "NO_MATCH" and str(prompt or "").strip()) else "NO",
        "PRE_AIVSB_CHARACTER_IDS": list(getattr(pa, "depicted_character_ids", []) or []),
        "PERSISTED_CHARACTER_IDS": list(getattr(pa, "character_ids", []) or []),
        "FINAL_GOVERNED_CONTEXT": "|".join([str(rec.get("GOVERNED_CONTEXT_BINDING_RESULT") or ""),
                                            str(rec.get("CHARACTER") or "-"), str(rec.get("IMAGE_INTENT_CLASS") or "")]),
        "PROMPT_FORMAT_DRIFT_DETECTED": "YES" if (pa is not None and (pa.drift or detector == "TOLERANT_MATCH")) else "NO",
        "PROVENANCE_MISMATCH_REASON": str(getattr(pa, "mismatch_reason", "")),
    })


def _merge_intent_requests(*reqs: Optional[ImageIntentRequest]) -> Optional[ImageIntentRequest]:
    """Later (more specific) requests override earlier ones field by field; scene_text concatenates."""
    out: Optional[ImageIntentRequest] = None
    for r in reqs:
        if r is None:
            continue
        if out is None:
            out = r
            continue
        out = ImageIntentRequest(
            depicted_characters=r.depicted_characters or out.depicted_characters,
            scene_subject=r.scene_subject or out.scene_subject,
            asset_role=r.asset_role or out.asset_role,
            background_only=r.background_only if r.background_only is not None else out.background_only,
            requested_asset_type=r.requested_asset_type or out.requested_asset_type,
            origin=r.origin or out.origin,
            scene_text=" ".join(t for t in (out.scene_text, r.scene_text) if t),
        )
    return out


def _augment_intent(rec: Dict[str, Any], *, intent: Optional[ImageIntent], binding: Optional[BindingResolution],
                    fb: Optional[Mapping[str, Any]], orig_intent_class: str, bypass_reason: str) -> None:
    """Part L final-hardening fields on EVERY record (bypass, bound, NO_GOVERNED, fail-closed, error)."""
    b = binding
    it = intent or ImageIntent("UNDETERMINED", "SAFE_DEFAULT_NO_STRUCTURED_INTENT", False, False,
                               ["INTENT_NOT_RESOLVED_GATE_ERROR"])
    verdict = str(rec.get("VERIFIER_DECISION"))
    error = rec.get("GOVERNED_CONTEXT_BINDING_RESULT") == "ERROR"
    failed = bool(b is not None and (b.result == "FAILED" or b.fail_reason))
    bypass = bool(bypass_reason) and verdict == NOT_APPLICABLE_DECISION and not failed and not error
    required = (not bypass and verdict != NON_CANON_DECISION
                and (it.governed_depiction or failed or error or bool(str(rec.get("CHARACTER") or ""))))
    tik = bool(fb is not None and fb.get("tiktok_reuse"))
    if fb is not None and orig_intent_class not in ALL_IMAGE_INTENT_CLASSES:
        orig_intent_class, orig_known = it.intent_class, False  # gate error before intent resolution
    else:
        orig_known = True
    if not tik:
        tik_ver = "NOT_APPLICABLE"
    elif not required:
        tik_ver = "NOT_REQUIRED"
    else:
        tik_ver = "YES" if verdict in ACCEPTING_DECISIONS else "NO"
    rec.update({
        "IMAGE_INTENT_CLASS": it.intent_class,
        "IMAGE_INTENT_SOURCE": it.source,
        "GOVERNED_CHARACTER_DEPICTION": "YES" if it.governed_depiction else "NO",
        "UPSTREAM_CHARACTER_ASSIGNED": "YES" if it.upstream_character_assigned else "NO",
        "STRUCTURED_CHARACTER_VALID": (b.structured_character_status if b is not None else "NOT_APPLICABLE"),
        "STRUCTURED_CHARACTER_CONFLICT": "YES" if (b is not None and b.structured_character_conflict) else "NO",
        "MALFORMED_CHARACTER_ID": "YES" if (b is not None and b.malformed_character_id) else "NO",
        "BINDING_FAILURE_REASON": (b.fail_reason if b is not None else ""),
        "SCENERY_BYPASS_APPLIED": "YES" if bypass else "NO",
        "SCENERY_BYPASS_REASON": bypass_reason if bypass else "",
        "IDENTITY_GATE_REQUIRED": "YES" if required else "NO",
        "FALLBACK_ORIGINAL_INTENT_CLASS": (orig_intent_class if fb is not None else "NOT_APPLICABLE"),
        "FALLBACK_INTENT_PRESERVED": ((("NO" if (orig_intent_class == INTENT_GOVERNED and it.intent_class not in
                                                 (INTENT_GOVERNED, "NON_CANON_SILHOUETTE")) else "YES")
                                       if orig_known else "NO")
                                      if fb is not None else "NOT_APPLICABLE"),
        "TIKTOK_REUSE_USED": "YES" if tik else "NO",
        "TIKTOK_REUSE_IDENTITY_VERIFIED": tik_ver,
        # evidence (not required fields)
        "IMAGE_INTENT_ORIGIN": it.origin,
        "IMAGE_INTENT_EVIDENCE": list(it.evidence),
    })


def _status_of(ver: Optional[IdentityVerification], name: str) -> Dict[str, Any]:
    if ver is None:
        return {"status": "NOT_APPLICABLE", "method": "NONE"}
    return dict(ver.fields.get(name) or {"status": METHOD_NONE, "method": METHOD_NONE})


def _record(rid: str, path_id: str, contract: Optional[IdentityContract], ver: Optional[IdentityVerification],
            decision: str, reasons: Sequence[str], accepted: bool, img: Optional[Path], image_sha: str,
            request_novel: str, milestone_conditioning_used: bool) -> Dict[str, Any]:
    constraint = ver.constraint if ver is not None else (resolve_identity_constraint(contract) if contract else {})
    age_field = _status_of(ver, "AGE_MATCH")
    rec: Dict[str, Any] = {
        "RUN_ID": rid,
        "TIMESTAMP": _now_pt_label(),
        "NOVEL": contract.novel_id if contract else request_novel,
        "CHARACTER": contract.character_id if contract else "",
        "IDENTITY_CONTRACT_ID": contract.contract_id if contract else "",
        "AUTHORITY_SOURCE": IDENTITY_AUTHORITY_SOURCE if contract else "",
        "TEXT_CANON_IDENTITY": text_canon_identity(contract) if contract else {},
        "VISUAL_DIRECTION": list(contract.visual_direction_allowed) if contract else [],
        "UNSPECIFIED_FIELDS": list(identity_spec_fields(contract)["unspecified_fields"]) if contract else [],
        "FINAL_IDENTITY_CONSTRAINT": {
            "constraint": constraint.get("FINAL_IDENTITY_CONSTRAINT", {}),
            "identity_lock": constraint.get("IDENTITY_LOCK", ""),
            "blocked_proposals": constraint.get("BLOCKED_PROPOSALS", []),
        } if contract else {},
        "MILESTONE_REF_PRESENT": ("YES (audit/visual-direction reference only: " + contract.milestone_reference_id + ")")
        if contract and contract.milestone_reference_id else "NO",
        "MILESTONE_CONDITIONING_USED": "YES" if milestone_conditioning_used else "NO",
        "AGE_EXPECTED": contract.age_required if contract else "",
        "AGE_OBSERVED": age_field.get("observed") if age_field.get("method") == METHOD_HUMAN else "NOT_OBSERVED",
        "FACE_MATCH": _status_of(ver, "FACE_MATCH"),
        "HAIR_MATCH": _status_of(ver, "HAIR_MATCH"),
        "BUILD_MATCH": _status_of(ver, "BUILD_MATCH"),
        "EYE_COLOR_MATCH": _status_of(ver, "EYE_COLOR_MATCH"),
        "DISTINCTIVE_TRAITS_MATCH": _status_of(ver, "DISTINCTIVE_TRAITS_MATCH"),
        "AUTOMATED_EVIDENCE_AVAILABLE": "NO (automated checks are spec/routing/field/binding/milestone/lighting-policy audits only; "
                                        "no qualified automated face/hair/build/age/eye method)",
        "HUMAN_REVIEW_REQUIRED": "NO" if accepted else "YES",
        "VERIFIER_CONFIDENCE": ver.confidence if ver is not None else "NONE",
        "VERIFIER_DECISION": decision,
        "FAIL_REASON": list(reasons),
        "AUTO_ACCEPT_ALLOWED": "YES" if accepted else "NO",
        "FEATURE_FLAG_ENABLED": "YES",
        "PATH_ID": path_id,
        "IMAGE_PATH": str(img or ""),
        "IMAGE_SHA256": image_sha,
        "QUARANTINE_PATH": "",
        "OBSERVATION_METHOD": ver.observation_method if ver is not None else "NONE",
        "AUTOMATED_CHECKS": ver.automated_checks if ver is not None else [],
        "PRODUCTION_DEFAULT": PRODUCTION_DEFAULT,
        "SCOPE": SCOPE,
        "IMAGE_BYTES_MUTATED_BY_IDENTITY_SYSTEM": "NO",
    }
    return rec


def enforce_identity_acceptance(image_path: Any, *, path_id: str, error_cls: type = None, **kwargs: Any) -> IdentityGateResult:
    """Run the gate and raise when auto-accept is not allowed (flag OFF: no-op BYPASS)."""
    result = run_identity_acceptance_gate(image_path, path_id=path_id, **kwargs)
    if not result.auto_accept_allowed:
        msg = (f"identity preservation blocked auto-accept at {path_id}: decision={result.decision} "
               f"quarantine={result.quarantine_path or '<none>'} reasons={result.fail_reason}")
        if error_cls is not None and issubclass(error_cls, BaseException):
            exc = error_cls(msg)
            try:
                setattr(exc, "identity_result", result)
            except Exception:
                pass
            raise exc
        raise IdentityAcceptanceBlocked(msg, result)
    return result


def is_identity_block(exc: BaseException) -> bool:
    return isinstance(exc, IdentityAcceptanceBlocked) or hasattr(exc, "identity_result")


def review_quarantined_image(
    quarantine_path: Any,
    observations: Mapping[str, Any],
    *,
    character_id: str,
    novel: str = "",
    spec: Any = None,
    environ: Optional[Mapping[str, str]] = None,
    writer: Optional[Callable[[Mapping[str, Any], Optional[Path], Path], Any]] = None,
    log_path: Optional[Path] = None,
    image_intent: Any = None,
) -> IdentityGateResult:
    """Only route to PASS on visual traits: a supplied qualified HUMAN_REVIEW record.

    PASS / UNSPECIFIED_OK -> image moved back to its original name (bytes unchanged).
    Anything else -> stays quarantined.
    """
    q = Path(str(quarantine_path))
    original = q.with_name(_QUARANTINE_TAG_RE.sub("", q.name, count=1))
    result = run_identity_acceptance_gate(
        q, path_id="HUMAN_REVIEW_RELEASE", spec=spec, novel=novel, character_id=character_id,
        observations=observations, environ=environ, writer=writer, log_path=log_path, quarantine=False,
        image_intent=image_intent,
    )
    if result.auto_accept_allowed and q.exists():
        os.replace(str(q), str(original))
        result.image_path = str(original)
        result.quarantine_path = ""
        # Coverage remediation (Part I): persist a sha-bound prior identity-review record so a
        # later reuse of these exact bytes for the same character / contract version can be
        # validated instead of re-reviewed. Flag ON only (the gate above bypasses when OFF).
        if result.feature_flag_enabled == "YES" and result.decision in ACCEPTING_DECISIONS and result.records:
            r0 = result.records[0]
            _o = _obs_for(observations, str(r0.get("CHARACTER") or "")) or {}
            if r0.get("CHARACTER") and str(_o.get("method", "")).upper() == METHOD_HUMAN:
                rec = build_prior_review_record(
                    image_sha256=str(r0.get("IMAGE_SHA256") or ""), character_id=str(r0.get("CHARACTER")),
                    verifier_decision=result.decision, human_review_status=PRIOR_REVIEW_APPROVED_STATUS,
                    reviewer=str(_o.get("reviewer", "")))
                prior_review_sidecar_path(original).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    else:
        result.quarantine_path = str(q)
    return result


# ---------------------------------------------------------------------------
# IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929 - Parts G/H/I/J
# Governed fallback policy, stock policy, prior identity-review reuse, procedural art.
# ---------------------------------------------------------------------------
def evaluate_governed_fallback(
    candidate: Any,
    *,
    fallback_source: str,
    asset_class: str,
    path_id: str,
    prompt: str = "",
    novel: str = "",
    character_id: str = "",
    identity_context: Optional[IdentityProductionContext] = None,
    prior_review_record: Any = None,
    observations: Any = None,
    quarantine: bool = False,
    write_sidecar: bool = False,
    environ: Optional[Mapping[str, str]] = None,
    writer: Optional[Callable[[Mapping[str, Any], Optional[Path], Path], Any]] = None,
    log_path: Optional[Path] = None,
    image_intent: Any = None,
    tiktok_reuse: bool = False,
    prompt_provenance: Any = None,
) -> IdentityGateResult:
    """One governed fallback / reuse policy (Part G). Flag OFF -> BYPASS (legacy behaviour).

    Flag ON, governed depiction (structured context or legacy prompt binding):
      * accepted only if the candidate is identity-verified NOW (qualified human
        observations for these exact bytes) or carries a COMPATIBLE prior identity-review
        record (same bytes sha256, same character, same contract id + version, accepting
        verifier decision, human review APPROVED);
      * otherwise REJECT_REVIEW / FAIL_CLOSED - never an unchecked reused person image.
    STOCK_IMAGE in a governed slot is never a canonical depiction without identity review
    (keyword match is not identity). PROCEDURAL_EMERGENCY_ART is classified
    NON_CANON_CHARACTER_DEPICTION (faceless / abstract; never an approved portrait).
    Shared bank / previous-run assets are evaluated in place and never moved
    (quarantine=False, no sidecar written next to them)."""
    if asset_class not in FALLBACK_ASSET_CLASSES:
        raise ValueError(f"unknown fallback asset class {asset_class!r}")
    return run_identity_acceptance_gate(
        candidate, path_id=path_id, prompt=prompt, novel=novel, character_id=character_id,
        identity_context=identity_context, observations=observations, environ=environ, writer=writer,
        log_path=log_path, quarantine=quarantine, write_sidecar=write_sidecar,
        fallback={"source": str(fallback_source or ""), "asset_class": asset_class,
                  "tiktok_reuse": bool(tiktok_reuse)},
        prior_review_record=prior_review_record, image_intent=image_intent, prompt_provenance=prompt_provenance,
    )


def enforce_governed_fallback(candidate: Any, **kwargs: Any) -> IdentityGateResult:
    """evaluate_governed_fallback + raise IdentityAcceptanceBlocked when not allowed."""
    result = evaluate_governed_fallback(candidate, **kwargs)
    if not result.auto_accept_allowed:
        raise IdentityAcceptanceBlocked(
            f"identity preservation blocked governed fallback at {result.path_id}: decision={result.decision} "
            f"asset_class={kwargs.get('asset_class')} source={kwargs.get('fallback_source')} reasons={result.fail_reason}",
            result,
        )
    return result


def classify_procedural_emergency_art(target: Any, *, path_id: str, fallback_source: str = "procedural_emergency_art",
                                      prompt: str = "", environ: Optional[Mapping[str, str]] = None,
                                      writer: Optional[Callable[[Mapping[str, Any], Optional[Path], Path], Any]] = None,
                                      log_path: Optional[Path] = None) -> IdentityGateResult:
    """Part J: procedural (abstract / faceless silhouette) art stays outside identity
    verification only because it is explicitly recorded NON_CANON_CHARACTER_DEPICTION with
    APPROVED_CHARACTER_PORTRAIT=NO in the log and in a sidecar next to the image."""
    return run_identity_acceptance_gate(
        target, path_id=path_id, prompt=prompt, environ=environ, writer=writer, log_path=log_path,
        quarantine=False, write_sidecar=True,
        fallback={"source": fallback_source, "asset_class": "PROCEDURAL_EMERGENCY_ART"},
    )


def canon_depiction_status(image_path: Any) -> str:
    """Downstream check: the recorded canon-depiction status for an image ('' if none)."""
    p = Path(str(image_path))
    side = p.with_name(p.name + ".identity_preservation.json")
    try:
        rec = json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(rec.get("CANON_DEPICTION_STATUS", ""))


def is_approved_character_portrait(image_path: Any) -> bool:
    """True only for an image whose identity record says APPROVED_CHARACTER_PORTRAIT=YES
    (procedural NON_CANON art / quarantined / unreviewed images are never approved)."""
    p = Path(str(image_path))
    side = p.with_name(p.name + ".identity_preservation.json")
    try:
        rec = json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(rec.get("APPROVED_CHARACTER_PORTRAIT", "NO")) == "YES" and \
        str(rec.get("CANON_DEPICTION_STATUS", "")) == "CANONICAL_IDENTITY_GOVERNED"
