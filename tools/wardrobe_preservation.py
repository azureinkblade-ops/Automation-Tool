"""WARDROBE preservation production plumbing (verify-only).

ENABLE_WARDROBE_PRESERVATION defaults OFF. PRODUCTION_DEFAULT stays NO.
Never mutates image bytes. Scopes wardrobe only — not held props, effects,
generic repair, or style refs.

Mirrors tools/held_prop_auto_repair.py flag + precommit seam style.
Promotes qualified shadow verifier (wardrobe-shadow-run-20260923) into
production-importable code.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Feature flag (dedicated; default OFF) — mirror ENABLE_HELD_PROP_AUTO_REPAIR
# ---------------------------------------------------------------------------
FEATURE_FLAG_NAME = "ENABLE_WARDROBE_PRESERVATION"
PRODUCTION_DEFAULT = "NO"  # never flipped by this module
AUTHORITY_SOURCE_REQUIRED = "TEXT_CANON"
CANON_PRECEDENCE = ("TEXT_CANON", "VISUAL_DIRECTION", "MILESTONE_STYLE_REF")

_TRUTHY = {"1", "true", "yes", "on"}

# Scope isolation markers — wardrobe lane must not touch these
SCOPE_EXCLUSIONS = (
    "HELD_PROP",
    "SCENE_CRITICAL_EFFECTS",
    "GENERIC_REPAIR",
    "STYLE_REFS_AS_WARDROBE_AUTHORITY",
)


def is_wardrobe_preservation_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Return True only when ENABLE_WARDROBE_PRESERVATION is explicitly truthy.

    Unset / empty / falsey → False (production-safe default OFF).
    """
    env = environ if environ is not None else os.environ
    raw = str(env.get(FEATURE_FLAG_NAME, "") or "").strip().lower()
    return raw in _TRUTHY


def feature_flag_status(environ: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    env = environ if environ is not None else os.environ
    raw = str(env.get(FEATURE_FLAG_NAME, "") or "")
    enabled = is_wardrobe_preservation_enabled(env)
    return {
        "FEATURE_FLAG_NAME": FEATURE_FLAG_NAME,
        "FEATURE_FLAG_RAW": raw if raw != "" else "<unset>",
        "FEATURE_FLAG_ENABLED": "YES" if enabled else "NO",
        "PRODUCTION_DEFAULT": PRODUCTION_DEFAULT,
        "SCOPE": "WARDROBE_ONLY",
        "SCOPE_EXCLUSIONS": ",".join(SCOPE_EXCLUSIONS),
        "NOTE": "Default OFF. Does not enable held-prop, effects, generic repair, or milestone wardrobe authority.",
    }


# ---------------------------------------------------------------------------
# Four-novel contracts (TEXT_CANON authority)
# ---------------------------------------------------------------------------

_CONTRACTS_EMBEDDED: Dict[str, Any] = {
    "kai": {
        "CHARACTER_ID": "kai",
        "NOVEL": "ha",
        "CONTRACT_ID": "kai_wardrobe_v1",
        "WARDROBE_REQUIRED": ["gray shirt with faded logo", "black pants"],
        "WARDROBE_ALLOWED": [
            "awakened cultivation trim (subtle)",
            "gray work shirt / clerk shirt class",
            "small faded generic logo (no store brand)",
        ],
        "WARDROBE_FORBIDDEN": [
            "store-name branding",
            "Korean text on clothing",
            "Happy Mart / Haengbok Mart / Seongbuk Mart branding",
            "unauthorized prominent emblem beyond small faded generic logo",
            "hoodie",
            "jacket as primary torso (unless scene explicitly authorizes)",
            "coat",
            "backpack as wardrobe authority",
            "hard armor",
            "pauldrons",
            "chest plate",
            "power armor",
            "military imagery",
        ],
        "COLOR_REQUIRED": ["gray (shirt)", "black (pants)"],
        "COLOR_ALLOWED": ["gray", "black", "subtle cultivation trim accents"],
        "ARMOR_ALLOWED": False,
        "ARMOR_FORBIDDEN": ["hard armor", "pauldrons", "chest plate", "power armor"],
        "LOGO_EMBLEM_ALLOWED": ["small_faded_generic_logo_only"],
        "LOGO_EMBLEM_FORBIDDEN": [
            "store-name branding",
            "unauthorized prominent emblem",
            "Korean text on clothing",
        ],
        "ACCESSORY_ALLOWED": ["pale-blue System HUD is EFFECT/UI not wardrobe"],
        "ACCESSORY_FORBIDDEN": ["backpack as wardrobe authority", "unauthorized emblem accessory"],
        "SCENE_DEPENDENT_VARIANTS": [],
        "UNSPECIFIED": ["exact fabric weave", "exact pant cut", "shoe style"],
        "TEXT_CANON_WARDROBE": [
            "gray_shirt_with_faded_logo",
            "black_pants",
            "awakened_cultivation_trim (subtle)",
        ],
        "VISUAL_DIRECTION": ["gray_clerk_wardrobe_direction (milestone allowed_authority; STYLE_REFS only)"],
        "MILESTONE_REFERENCE_ONLY": ["exact wardrobe_logo geometry/color from milestone", "milestone build"],
    },
    "kael": {
        "CHARACTER_ID": "kael_veyra",
        "NOVEL": "en",
        "CONTRACT_ID": "kael_wardrobe_v1",
        "WARDROBE_REQUIRED": [
            "SCENE_DEPENDENT: casual gamer wear (start) OR obsidian tech shell blue glyph trim (nexus)"
        ],
        "WARDROBE_ALLOWED": [
            "casual gamer wear",
            "obsidian tech shell with blue glyph trim (soft/tech garment class — NOT hard armor)",
        ],
        "WARDROBE_FORBIDDEN": [
            "hard armor shell",
            "pauldrons",
            "chest plate / chest-shell",
            "power armor",
            "full tactical plate",
            "helmet that erases face/identity as wardrobe default",
            "gym-adjacent armored body shell",
        ],
        "COLOR_REQUIRED": ["UNSPECIFIED for casual; blue glyph trim when nexus variant"],
        "COLOR_ALLOWED": ["casual gamer palette UNSPECIFIED", "obsidian + blue glyph accents (nexus)"],
        "ARMOR_ALLOWED": False,
        "ARMOR_FORBIDDEN": [
            "hard armor shell",
            "pauldrons",
            "chest plate",
            "power armor",
            "full tactical plate",
        ],
        "LOGO_EMBLEM_ALLOWED": [],
        "LOGO_EMBLEM_FORBIDDEN": ["any wardrobe emblem as canon"],
        "ACCESSORY_ALLOWED": [
            "Soulblade is EQUIPMENT not wardrobe",
            "holo UI is EFFECT/UI not wardrobe",
            "NexusPod is environment/prop not wardrobe",
        ],
        "ACCESSORY_FORBIDDEN": ["helmet that erases face as wardrobe default"],
        "SCENE_DEPENDENT_VARIANTS": [
            {"variant_id": "start", "wardrobe": "casual gamer wear"},
            {"variant_id": "nexus", "wardrobe": "obsidian tech shell blue glyph trim"},
        ],
        "UNSPECIFIED": [
            "exact casual garment brands/cuts",
            "exact tech-shell fabric construction beyond soft tech shell + blue glyph trim",
        ],
        "TEXT_CANON_WARDROBE": [
            "casual_gamer_wear (start)",
            "obsidian_tech_shell_blue_glyph_trim (nexus)",
        ],
        "VISUAL_DIRECTION": [
            "identity_direction / style_direction (milestone STYLE_REFS only; wardrobe_canon=false)"
        ],
        "MILESTONE_REFERENCE_ONLY": ["milestone wardrobe appearance", "glyph_layout"],
    },
    "liang": {
        "CHARACTER_ID": "liang",
        "NOVEL": "hp",
        "CONTRACT_ID": "liang_wardrobe_v1",
        "WARDROBE_REQUIRED": ["jade sect robes"],
        "WARDROBE_ALLOWED": ["jade sect robe class / cultivator robes"],
        "WARDROBE_FORBIDDEN": [
            "modern clothing",
            "hard armor",
            "pauldrons",
            "power armor",
            "treating exact_robe_construction from milestone as text canon",
            "promoting unauthorized weaponization into wardrobe canon",
        ],
        "COLOR_REQUIRED": ["UNSPECIFIED"],
        "COLOR_ALLOWED": [
            "UNSPECIFIED; jade-sect visual direction may prefer jade/muted gold/silver palette but exact robe hue is NOT text-locked"
        ],
        "ARMOR_ALLOWED": False,
        "ARMOR_FORBIDDEN": ["hard armor", "pauldrons", "power armor"],
        "LOGO_EMBLEM_ALLOWED": [],
        "LOGO_EMBLEM_FORBIDDEN": ["any wardrobe emblem as canon"],
        "ACCESSORY_ALLOWED": [
            "Jade Token (accessory/item)",
            "red banners nearby are ENVIRONMENT not wardrobe",
            "silver-edged weapon is EQUIPMENT not wardrobe",
        ],
        "ACCESSORY_FORBIDDEN": [],
        "SCENE_DEPENDENT_VARIANTS": [],
        "UNSPECIFIED": [
            "exact robe hue (red vs jade-green) — UNSPECIFIED != WRONG",
            "exact sleeve/hem construction",
            "belt/obi details",
            "footwear",
            "exact_robe_construction",
        ],
        "TEXT_CANON_WARDROBE": ["jade_sect_robes"],
        "VISUAL_DIRECTION": [
            "jade_sect_robe_direction",
            "mist_jade_muted_gold_silver_palette",
            "red_banner_environmental_direction",
        ],
        "MILESTONE_REFERENCE_ONLY": [
            "exact_robe_construction",
            "exact banner calligraphy",
            "weapon_equipment presentation",
        ],
    },
    "jarek": {
        "CHARACTER_ID": "jarek",
        "NOVEL": "sf",
        "CONTRACT_ID": "jarek_wardrobe_v1",
        "WARDROBE_REQUIRED": ["scavenger rags oil stained"],
        "WARDROBE_ALLOWED": [
            "layered oil-stained scavenger rags",
            "patched/frayed rough fabric class",
        ],
        "WARDROBE_FORBIDDEN": [
            "heavy plate armor",
            "hard armor shell",
            "pauldrons",
            "chest plate with forge-core aperture as wardrobe",
            "full helmet armored shell",
            "power armor",
            "structured tactical jacket as wardrobe canon",
            "replacing scavenger clothing with heavy armor",
        ],
        "COLOR_REQUIRED": ["UNSPECIFIED"],
        "COLOR_ALLOWED": ["oil/soot-stained scavenger tones UNSPECIFIED"],
        "ARMOR_ALLOWED": False,
        "ARMOR_FORBIDDEN": [
            "heavy plate armor",
            "hard armor shell",
            "pauldrons",
            "chest plate",
            "power armor",
            "full helmet armored shell",
        ],
        "LOGO_EMBLEM_ALLOWED": [],
        "LOGO_EMBLEM_FORBIDDEN": ["any wardrobe emblem as canon"],
        "ACCESSORY_ALLOWED": ["iron chains are EQUIPMENT/ENVIRONMENT association not wardrobe"],
        "ACCESSORY_FORBIDDEN": [],
        "SCENE_DEPENDENT_VARIANTS": [],
        "UNSPECIFIED": [
            "exact rag patch geometry",
            "exact soot pattern",
            "exact hair/skin (non-wardrobe)",
        ],
        "TEXT_CANON_WARDROBE": ["scavenger_rags_oil_stained"],
        "VISUAL_DIRECTION": [
            "scavenger_lean_hungry_hardened_direction",
            "oil-stained rag wardrobe direction (STYLE_REFS only; wardrobe_canon=false)",
        ],
        "MILESTONE_REFERENCE_ONLY": [
            "exact_scavenger_rag_construction",
            "structured_jacket_collar_tactical_seams_as_wardrobe_canon",
        ],
    },
}

_CHARACTER_ALIASES = {
    "kai": "kai",
    "kael": "kael",
    "kael_veyra": "kael",
    "liang": "liang",
    "jarek": "jarek",
}


def normalize_character_key(character_id: str) -> str:
    key = str(character_id or "").strip().lower().replace(" ", "_")
    if key not in _CHARACTER_ALIASES:
        raise KeyError(f"unknown wardrobe character_id: {character_id!r}")
    return _CHARACTER_ALIASES[key]


def load_contract(character_id: str) -> Dict[str, Any]:
    """Return the TEXT_CANON wardrobe contract for a character (copy)."""
    key = normalize_character_key(character_id)
    return json.loads(json.dumps(_CONTRACTS_EMBEDDED[key]))  # deep copy via JSON


def list_contract_character_keys() -> Tuple[str, ...]:
    return tuple(_CONTRACTS_EMBEDDED.keys())


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
REQUIRED_LOG_FIELDS: List[str] = [
    "RUN_ID",
    "TIMESTAMP",
    "NOVEL",
    "CHARACTER",
    "WARDROBE_CONTRACT_ID",
    "AUTHORITY_SOURCE",
    "TEXT_CANON_WARDROBE",
    "FINAL_WARDROBE_CONSTRAINT",
    "MILESTONE_REF_PRESENT",
    "WARDROBE_CLASS",
    "COLOR_MATCH",
    "ARMOR_STATE",
    "FORBIDDEN_ARMOR_PRESENT",
    "UNAUTHORIZED_EMBLEM",
    "UNAUTHORIZED_ACCESSORY",
    "UNSPECIFIED_FIELDS",
    "VERIFIER_CONFIDENCE",
    "VERIFIER_DECISION",
    "AUTO_ACCEPT_ALLOWED",
    "HUMAN_REVIEW_REQUIRED",
    "FAIL_REASON",
    "FEATURE_FLAG_ENABLED",
    # always-present plumbing fields
    "PRODUCTION_DEFAULT",
    "IMAGE_BYTES_MUTATED_BY_WARDROBE_SYSTEM",
    "UNRELATED_SCENE_FIELDS_CHANGED",
    "SCOPE",
]


def _now_pt_label() -> str:
    # Box / DavidsPC Automation tool convention: America/Phoenix wall clock.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S PT")


def empty_observability_record(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {k: None for k in REQUIRED_LOG_FIELDS}
    base.update(
        {
            "RUN_ID": "",
            "TIMESTAMP": _now_pt_label(),
            "AUTHORITY_SOURCE": AUTHORITY_SOURCE_REQUIRED,
            "FEATURE_FLAG_ENABLED": "NO",
            "PRODUCTION_DEFAULT": PRODUCTION_DEFAULT,
            "IMAGE_BYTES_MUTATED_BY_WARDROBE_SYSTEM": "NO",
            "UNRELATED_SCENE_FIELDS_CHANGED": "NO",
            "SCOPE": "WARDROBE_ONLY",
            "AUTO_ACCEPT_ALLOWED": "NO",
            "HUMAN_REVIEW_REQUIRED": "NO",
            "VERIFIER_DECISION": "BYPASS",
            "FAIL_REASON": None,
        }
    )
    base.update(overrides)
    return base


def validate_observability_record(record: Mapping[str, Any]) -> List[str]:
    return [k for k in REQUIRED_LOG_FIELDS if k not in record]


def write_observability_json(record: Mapping[str, Any], path: Path | str) -> Path:
    missing = validate_observability_record(record)
    if missing:
        raise ObservabilityError(f"incomplete wardrobe observability record; missing={missing}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(record), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


class ObservabilityError(Exception):
    """Raised when wardrobe observability cannot be completed (fail-closed)."""


class ObservabilityEmitter:
    def __init__(self, writer: Optional[Callable[[Mapping[str, Any], Path], Any]] = None):
        self._writer = writer or write_observability_json

    def emit(self, record: Mapping[str, Any], path: Path | str) -> Path:
        missing = validate_observability_record(record)
        if missing:
            raise ObservabilityError(f"incomplete wardrobe observability record; missing={missing}")
        return Path(self._writer(record, Path(path)))

    def __call__(self, record: Mapping[str, Any], path: Path | str) -> Path:
        return self.emit(record, path)


def emit_observability(record: Mapping[str, Any], path: Path | str) -> Path:
    return ObservabilityEmitter().emit(record, path)


# ---------------------------------------------------------------------------
# Canon precedence / WardrobeSpec resolution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedWardrobeConstraint:
    character_key: str
    novel: str
    contract_id: str
    authority_source: str
    text_canon_wardrobe: Tuple[str, ...]
    final_wardrobe: Tuple[str, ...]
    wardrobe_required: Tuple[str, ...]
    wardrobe_allowed: Tuple[str, ...]
    wardrobe_forbidden: Tuple[str, ...]
    color_required: Tuple[str, ...]
    color_allowed: Tuple[str, ...]
    armor_allowed: bool
    armor_forbidden: Tuple[str, ...]
    logo_emblem_allowed: Tuple[str, ...]
    logo_emblem_forbidden: Tuple[str, ...]
    accessory_allowed: Tuple[str, ...]
    accessory_forbidden: Tuple[str, ...]
    scene_dependent_variants: Tuple[Dict[str, str], ...]
    unspecified_fields: Tuple[str, ...]
    visual_direction: Tuple[str, ...]
    style_direction: Tuple[str, ...]
    milestone_ref_present: bool
    milestone_authority_creation_blocked: bool
    authority_leak_attempts: Tuple[Dict[str, Any], ...]
    final_constraint_lines: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _as_tuple(values: Any) -> Tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    return tuple(str(v) for v in values)


def resolve_wardrobe_constraint(
    character_id: str,
    *,
    variant: Optional[str] = None,
    milestone_style_ref: Optional[Mapping[str, Any]] = None,
    milestone_visual_appearance: Optional[Mapping[str, Any]] = None,
    visual_direction_override: Optional[Sequence[str]] = None,
) -> ResolvedWardrobeConstraint:
    """Resolve final wardrobe constraint with TEXT_CANON > VISUAL_DIRECTION > MILESTONE_STYLE_REF.

    Milestone / visual inputs may influence STYLE_DIRECTION only. They never populate
    authority fields (wardrobe/armor/logo/accessory/color required locks).
    MILESTONE_IMAGE → WARDROBE_AUTHORITY is blocked.
    """
    key = normalize_character_key(character_id)
    c = load_contract(key)
    milestone = dict(milestone_style_ref or {})
    milestone_visual = dict(milestone_visual_appearance or {})

    text_canon = _as_tuple(c.get("TEXT_CANON_WARDROBE"))
    visual_direction = _as_tuple(visual_direction_override or c.get("VISUAL_DIRECTION"))
    forbidden = _as_tuple(c.get("WARDROBE_FORBIDDEN"))
    color_required = _as_tuple(c.get("COLOR_REQUIRED"))
    color_allowed = _as_tuple(c.get("COLOR_ALLOWED"))

    style_direction = list(visual_direction)
    if milestone.get("present") or milestone.get("asset_label") or milestone.get("style_direction"):
        extra = milestone.get("style_direction") or []
        if isinstance(extra, str):
            extra = [extra]
        style_direction = list(dict.fromkeys(style_direction + list(extra)))
        if milestone.get("asset_label"):
            style_direction.append(f"STYLE_REF:{milestone.get('asset_label')}")

    # Attempted milestone wardrobe authority — MUST be rejected
    authority_leaks: List[Dict[str, Any]] = []
    for leak_type, value in (
        ("WARDROBE_OR_ARMOR", milestone_visual.get("wardrobe") or milestone_visual.get("armor")),
        ("COLOR", milestone_visual.get("color")),
        ("LOGO", milestone_visual.get("logo")),
        ("ACCESSORY", milestone_visual.get("accessory")),
        ("UNSPECIFIED_DETAIL", milestone_visual.get("exact_construction") or milestone_visual.get("unspecified_detail")),
    ):
        if value:
            authority_leaks.append(
                {
                    "type": leak_type,
                    "milestone_value": value,
                    "action": "IGNORED_TEXT_CANON_WINS",
                    "applied_to_final": False,
                }
            )

    final_wardrobe = list(text_canon)
    # Scene variant selection (Kael) — still TEXT_CANON variants, not milestone
    if key == "kael" and variant:
        if variant == "start":
            final_wardrobe = ["casual_gamer_wear"]
        elif variant == "nexus":
            final_wardrobe = ["obsidian_tech_shell_blue_glyph_trim"]

    # Never promote milestone specifics into UNSPECIFIED fields
    unspecified = list(_as_tuple(c.get("UNSPECIFIED")))
    if milestone_visual.get("exact_construction") or milestone_visual.get("unspecified_detail"):
        # stays UNSPECIFIED — do not remove or replace with milestone specific
        pass

    # Canon forbids hard armor even if milestone shows hard armor
    armor_forbidden = list(_as_tuple(c.get("ARMOR_FORBIDDEN")))
    if milestone_visual.get("armor") and not c.get("ARMOR_ALLOWED"):
        # keep forbid; do not allow
        pass

    # Canon color wins over milestone other color
    final_colors = list(color_required)

    milestone_authority_created = any(a.get("applied_to_final") for a in authority_leaks)
    assert not milestone_authority_created, "milestone must never create wardrobe authority"

    constraint_lines = [
        f"REQUIRED: {', '.join(final_wardrobe)}",
        f"FORBIDDEN: {', '.join(forbidden)}",
        "MILESTONE_AUTHORITY: STYLE_REFS_ONLY",
        "WARDROBE_CANON_SOURCE: TEXT_CANON",
        "PRECEDENCE: TEXT_CANON>VISUAL_DIRECTION>MILESTONE_STYLE_REF",
        "NO_MILESTONE_IMAGE_TO_WARDROBE_AUTHORITY",
        "NO_IMAGE_MUTATION",
    ]

    variants_raw = c.get("SCENE_DEPENDENT_VARIANTS") or []
    variants: Tuple[Dict[str, str], ...] = tuple(
        {"variant_id": str(v.get("variant_id", "")), "wardrobe": str(v.get("wardrobe", ""))}
        for v in variants_raw
        if isinstance(v, dict)
    )

    return ResolvedWardrobeConstraint(
        character_key=key,
        novel=str(c.get("NOVEL") or ""),
        contract_id=str(c.get("CONTRACT_ID") or f"{key}_wardrobe_v1"),
        authority_source=AUTHORITY_SOURCE_REQUIRED,
        text_canon_wardrobe=text_canon,
        final_wardrobe=tuple(final_wardrobe),
        wardrobe_required=_as_tuple(c.get("WARDROBE_REQUIRED")),
        wardrobe_allowed=_as_tuple(c.get("WARDROBE_ALLOWED")),
        wardrobe_forbidden=forbidden,
        color_required=tuple(final_colors),
        color_allowed=color_allowed,
        armor_allowed=bool(c.get("ARMOR_ALLOWED")),
        armor_forbidden=tuple(armor_forbidden),
        logo_emblem_allowed=_as_tuple(c.get("LOGO_EMBLEM_ALLOWED")),
        logo_emblem_forbidden=_as_tuple(c.get("LOGO_EMBLEM_FORBIDDEN")),
        accessory_allowed=_as_tuple(c.get("ACCESSORY_ALLOWED")),
        accessory_forbidden=_as_tuple(c.get("ACCESSORY_FORBIDDEN")),
        scene_dependent_variants=variants,
        unspecified_fields=tuple(unspecified),
        visual_direction=visual_direction,
        style_direction=tuple(style_direction),
        milestone_ref_present=bool(
            milestone.get("present") or milestone.get("asset_label") or milestone_visual
        ),
        milestone_authority_creation_blocked=True,
        authority_leak_attempts=tuple(authority_leaks),
        final_constraint_lines=tuple(constraint_lines),
    )


def build_wardrobe_spec_dict(resolved: ResolvedWardrobeConstraint) -> Dict[str, Any]:
    """Dict suitable for tools.generation_spec.WardrobeSpec(**kwargs) / asdict mirror."""
    return {
        "character_id": resolved.character_key
        if resolved.character_key != "kael"
        else "kael_veyra",
        "contract_id": resolved.contract_id,
        "wardrobe_required": resolved.wardrobe_required,
        "wardrobe_allowed": resolved.wardrobe_allowed,
        "wardrobe_forbidden": resolved.wardrobe_forbidden,
        "color_required": resolved.color_required,
        "color_allowed": resolved.color_allowed,
        "armor_allowed": resolved.armor_allowed,
        "armor_forbidden": resolved.armor_forbidden,
        "logo_emblem_allowed": resolved.logo_emblem_allowed,
        "logo_emblem_forbidden": resolved.logo_emblem_forbidden,
        "accessory_allowed": resolved.accessory_allowed,
        "accessory_forbidden": resolved.accessory_forbidden,
        "scene_dependent_variants": resolved.scene_dependent_variants,
        "unspecified_fields": resolved.unspecified_fields,
        "authority_source": AUTHORITY_SOURCE_REQUIRED,
    }


def attach_wardrobe_to_generation_spec(spec: Any, resolved: ResolvedWardrobeConstraint) -> Any:
    """Return a new GenerationSpec with wardrobe domain populated (immutable dataclasses).

    Uses dataclasses.replace. authority_source forced to TEXT_CANON.
    """
    from dataclasses import replace

    from tools.generation_spec import WardrobeSpec, WardrobeVariant

    variants = tuple(
        WardrobeVariant(variant_id=v["variant_id"], wardrobe=v["wardrobe"])
        for v in resolved.scene_dependent_variants
    )
    wardrobe = WardrobeSpec(
        character_id=build_wardrobe_spec_dict(resolved)["character_id"],
        contract_id=resolved.contract_id,
        wardrobe_required=resolved.wardrobe_required,
        wardrobe_allowed=resolved.wardrobe_allowed,
        wardrobe_forbidden=resolved.wardrobe_forbidden,
        color_required=resolved.color_required,
        color_allowed=resolved.color_allowed,
        armor_allowed=resolved.armor_allowed,
        armor_forbidden=resolved.armor_forbidden,
        logo_emblem_allowed=resolved.logo_emblem_allowed,
        logo_emblem_forbidden=resolved.logo_emblem_forbidden,
        accessory_allowed=resolved.accessory_allowed,
        accessory_forbidden=resolved.accessory_forbidden,
        scene_dependent_variants=variants,
        unspecified_fields=resolved.unspecified_fields,
        authority_source=AUTHORITY_SOURCE_REQUIRED,
    )
    if wardrobe.authority_source != AUTHORITY_SOURCE_REQUIRED:
        raise ValueError("WardrobeSpec.authority_source must be TEXT_CANON")
    return replace(spec, wardrobe=wardrobe)


# ---------------------------------------------------------------------------
# Deterministic postgen verifier (promoted from shadow)
# ---------------------------------------------------------------------------

VERIFIER_DECISIONS = ("PASS", "UNSPECIFIED_OK", "REJECT_REVIEW", "FAIL_CLOSED")


def verify_wardrobe_observations(
    character_id: str,
    observations: Mapping[str, Any],
    *,
    contract: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic fail-closed wardrobe verifier.

    Decisions: PASS | UNSPECIFIED_OK | REJECT_REVIEW | FAIL_CLOSED
    UNSPECIFIED != WRONG. UNCERTAIN → REJECT_REVIEW or FAIL_CLOSED, never PASS by assumption.
    """
    key = normalize_character_key(character_id)
    c = dict(contract) if contract is not None else load_contract(key)
    obs = dict(observations or {})
    checks: Dict[str, Any] = {}
    reasons: List[str] = []
    disposition = "PASS"

    armor_allowed = bool(c.get("ARMOR_ALLOWED"))
    armor_present = obs.get("ARMOR_PRESENT")
    forbidden_armor = obs.get("FORBIDDEN_ARMOR_PRESENT")
    armor_confidence = str(obs.get("ARMOR_DETECTOR_CONFIDENCE") or obs.get("VERIFIER_CONFIDENCE_HINT") or "HIGH")
    armor_state_in = obs.get("ARMOR_STATE")

    checks["ARMOR_PRESENT"] = armor_present
    checks["FORBIDDEN_ARMOR_PRESENT"] = forbidden_armor
    checks["ARMOR_DETECTOR_CONFIDENCE"] = armor_confidence

    if (
        forbidden_armor == "UNCERTAIN"
        or armor_present == "UNCERTAIN"
        or armor_confidence.upper() == "UNCERTAIN"
        or str(armor_state_in or "").upper() == "UNCERTAIN"
    ):
        disposition = "FAIL_CLOSED"
        reasons.append("forbidden_armor_detector_uncertain_fail_closed")
    elif (armor_present is True or forbidden_armor is True) and not armor_allowed:
        disposition = "REJECT_REVIEW"
        reasons.append("forbidden_armor_present")

    logo = obs.get("FORBIDDEN_LOGO_PRESENT", obs.get("UNAUTHORIZED_EMBLEM"))
    if isinstance(logo, bool):
        forbidden_logo = logo
    else:
        forbidden_logo = bool(logo) if logo not in (None, "PASS", False, "NO") else False
        if logo is True or logo == "FAIL" or logo == "YES":
            forbidden_logo = True
    checks["FORBIDDEN_LOGO_PRESENT"] = forbidden_logo
    logo_policy = c.get("LOGO_EMBLEM_ALLOWED")
    logo_allowed_list = c.get("LOGO_EMBLEM_ALLOWED") or []
    if isinstance(logo_policy, bool):
        logo_blocks_unauthorized = logo_policy is False
    else:
        logo_blocks_unauthorized = (
            logo_policy in (False, "small_faded_generic_logo_only")
            or "small_faded_generic_logo_only" in list(logo_allowed_list)
            or list(logo_allowed_list) == []
        )
    if forbidden_logo and logo_blocks_unauthorized:
        # Kai: only small faded generic allowed; unauthorized emblem fails
        if key == "kai" or list(logo_allowed_list) == [] or "small_faded_generic_logo_only" in list(logo_allowed_list):
            if disposition not in ("FAIL_CLOSED",):
                disposition = "REJECT_REVIEW"
            reasons.append("forbidden_logo_or_unauthorized_emblem")

    generic_faded = obs.get("GENERIC_FADED_LOGO_PRESENT")
    checks["GENERIC_FADED_LOGO_PRESENT"] = generic_faded
    if key == "kai" and generic_faded is True and not forbidden_logo:
        reasons.append("kai_generic_faded_logo_allowed")

    forb_acc = obs.get("FORBIDDEN_ACCESSORY_PRESENT", obs.get("UNAUTHORIZED_ACCESSORY"))
    if forb_acc in (True, "YES", "FAIL"):
        forb_acc_bool = True
    elif forb_acc in (False, "NO", "PASS", None):
        forb_acc_bool = False
    else:
        forb_acc_bool = bool(forb_acc)
    checks["FORBIDDEN_ACCESSORY_PRESENT"] = forb_acc_bool
    if forb_acc_bool and key in ("kai", "kael", "jarek"):
        if disposition not in ("FAIL_CLOSED",):
            disposition = "REJECT_REVIEW"
        reasons.append("forbidden_accessory_present")

    color = obs.get("REQUIRED_COLOR_PRESENT", obs.get("COLOR_MATCH"))
    # Normalize COLOR_MATCH-style values
    if color in ("PASS", True, "YES"):
        color_norm = "PASS"
    elif color in ("FAIL", False, "NO"):
        color_norm = "FAIL"
    elif color in ("UNSPECIFIED", "UNSPECIFIED_OK"):
        color_norm = "UNSPECIFIED"
    elif color == "PARTIAL":
        color_norm = "PARTIAL"
    else:
        color_norm = color
    checks["REQUIRED_COLOR_PRESENT"] = color_norm
    color_required = _as_tuple(c.get("COLOR_REQUIRED"))
    color_is_unspecified_lock = any("UNSPECIFIED" in str(x).upper() for x in color_required) or key == "liang"

    if color_norm == "FAIL" and not color_is_unspecified_lock:
        if disposition not in ("FAIL_CLOSED",):
            disposition = "REJECT_REVIEW"
        reasons.append("required_color_absent")
    elif color_norm == "UNSPECIFIED":
        if disposition == "PASS":
            disposition = "UNSPECIFIED_OK"
        reasons.append("color_unspecified_not_wrong")

    wclass = obs.get("WARDROBE_CLASS")
    checks["WARDROBE_CLASS"] = wclass
    checks["TORSO_COVERAGE_CLASS"] = obs.get("TORSO_COVERAGE_CLASS")

    forbidden_classes = {
        "kai": {"power_armor", "heavy_plate_armor", "hard_chest_shell"},
        "kael": {"power_armor", "heavy_plate_armor"},
        "liang": {"power_armor", "heavy_plate_armor"},
        "jarek": {"power_armor", "heavy_plate_armor"},
    }
    if wclass in forbidden_classes.get(key, set()):
        if disposition not in ("FAIL_CLOSED",):
            disposition = "REJECT_REVIEW"
        reasons.append(f"wardrobe_class_forbidden:{wclass}")

    if key == "kai" and wclass in ("clerk_blazer_backpack",):
        if disposition not in ("FAIL_CLOSED",):
            disposition = "REJECT_REVIEW"
        reasons.append("kai_clerk_drift_unauthorized_emblem_path")

    if key == "kael" and wclass in ("casual_gamer", "soft_obsidian_tech_shell"):
        if disposition == "PASS" and not (armor_present is True or forbidden_armor is True):
            pass

    if key == "liang" and wclass == "sect_robes" and not (armor_present is True):
        if disposition == "PASS" and color_norm == "UNSPECIFIED":
            disposition = "UNSPECIFIED_OK"
        if disposition == "REJECT_REVIEW" and reasons == ["color_unspecified_not_wrong"]:
            disposition = "UNSPECIFIED_OK"

    if key == "jarek" and wclass == "scavenger_oil_stained_rags":
        if disposition == "PASS" and not (armor_present is True or forbidden_armor is True):
            pass

    # Armor state label for observability
    if forbidden_armor is True or armor_present is True:
        armor_state = "FORBIDDEN_PRESENT" if not armor_allowed else "ALLOWED_PRESENT"
    elif str(armor_state_in or "").upper() == "UNCERTAIN" or armor_confidence.upper() == "UNCERTAIN":
        armor_state = "UNCERTAIN"
    else:
        armor_state = str(armor_state_in or "NONE")

    unspecified_fields = list(obs.get("UNSPECIFIED_FIELDS") or c.get("UNSPECIFIED") or [])

    conf_map = {"PASS": 0.85, "UNSPECIFIED_OK": 0.75, "REJECT_REVIEW": 0.9, "FAIL_CLOSED": 0.55}
    # If caller supplied numeric confidence and decision is uncertain path, keep lower
    supplied_conf = obs.get("VERIFIER_CONFIDENCE")
    try:
        verifier_confidence = float(supplied_conf) if supplied_conf is not None else conf_map.get(disposition, 0.5)
    except (TypeError, ValueError):
        verifier_confidence = conf_map.get(disposition, 0.5)
    if disposition == "FAIL_CLOSED":
        verifier_confidence = min(verifier_confidence, 0.55)

    unauthorized_emblem = bool(forbidden_logo)
    unauthorized_accessory = bool(forb_acc_bool)

    return {
        "character_id": key,
        "disposition": disposition,
        "VERIFIER_DECISION": disposition,
        "VERIFIER_CONFIDENCE": verifier_confidence,
        "WARDROBE_CLASS": wclass,
        "COLOR_MATCH": color_norm,
        "ARMOR_STATE": armor_state,
        "FORBIDDEN_ARMOR_PRESENT": forbidden_armor,
        "UNAUTHORIZED_EMBLEM": unauthorized_emblem,
        "UNAUTHORIZED_ACCESSORY": unauthorized_accessory,
        "UNSPECIFIED_FIELDS": unspecified_fields,
        "checks": checks,
        "reasons": reasons,
        "certainty_claim": "NO_UNSUPERVISED_VISION_CERTAINTY",
        "contract_armor_allowed": armor_allowed,
        "logo_emblem_allowed": logo_policy if logo_policy is not None else logo_allowed_list,
    }


# ---------------------------------------------------------------------------
# Precommit gate (verify-only; no image mutation)
# ---------------------------------------------------------------------------

@dataclass
class WardrobePrecommitResult:
    feature_flag_enabled: str
    verifier_decision: str
    auto_accept_allowed: str
    human_review_required: str
    fail_reason: str
    image_bytes_mutated: str = "NO"
    unrelated_scene_fields_changed: str = "NO"
    observability: Dict[str, Any] = field(default_factory=dict)
    resolved: Dict[str, Any] = field(default_factory=dict)
    verifier: Dict[str, Any] = field(default_factory=dict)
    committed_path: str = ""
    acceptance: str = "BYPASS"  # ACCEPT | REVIEW | FAIL_CLOSED | BYPASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_flag_enabled": self.feature_flag_enabled,
            "verifier_decision": self.verifier_decision,
            "auto_accept_allowed": self.auto_accept_allowed,
            "human_review_required": self.human_review_required,
            "fail_reason": self.fail_reason,
            "image_bytes_mutated": self.image_bytes_mutated,
            "unrelated_scene_fields_changed": self.unrelated_scene_fields_changed,
            "acceptance": self.acceptance,
            "committed_path": self.committed_path,
            "observability": self.observability,
            "resolved": self.resolved,
            "verifier": self.verifier,
            "PRODUCTION_DEFAULT": PRODUCTION_DEFAULT,
            "SCOPE": "WARDROBE_ONLY",
        }


def _decision_to_acceptance(decision: str) -> Tuple[str, str, str]:
    """Map verifier decision → (acceptance, auto_accept_allowed, human_review_required)."""
    if decision in ("PASS", "UNSPECIFIED_OK"):
        return "ACCEPT", "YES", "NO"
    if decision == "REJECT_REVIEW":
        return "REVIEW", "NO", "YES"
    if decision == "FAIL_CLOSED":
        return "FAIL_CLOSED", "NO", "YES"
    return "BYPASS", "NO", "NO"


def run_wardrobe_precommit_verify(
    *,
    character_id: str,
    observations: Optional[Mapping[str, Any]] = None,
    novel: str = "",
    variant: Optional[str] = None,
    milestone_style_ref: Optional[Mapping[str, Any]] = None,
    milestone_visual_appearance: Optional[Mapping[str, Any]] = None,
    base_output_path: Optional[Path | str] = None,
    contract: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
    log_dir: Optional[Path | str] = None,
    observability_writer: Optional[Callable[[Mapping[str, Any], Path], Any]] = None,
    run_id: Optional[str] = None,
) -> WardrobePrecommitResult:
    """BASE_RENDER → WARDROBE_VERIFY → ACCEPT/REVIEW/FAIL_CLOSED.

    Never mutates image bytes. Flag OFF → BYPASS (no enforcement).
    Logger failure while flag ON → FAIL_CLOSED (blocks acceptance).
    """
    env = environ if environ is not None else os.environ
    flag_on = is_wardrobe_preservation_enabled(env)
    rid = run_id or f"WARDROBE_{uuid.uuid4().hex[:12]}"
    base_path = Path(base_output_path) if base_output_path else None
    source_bytes = None
    if base_path and base_path.exists():
        source_bytes = base_path.read_bytes()

    def _finish(
        *,
        decision: str,
        fail_reason: str,
        resolved: Optional[ResolvedWardrobeConstraint] = None,
        verifier: Optional[Dict[str, Any]] = None,
        force_fail_closed: bool = False,
    ) -> WardrobePrecommitResult:
        if force_fail_closed:
            decision = "FAIL_CLOSED"
        acceptance, auto_ok, human = _decision_to_acceptance(decision)
        if not flag_on:
            acceptance, auto_ok, human = "BYPASS", "NO", "NO"
            decision = decision if decision == "BYPASS" else "BYPASS"
            fail_reason = fail_reason or "FEATURE_FLAG_OFF"

        record = empty_observability_record(
            RUN_ID=rid,
            TIMESTAMP=_now_pt_label(),
            NOVEL=novel or (resolved.novel if resolved else ""),
            CHARACTER=character_id,
            WARDROBE_CONTRACT_ID=(resolved.contract_id if resolved else ""),
            AUTHORITY_SOURCE=AUTHORITY_SOURCE_REQUIRED if resolved else AUTHORITY_SOURCE_REQUIRED,
            TEXT_CANON_WARDROBE=list(resolved.text_canon_wardrobe) if resolved else [],
            FINAL_WARDROBE_CONSTRAINT=list(resolved.final_constraint_lines) if resolved else [],
            MILESTONE_REF_PRESENT=(
                "YES" if (resolved and resolved.milestone_ref_present) else "NO"
            ),
            WARDROBE_CLASS=(verifier or {}).get("WARDROBE_CLASS"),
            COLOR_MATCH=(verifier or {}).get("COLOR_MATCH"),
            ARMOR_STATE=(verifier or {}).get("ARMOR_STATE"),
            FORBIDDEN_ARMOR_PRESENT=(verifier or {}).get("FORBIDDEN_ARMOR_PRESENT"),
            UNAUTHORIZED_EMBLEM=(verifier or {}).get("UNAUTHORIZED_EMBLEM"),
            UNAUTHORIZED_ACCESSORY=(verifier or {}).get("UNAUTHORIZED_ACCESSORY"),
            UNSPECIFIED_FIELDS=(verifier or {}).get("UNSPECIFIED_FIELDS")
            or (list(resolved.unspecified_fields) if resolved else []),
            VERIFIER_CONFIDENCE=(verifier or {}).get("VERIFIER_CONFIDENCE"),
            VERIFIER_DECISION=decision,
            AUTO_ACCEPT_ALLOWED=auto_ok if flag_on else "NO",
            HUMAN_REVIEW_REQUIRED=human if flag_on else "NO",
            FAIL_REASON=fail_reason or None,
            FEATURE_FLAG_ENABLED="YES" if flag_on else "NO",
        )

        log_error = None
        if flag_on and log_dir is not None:
            try:
                writer = observability_writer or write_observability_json
                out = Path(log_dir) / f"{rid}.wardrobe.json"
                writer(record, out)
            except Exception as exc:  # noqa: BLE001 — fail-closed on any log failure
                log_error = str(exc)
                decision = "FAIL_CLOSED"
                acceptance, auto_ok, human = "FAIL_CLOSED", "NO", "YES"
                fail_reason = f"OBSERVABILITY_LOG_FAILURE:{log_error}"
                record["VERIFIER_DECISION"] = decision
                record["AUTO_ACCEPT_ALLOWED"] = "NO"
                record["HUMAN_REVIEW_REQUIRED"] = "YES"
                record["FAIL_REASON"] = fail_reason

        # Prove no mutation
        if base_path and base_path.exists() and source_bytes is not None:
            assert base_path.read_bytes() == source_bytes, "wardrobe system mutated image bytes"

        return WardrobePrecommitResult(
            feature_flag_enabled="YES" if flag_on else "NO",
            verifier_decision=decision,
            auto_accept_allowed=auto_ok if flag_on else "NO",
            human_review_required=human if flag_on else "NO",
            fail_reason=fail_reason or "",
            image_bytes_mutated="NO",
            unrelated_scene_fields_changed="NO",
            observability=record,
            resolved=resolved.to_dict() if resolved else {},
            verifier=verifier or {},
            committed_path=str(base_path) if base_path else "",
            acceptance=acceptance,
        )

    if not flag_on:
        return _finish(decision="BYPASS", fail_reason="FEATURE_FLAG_OFF")

    # Flag ON: require resolvable contract
    try:
        resolved = resolve_wardrobe_constraint(
            character_id,
            variant=variant,
            milestone_style_ref=milestone_style_ref,
            milestone_visual_appearance=milestone_visual_appearance,
        )
    except Exception as exc:  # noqa: BLE001
        return _finish(
            decision="FAIL_CLOSED",
            fail_reason=f"MALFORMED_OR_MISSING_CONTRACT:{exc}",
            force_fail_closed=True,
        )

    if contract is None and not resolved.contract_id:
        return _finish(
            decision="FAIL_CLOSED",
            fail_reason="MALFORMED_OR_MISSING_CONTRACT",
            resolved=resolved,
            force_fail_closed=True,
        )

    if observations is None:
        return _finish(
            decision="FAIL_CLOSED",
            fail_reason="MISSING_WARDROBE_OBSERVATIONS",
            resolved=resolved,
            force_fail_closed=True,
        )

    verifier = verify_wardrobe_observations(
        character_id, observations, contract=contract or load_contract(character_id)
    )
    decision = verifier["VERIFIER_DECISION"]
    fail_reason = ",".join(verifier.get("reasons") or []) or (
        "" if decision in ("PASS", "UNSPECIFIED_OK") else decision
    )
    return _finish(decision=decision, fail_reason=fail_reason, resolved=resolved, verifier=verifier)


def apply_wardrobe_at_v2_dispatch_seam(
    *,
    base_output_path: Path | str,
    wardrobe: Mapping[str, Any],
    environ: Optional[Mapping[str, str]] = None,
    observability_writer: Optional[Callable[[Mapping[str, Any], Path], Any]] = None,
    log_dir: Optional[Path | str] = None,
) -> WardrobePrecommitResult:
    """V2 dispatch seam adapter: verify-only wardrobe precommit.

    Call only when wardrobe kwarg is provided. When wardrobe is None the dispatch
    must not import/call this path (flag-OFF / unrelated pipelines unchanged).
    Never overwrites base image bytes.
    """
    base = Path(base_output_path)
    return run_wardrobe_precommit_verify(
        character_id=str(wardrobe.get("character_id") or wardrobe.get("character") or ""),
        observations=wardrobe.get("observations"),
        novel=str(wardrobe.get("novel") or ""),
        variant=wardrobe.get("variant"),
        milestone_style_ref=wardrobe.get("milestone_style_ref"),
        milestone_visual_appearance=wardrobe.get("milestone_visual_appearance"),
        base_output_path=base,
        contract=wardrobe.get("contract"),
        environ=environ,
        log_dir=log_dir,
        observability_writer=observability_writer,
        run_id=wardrobe.get("run_id"),
    )


def wardrobe_request_from_dict(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a wardrobe seam payload."""
    return {
        "character_id": data.get("character_id") or data.get("character") or "",
        "novel": data.get("novel") or "",
        "variant": data.get("variant"),
        "observations": data.get("observations"),
        "milestone_style_ref": data.get("milestone_style_ref"),
        "milestone_visual_appearance": data.get("milestone_visual_appearance"),
        "contract": data.get("contract"),
        "run_id": data.get("run_id"),
    }


# ---------------------------------------------------------------------------
# Auto-attachment plumbing (WARDROBE_AUTO_ATTACHMENT_PLUMBING_20260924)
# ---------------------------------------------------------------------------
# === AUTO-ATTACHMENT API (appended to tools/wardrobe_preservation.py) ===
# Marker: WARDROBE_AUTO_ATTACHMENT_PLUMBING_20260924

SUPPORTED_WARDROBE_CHARACTER_KEYS: Tuple[str, ...] = ("kai", "kael", "liang", "jarek")
NOVEL_ID_FOR_CHARACTER: Dict[str, str] = {
    "kai": "ha",
    "kael": "en",
    "liang": "hp",
    "jarek": "sf",
}
EXPLICIT_WARDROBE_POLICY = "MUST_MATCH_CANONICAL_OR_FAIL_CLOSED"
MISSING_CONTRACT_POLICY = "NO_CONTRACT_NOT_APPLICABLE"
CALLER_OVERRIDE_CANON_ALLOWED = False  # CALLER_OVERRIDE_CANON_ALLOWED=NO

ATTACHMENT_REASONS = (
    "ATTACHED",
    "FLAG_OFF",
    "NO_CONTRACT",
    "EXPLICIT_CANONICAL_SPEC",
    "EXPLICIT_SPEC_MISMATCH",
    "UNSUPPORTED_CHARACTER",
    "NOVEL_MISMATCH",
)


class WardrobeCanonMismatchError(ValueError):
    """Caller-supplied wardrobe does not match TEXT_CANON. Override forbidden."""


class WardrobeNovelMismatchError(ValueError):
    """Provided novel_id conflicts with the character's TEXT_CANON contract novel."""


@dataclass
class WardrobeAutoAttachmentResult:
    attempted: bool
    attached: bool
    reason: str
    contract_id: str
    authority_source: str
    character_id: str
    novel_id: str
    spec: Any
    log_record: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "WARDROBE_AUTO_ATTACHMENT_ATTEMPTED": "YES" if self.attempted else "NO",
            "WARDROBE_AUTO_ATTACHMENT_RESULT": "YES" if self.attached else "NO",
            "CONTRACT_ID": self.contract_id,
            "AUTHORITY_SOURCE": self.authority_source,
            "ATTACHMENT_REASON": self.reason,
            "CHARACTER_ID": self.character_id,
            "NOVEL_ID": self.novel_id,
        }


def wardrobe_spec_is_populated(wardrobe: Any) -> bool:
    """True when GenerationSpec.wardrobe carries a TEXT_CANON contract."""
    if wardrobe is None:
        return False
    contract_id = str(getattr(wardrobe, "contract_id", "") or "")
    authority = str(getattr(wardrobe, "authority_source", "") or "")
    return bool(contract_id) and authority == AUTHORITY_SOURCE_REQUIRED


def try_normalize_character_key(character_id: str) -> Optional[str]:
    """Return normalized key or None when character is not a supported wardrobe contract."""
    try:
        return normalize_character_key(character_id)
    except KeyError:
        return None


def _wardrobe_spec_from_resolved(resolved: ResolvedWardrobeConstraint) -> Any:
    from tools.generation_spec import WardrobeSpec, WardrobeVariant

    variants = tuple(
        WardrobeVariant(variant_id=v["variant_id"], wardrobe=v["wardrobe"])
        for v in resolved.scene_dependent_variants
    )
    payload = build_wardrobe_spec_dict(resolved)
    return WardrobeSpec(
        character_id=payload["character_id"],
        contract_id=resolved.contract_id,
        wardrobe_required=resolved.wardrobe_required,
        wardrobe_allowed=resolved.wardrobe_allowed,
        wardrobe_forbidden=resolved.wardrobe_forbidden,
        color_required=resolved.color_required,
        color_allowed=resolved.color_allowed,
        armor_allowed=resolved.armor_allowed,
        armor_forbidden=resolved.armor_forbidden,
        logo_emblem_allowed=resolved.logo_emblem_allowed,
        logo_emblem_forbidden=resolved.logo_emblem_forbidden,
        accessory_allowed=resolved.accessory_allowed,
        accessory_forbidden=resolved.accessory_forbidden,
        scene_dependent_variants=variants,
        unspecified_fields=resolved.unspecified_fields,
        authority_source=AUTHORITY_SOURCE_REQUIRED,
    )


def resolve_wardrobe_spec(
    character_id: str,
    *,
    novel_id: str = "",
    variant: Optional[str] = None,
    milestone_style_ref: Optional[Mapping[str, Any]] = None,
    milestone_visual_appearance: Optional[Mapping[str, Any]] = None,
    visual_direction_override: Optional[Sequence[str]] = None,
    require_novel_match: bool = True,
) -> Optional[Any]:
    """Resolve authoritative TEXT_CANON WardrobeSpec for NOVEL_ID + CHARACTER_ID.

    Authority is Studio Bible / embedded TEXT_CANON contracts only.
    Does NOT derive from milestone image, style_ref, generated image, prompt
    appearance, or model guess. Returns None when no qualified contract exists.

    When novel_id is provided and conflicts with the contract novel, raises
    WardrobeNovelMismatchError (fail closed on authority conflict).
    """
    key = try_normalize_character_key(character_id)
    if key is None:
        return None
    contract = load_contract(key)
    expected_novel = str(contract.get("NOVEL") or NOVEL_ID_FOR_CHARACTER.get(key) or "").strip().lower()
    provided_novel = str(novel_id or "").strip().lower()
    if provided_novel and require_novel_match and expected_novel and provided_novel != expected_novel:
        # Accept common full-title normalizations via studio bible when available
        try:
            from tools.studio_bible_adapter import normalize_novel_id as _norm_novel

            provided_novel = _norm_novel(provided_novel, empty_ok=True) or provided_novel
        except Exception:
            pass
        if provided_novel != expected_novel:
            raise WardrobeNovelMismatchError(
                f"novel_id={novel_id!r} does not match TEXT_CANON novel "
                f"{expected_novel!r} for character {character_id!r}"
            )
    resolved = resolve_wardrobe_constraint(
        key,
        variant=variant,
        milestone_style_ref=milestone_style_ref,
        milestone_visual_appearance=milestone_visual_appearance,
        visual_direction_override=visual_direction_override,
    )
    return _wardrobe_spec_from_resolved(resolved)


def _coerce_wardrobe_spec(value: Any) -> Any:
    """Accept WardrobeSpec, Mapping, or None → WardrobeSpec or None."""
    if value is None:
        return None
    from tools.generation_spec import WardrobeSpec, WardrobeVariant

    if isinstance(value, WardrobeSpec):
        return value
    if isinstance(value, Mapping):
        variants_raw = value.get("scene_dependent_variants") or ()
        variants = []
        for v in variants_raw:
            if isinstance(v, WardrobeVariant):
                variants.append(v)
            elif isinstance(v, Mapping):
                variants.append(
                    WardrobeVariant(
                        variant_id=str(v.get("variant_id", "")),
                        wardrobe=str(v.get("wardrobe", "")),
                    )
                )
        return WardrobeSpec(
            character_id=str(value.get("character_id") or ""),
            contract_id=str(value.get("contract_id") or ""),
            wardrobe_required=_as_tuple(value.get("wardrobe_required")),
            wardrobe_allowed=_as_tuple(value.get("wardrobe_allowed")),
            wardrobe_forbidden=_as_tuple(value.get("wardrobe_forbidden")),
            color_required=_as_tuple(value.get("color_required")),
            color_allowed=_as_tuple(value.get("color_allowed")),
            armor_allowed=bool(value.get("armor_allowed", False)),
            armor_forbidden=_as_tuple(value.get("armor_forbidden")),
            logo_emblem_allowed=_as_tuple(value.get("logo_emblem_allowed")),
            logo_emblem_forbidden=_as_tuple(value.get("logo_emblem_forbidden")),
            accessory_allowed=_as_tuple(value.get("accessory_allowed")),
            accessory_forbidden=_as_tuple(value.get("accessory_forbidden")),
            scene_dependent_variants=tuple(variants),
            unspecified_fields=_as_tuple(value.get("unspecified_fields")),
            authority_source=str(value.get("authority_source") or ""),
        )
    raise TypeError(f"unsupported wardrobe explicit type: {type(value)!r}")


def _wardrobe_equality_core(ws: Any) -> Tuple[Any, ...]:
    return (
        str(getattr(ws, "contract_id", "") or ""),
        str(getattr(ws, "authority_source", "") or ""),
        tuple(getattr(ws, "wardrobe_required", ()) or ()),
        tuple(getattr(ws, "wardrobe_forbidden", ()) or ()),
        tuple(getattr(ws, "color_required", ()) or ()),
        bool(getattr(ws, "armor_allowed", False)),
        tuple(getattr(ws, "armor_forbidden", ()) or ()),
        tuple(getattr(ws, "logo_emblem_allowed", ()) or ()),
        tuple(getattr(ws, "logo_emblem_forbidden", ()) or ()),
        tuple(getattr(ws, "accessory_forbidden", ()) or ()),
    )


def explicit_wardrobe_matches_canonical(explicit: Any, canonical: Any) -> bool:
    if explicit is None or canonical is None:
        return False
    if str(getattr(explicit, "authority_source", "") or "") != AUTHORITY_SOURCE_REQUIRED:
        return False
    return _wardrobe_equality_core(explicit) == _wardrobe_equality_core(canonical)


def wardrobe_seam_dict_from_spec(
    spec: Any,
    *,
    observations: Optional[Mapping[str, Any]] = None,
    novel_id: str = "",
    variant: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build route_v2 wardrobe seam payload from an auto-attached GenerationSpec.wardrobe."""
    wardrobe = getattr(spec, "wardrobe", None)
    if not wardrobe_spec_is_populated(wardrobe):
        return None
    character_id = str(getattr(wardrobe, "character_id", "") or "")
    novel = str(novel_id or "")
    if not novel:
        key = try_normalize_character_key(character_id)
        if key:
            novel = NOVEL_ID_FOR_CHARACTER.get(key, "")
    payload: Dict[str, Any] = {
        "character_id": character_id,
        "novel": novel,
        "variant": variant,
        "observations": dict(observations) if observations is not None else None,
        "contract_id": str(getattr(wardrobe, "contract_id", "") or ""),
        "authority_source": str(getattr(wardrobe, "authority_source", "") or ""),
        "auto_attached": True,
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _emit_auto_attachment_log(
    record: Mapping[str, Any],
    *,
    observability_sink: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> None:
    if observability_sink is not None:
        observability_sink(dict(record))


def auto_attach_wardrobe_to_generation_spec(
    spec: Any,
    *,
    character_id: str = "",
    novel_id: str = "",
    wardrobe_explicit: Any = None,
    variant: Optional[str] = None,
    milestone_style_ref: Optional[Mapping[str, Any]] = None,
    milestone_visual_appearance: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
    observability_sink: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    fail_closed_on_mismatch: bool = True,
) -> WardrobeAutoAttachmentResult:
    """Flag-gated auto-attachment of TEXT_CANON WardrobeSpec onto GenerationSpec.

    IF ENABLE_WARDROBE_PRESERVATION=ON AND supported character has qualified contract
    THEN GenerationSpec.wardrobe is populated automatically (no manual wardrobe=).

    IF OFF: preserve existing behavior; do not attach enforcement spec.

    Explicit wardrobe=: must match canonical TEXT_CANON or fail closed
    (CALLER_OVERRIDE_CANON_ALLOWED=NO).

    Missing contract (flag ON): NO_CONTRACT_NOT_APPLICABLE — do not invent,
    copy milestone, or create empty permissive authority.
    """
    from dataclasses import replace

    cid = str(character_id or getattr(getattr(spec, "identity", None), "character_id", "") or "").strip()
    nid = str(novel_id or "").strip()
    attempted = True
    explicit = _coerce_wardrobe_spec(wardrobe_explicit)
    # Also treat already-populated spec.wardrobe as explicit when caller pre-set it
    # and no separate wardrobe_explicit was passed.
    if explicit is None and wardrobe_spec_is_populated(getattr(spec, "wardrobe", None)):
        explicit = getattr(spec, "wardrobe")

    enabled = is_wardrobe_preservation_enabled(environ)

    def _finish(
        *,
        attached: bool,
        reason: str,
        contract_id: str = "",
        authority_source: str = "",
        out_spec: Any = None,
        character: str = "",
        novel: str = "",
    ) -> WardrobeAutoAttachmentResult:
        log_record = {
            "WARDROBE_AUTO_ATTACHMENT_ATTEMPTED": "YES" if attempted else "NO",
            "WARDROBE_AUTO_ATTACHMENT_RESULT": "YES" if attached else "NO",
            "CONTRACT_ID": contract_id,
            "AUTHORITY_SOURCE": authority_source,
            "ATTACHMENT_REASON": reason,
            "CHARACTER_ID": character or cid,
            "NOVEL_ID": novel or nid,
            "FEATURE_FLAG_ENABLED": "YES" if enabled else "NO",
            "TIMESTAMP": _now_pt_label(),
            "EXPLICIT_WARDROBE_POLICY": EXPLICIT_WARDROBE_POLICY,
            "MISSING_CONTRACT_POLICY": MISSING_CONTRACT_POLICY,
            "CALLER_OVERRIDE_CANON_ALLOWED": "NO",
        }
        _emit_auto_attachment_log(log_record, observability_sink=observability_sink)
        return WardrobeAutoAttachmentResult(
            attempted=attempted,
            attached=attached,
            reason=reason,
            contract_id=contract_id,
            authority_source=authority_source,
            character_id=character or cid,
            novel_id=novel or nid,
            spec=out_spec if out_spec is not None else spec,
            log_record=log_record,
        )

    if not enabled:
        # Preserve existing behavior: leave spec unchanged (even if empty).
        # Do not strip a pre-existing explicit wardrobe — that would be a mutation
        # of caller intent under flag OFF; enforcement stays off via seam BYPASS.
        return _finish(attached=False, reason="FLAG_OFF", out_spec=spec)

    # Flag ON ---------------------------------------------------------------
    if explicit is not None and wardrobe_spec_is_populated(explicit):
        # Resolve canonical for the character named by explicit or cid
        explicit_cid = str(getattr(explicit, "character_id", "") or cid)
        try:
            canonical = resolve_wardrobe_spec(
                explicit_cid,
                novel_id=nid,
                variant=variant,
                milestone_style_ref=milestone_style_ref,
                milestone_visual_appearance=milestone_visual_appearance,
            )
        except WardrobeNovelMismatchError:
            if fail_closed_on_mismatch:
                raise
            return _finish(attached=False, reason="NOVEL_MISMATCH", out_spec=spec)

        if canonical is None:
            if fail_closed_on_mismatch:
                raise WardrobeCanonMismatchError(
                    f"explicit wardrobe for {explicit_cid!r} has no TEXT_CANON contract; "
                    f"CALLER_OVERRIDE_CANON_ALLOWED=NO"
                )
            return _finish(attached=False, reason="EXPLICIT_SPEC_MISMATCH", out_spec=spec)

        if not explicit_wardrobe_matches_canonical(explicit, canonical):
            if fail_closed_on_mismatch:
                raise WardrobeCanonMismatchError(
                    f"explicit wardrobe does not match TEXT_CANON contract "
                    f"{getattr(canonical, 'contract_id', '')}; CALLER_OVERRIDE_CANON_ALLOWED=NO"
                )
            return _finish(
                attached=False,
                reason="EXPLICIT_SPEC_MISMATCH",
                contract_id=str(getattr(canonical, "contract_id", "") or ""),
                authority_source=AUTHORITY_SOURCE_REQUIRED,
                out_spec=spec,
            )

        # Match: keep canonical (authoritative) attachment
        out = replace(spec, wardrobe=canonical)
        return _finish(
            attached=True,
            reason="EXPLICIT_CANONICAL_SPEC",
            contract_id=str(canonical.contract_id),
            authority_source=AUTHORITY_SOURCE_REQUIRED,
            out_spec=out,
            character=str(canonical.character_id),
        )

    # No explicit populated wardrobe — resolve from character/novel
    if not cid:
        return _finish(attached=False, reason="NO_CONTRACT", out_spec=spec)

    key = try_normalize_character_key(cid)
    if key is None:
        return _finish(
            attached=False,
            reason="UNSUPPORTED_CHARACTER",
            out_spec=spec,
            character=cid,
        )

    try:
        canonical = resolve_wardrobe_spec(
            key,
            novel_id=nid,
            variant=variant,
            milestone_style_ref=milestone_style_ref,
            milestone_visual_appearance=milestone_visual_appearance,
        )
    except WardrobeNovelMismatchError:
        if fail_closed_on_mismatch:
            raise
        return _finish(attached=False, reason="NOVEL_MISMATCH", out_spec=spec, character=cid)

    if canonical is None:
        # Should not happen for supported keys, but keep safe policy
        return _finish(attached=False, reason="NO_CONTRACT", out_spec=spec, character=cid)

    out = replace(spec, wardrobe=canonical)
    return _finish(
        attached=True,
        reason="ATTACHED",
        contract_id=str(canonical.contract_id),
        authority_source=AUTHORITY_SOURCE_REQUIRED,
        out_spec=out,
        character=str(canonical.character_id),
        novel=nid or NOVEL_ID_FOR_CHARACTER.get(key, ""),
    )


def apply_auto_attached_wardrobe(
    spec: Any,
    *,
    character_id: str = "",
    novel_id: str = "",
    wardrobe_explicit: Any = None,
    variant: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
    **kwargs: Any,
) -> Any:
    """Convenience: return GenerationSpec after flag-gated auto-attach."""
    result = auto_attach_wardrobe_to_generation_spec(
        spec,
        character_id=character_id,
        novel_id=novel_id,
        wardrobe_explicit=wardrobe_explicit,
        variant=variant,
        environ=environ,
        **kwargs,
    )
    return result.spec

