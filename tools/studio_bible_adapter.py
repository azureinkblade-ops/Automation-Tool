"""Image Pipeline V2 M2 — Studio Bible Visual Adapter (read-only projection).

M2 consumes the M1 GenerationSpec contract; it does NOT redesign it.
M1_CONTRACT_MUTATION_AUTHORIZED = False (see constant below and the checkpoint
at .kilo/plans/image_pipeline_v2_m1_checkpoint.md). If this adapter cannot fill
a GenerationSpec field because the field does not exist, it raises
ContractIncompatibilityError with the exact missing path. It never adds fields to
tools/generation_spec.py.

Design constraints (design doc section E.3 / M2 stage):
- READ-ONLY against Studio Bible: canon YAML is read, never mutated. Source dicts
  are not modified.
- MISSING canonical data is represented as absent/unresolved (empty string /
  empty tuple), never synthesized.
- Canon diagnostics (malformed / contradictory entries) are surfaced as warnings,
  never silently dropped.
- Adapter output is a stable, hashable projection consumed by the GenerationSpec
  builder (a later stage / the deterministic router sets pipeline, seed, etc.).
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.gate6a_conditioning import ConditioningSpec, RunConfig
from tools.generation_spec import (
    AttachmentSpec,
    CompositionSpec,
    ConditioningSpec,  # noqa: F811  (re-exported for clarity)
    ContentSpec,
    GenerationSpec,
    IdentitySpec,
    ModelExecutionSpec,
    ReferenceBinding,
    ReferenceSpec,
    StudioBibleBinding,
    StyleSpec,
    canonical_serialize_obj,
)

# --- M1 contract guard (binding for M2) -------------------------------------
M1_CONTRACT_MUTATION_AUTHORIZED = False


class ContractIncompatibilityError(Exception):
    """Raised when M2 needs a GenerationSpec field that does not exist.

    This makes any M1 contract deficiency visible instead of letting M2 silently
    expand or rewrite tools/generation_spec.py.
    """


# Fields this adapter intends to populate on GenerationSpec. If any path is
# absent, project_to_generation_spec fails loudly with the exact path.
REQUIRED_CONTRACT_PATHS = (
    "spec_version",
    "identity.character_id",
    "identity.studio_bible_binding",
    "identity.reference_bindings",
    "content.subjects",
    "content.environment",
    "content.props",
    "style.pipeline",
    "style.style_profile",
    "style.palette",
    "style.lighting_design",
    "conditioning.object_class",
    "conditioning.object_state",
    "conditioning.object_identity",
    "conditioning.lighting",
    "conditioning.negative_constraints",
    "attachment.attachment_type",
    "attachment.required_visible_evidence",
    "references",
    "run.seed",
)


def _require_contract_paths(paths: Tuple[str, ...]) -> None:
    if M1_CONTRACT_MUTATION_AUTHORIZED:
        return
    probe = GenerationSpec()
    for path in paths:
        obj: Any = probe
        for part in path.split("."):
            if not hasattr(obj, part):
                raise ContractIncompatibilityError(path)
            obj = getattr(obj, part)


# --- Bible (Studio Canon) location -----------------------------------------
_DEFAULT_BIBLE_DIR = Path(r"C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb")
BIBLE_DIR = Path(os.environ.get("AIVSB_BIBLE_DIR", str(_DEFAULT_BIBLE_DIR))).resolve()
CHARACTERS_DIR = BIBLE_DIR / "characters"
LOCATIONS_DIR = BIBLE_DIR / "locations"
STYLE_DIR = BIBLE_DIR / "style_guides"
VISUAL_REFS_DIR = BIBLE_DIR / "visual_references"

NOVEL_STYLE_FILE = {"en": "en.yaml", "ha": "ha.yaml", "hp": "hp.yaml", "sf": "sf.yaml"}
NOVEL_GENRE_LABEL = {
    "hp": "xianxia cultivation fantasy illustration",
    "en": "cyberpunk mystic fantasy illustration",
    "sf": "ashpunk industrial fantasy illustration",
    "ha": "system fantasy illustration",
}

# --- Novel-id normalizer (single owner for live full-title -> short-id) ------
NORMALIZER_OWNER = "tools.studio_bible_adapter.normalize_novel_id"
CLIP_PROJECTION_OWNER = "tools.studio_bible_adapter.clip_cinematography_clauses"
CINEMATIC_POLICY_OWNER = "aivsb/cinematic_language.yaml"
CAMERA_INTENT_POLICY_OWNER = "aivsb/camera_intents.yaml"
LIGHTING_INTENT_POLICY_OWNER = "aivsb/lighting_intents.yaml"
# Bible fallback is the camera intent whose when_to_use list contains the token
# "default" (currently medium in camera_intents.yaml). Not a Python creative default.
BIBLE_DEFAULT_WHEN_TO_USE_TOKEN = "default"

_SHORT_NOVEL_IDS = frozenset({"en", "ha", "hp", "sf"})

# Exact live titles only (case/whitespace collapsed). No fuzzy guessing.
_FULL_TITLE_TO_NOVEL_ID = {
    "eternal nexus": "en",
    "heavenly ascension system": "ha",
    "the hundredfold path": "hp",
    "hundredfold path": "hp",
    "soul forge era": "sf",
    "soulforge era": "sf",
}


class CanonStatus:
    """Fail-closed required-canon taxonomy for bible-driven V2."""

    OK = "OK"
    UNKNOWN_NOVEL = "UNKNOWN_NOVEL"
    UNKNOWN_CHARACTER = "UNKNOWN_CHARACTER"
    UNKNOWN_SCENE = "UNKNOWN_SCENE"
    MISSING_REQUIRED_CANON = "MISSING_REQUIRED_CANON"
    CONTRADICTORY_CANON = "CONTRADICTORY_CANON"


class CanonUnresolvedError(RuntimeError):
    """Raised when required Studio Bible canon cannot be resolved (fail closed)."""

    def __init__(self, code: str, detail: str = ""):
        self.code = str(code or CanonStatus.MISSING_REQUIRED_CANON)
        self.detail = str(detail or "")
        msg = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(msg)


def _collapse_novel_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_novel_id(value: Any, *, empty_ok: bool = True) -> str:
    """Deterministic novel-id normalizer.

    Maps exact live full titles and identity short ids (en|ha|hp|sf) to the
    Studio Bible short id. Case/whitespace safe. Unknown non-empty input fails
    closed (raises CanonUnresolvedError / UNKNOWN_NOVEL) — never silent map.
    """
    raw = str(value or "").strip()
    if not raw:
        if empty_ok:
            return ""
        raise CanonUnresolvedError(CanonStatus.UNKNOWN_NOVEL, "empty novel id")
    key = _collapse_novel_key(raw)
    if key in _SHORT_NOVEL_IDS:
        return key
    mapped = _FULL_TITLE_TO_NOVEL_ID.get(key)
    if mapped:
        return mapped
    raise CanonUnresolvedError(
        CanonStatus.UNKNOWN_NOVEL, f"unknown novel id/title: {raw!r}"
    )


@dataclass(frozen=True)
class CanonEvaluation:
    status: str = CanonStatus.OK
    codes: Tuple[str, ...] = ()
    detail: str = ""


def evaluate_required_canon(
    projection: "StudioBibleProjection",
    *,
    scene_text: str = "",
) -> CanonEvaluation:
    """Evaluate required canon for bible-driven V2 (no optional-field broadening).

    CONTRADICTORY_CANON is scoped to the selected character/location for this
    request novel — global load warnings from other novels do not fail-close.
    """
    codes: List[str] = []
    scene = scene_text if scene_text is not None else projection.scene_text
    if not (projection.novel or "").strip():
        codes.append(CanonStatus.UNKNOWN_NOVEL)
    primary = select_character_record(projection, scene)
    loc = select_location_record(projection, scene)
    if primary is None or "content.subjects" in projection.unresolved_fields or "characters" in projection.unresolved_fields:
        codes.append(CanonStatus.UNKNOWN_CHARACTER)
    # Unmatched implied setting returns loc=None (fail closed, no pool[0]
    # injection). That is not UNKNOWN_SCENE when the novel still has locations;
    # scene_text carries the setting language. Raise only when the novel has no
    # location pool / environment is structurally unresolved.
    novel_l = (projection.novel or "").lower()
    novel_locs = [
        l for l in projection.locations
        if novel_l and (l.novel or "").lower() == novel_l
    ] if novel_l else list(projection.locations)
    if "content.environment" in projection.unresolved_fields or not novel_locs:
        codes.append(CanonStatus.UNKNOWN_SCENE)
    if (not projection.styles) or "style.palette" in projection.unresolved_fields:
        codes.append(CanonStatus.MISSING_REQUIRED_CANON)
    # Scope contradictions to the selected character/location by name. Per-record
    # warnings currently accumulate the shared projection warning list, so name
    # matching avoids cross-novel false positives.
    if primary is not None:
        pname = (primary.name or "").lower()
        if pname and any(
            "contradiction" in str(w).lower() and pname in str(w).lower()
            for w in projection.canon_warnings
        ):
            codes.append(CanonStatus.CONTRADICTORY_CANON)
    # Stable unique order
    codes = list(dict.fromkeys(codes))
    if not codes:
        return CanonEvaluation(status=CanonStatus.OK, codes=())
    return CanonEvaluation(
        status=codes[0],
        codes=tuple(codes),
        detail=",".join(codes),
    )


def require_resolved_canon(
    projection: "StudioBibleProjection",
    *,
    scene_text: str = "",
) -> None:
    """Fail closed when required canon is unresolved. Does not broaden to optional fields."""
    ev = evaluate_required_canon(projection, scene_text=scene_text)
    if ev.status != CanonStatus.OK:
        raise CanonUnresolvedError(ev.status, ev.detail)


# Canon negative constraints that protect identity (mirrors visual_director).
CANON_NEGATIVE_CONSTRAINTS = (
    "modern clothing", "modern objects", "incorrect weapon", "wrong clothing",
    "incorrect hairstyle", "changed eye color", "changed age", "extra limbs",
    "distorted hands", "generic fantasy appearance", "wrong setting",
    "missing character symbols",
)

_WEAPON_CANON = {
    "silver edged weapon": "silver-edged sword",
    "silver edged": "silver-edged sword",
    "silver_edged_weapon": "silver-edged sword",
    "silver edged sword": "silver-edged sword",
}
_WEAPON_NOUNS = ("soulblade", "sword", "jian", "blade", "bow", "staff",
                 "spear", "fan", "horn", "axe", "saber", "sabre")
_NEG_WEAPON = ("no weapon", "carries no", "missing weapon", "unarmed")
_AGE_CANON = {"reborn_adult": "young adult", "young_adult": "young adult",
              "young adult": "young adult"}
_GENDER_PRONOUNS = {"he": "male", "him": "male", "his": "male", "himself": "male",
                    "she": "female", "her": "female", "hers": "female", "herself": "female"}


# --------------------------------------------------------------------------- #
# Projection record types (read-only, hashable)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CharacterVisualRecord:
    character_id: str = ""
    version: str = ""
    name: str = ""
    novel: str = ""  # owning novel (canon `novel` key); selection-time scoping only
    gender: str = ""
    age: str = ""
    build: str = ""
    hair: str = ""
    eyes: str = ""
    clothing: Tuple[str, ...] = ()
    weapons: Tuple[str, ...] = ()
    magic_style: str = ""
    lighting_preference: str = ""
    identity_constraints: Tuple[str, ...] = ()
    forbidden_changes: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class LocationVisualRecord:
    location_id: str = ""
    name: str = ""
    novel: str = ""  # owning novel (canon `novel` key); selection-time scoping only
    architecture: Tuple[str, ...] = ()
    environment_state: str = ""
    lighting: str = ""
    magic_effects: str = ""
    banners_decorations: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StyleProfile:
    novel: str = ""
    genre_label: str = ""
    palette_phrase: str = ""
    line_shading_behavior: str = ""
    material_treatment: str = ""
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectVisualRecord:
    object_id: str = ""
    version: str = ""
    state: str = ""  # drawn | sheathed | prop
    canonical_phrase: str = ""
    attachment_type: str = ""
    attachment_mechanism: str = ""
    required_visible_evidence: Tuple[str, ...] = ()
    reference_asset: str = ""
    reference_sha256: str = ""
    character_id: str = ""  # owning character; empty means unscored (no cross-novel fallback)
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MilestoneVisualReference:
    novel: str = ""
    character_id: str = ""
    reference_class: str = "MILESTONE_VISUAL_REFERENCE"
    asset_path: str = ""
    asset_sha256: str = ""
    allowed_authority: Tuple[str, ...] = ()
    noncanon_attributes: Tuple[str, ...] = ()
    build_canon: bool = False
    wardrobe_logo_canon: bool = False
    amber_qi_canon: bool = False
    golden_core_canon: bool = False
    wardrobe_canon: bool = False
    glyph_layout_canon: bool = False
    exact_environment_geometry_canon: bool = False


@dataclass(frozen=True)
class CameraIntent:
    intent_id: str = ""
    description: str = ""


@dataclass(frozen=True)
class LightingIntent:
    intent_id: str = ""
    description: str = ""


@dataclass(frozen=True)
class RenderRules:
    mechanical_invariants: Tuple[str, ...] = ()


@dataclass(frozen=True)
class NegativeConstraints:
    canon: Tuple[str, ...] = ()
    per_character: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StudioBibleProjection:
    novel: str = ""
    chapter: str = ""
    scene_text: str = ""
    characters: Tuple[CharacterVisualRecord, ...] = ()
    locations: Tuple[LocationVisualRecord, ...] = ()
    styles: Tuple[StyleProfile, ...] = ()
    objects: Tuple[ObjectVisualRecord, ...] = ()
    camera_intents: Tuple[CameraIntent, ...] = ()
    lighting_intents: Tuple[LightingIntent, ...] = ()
    render_rules: RenderRules = field(default_factory=RenderRules)
    negative_constraints: NegativeConstraints = field(default_factory=NegativeConstraints)
    unresolved_fields: Tuple[str, ...] = ()
    canon_warnings: Tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Read-only canon loaders (no mutation of source dicts)
# --------------------------------------------------------------------------- #


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # available in the AIVSB/codex runtime
    except Exception:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


def load_character_profiles() -> Dict[str, Dict[str, Any]]:
    """Return {lower_full_name: profile} across character YAML files.

    READ-ONLY: source dicts are NOT mutated (no in-place setdefault of `_source`).
    """
    profiles: Dict[str, Dict[str, Any]] = {}
    if not CHARACTERS_DIR.exists():
        return profiles
    for path in sorted(CHARACTERS_DIR.glob("*.yaml")):
        data = _load_yaml(path)
        if not data:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            profiles[key] = entry
            first = key.split()[0]
            if first and first not in profiles:
                profiles[first] = entry
    return profiles


def load_locations() -> List[Dict[str, Any]]:
    data = _load_yaml(LOCATIONS_DIR / "locations.yaml")
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def load_novel_palette(novel: str) -> Dict[str, Any]:
    try:
        novel_id = normalize_novel_id(novel, empty_ok=True)
    except CanonUnresolvedError:
        return {}
    fname = NOVEL_STYLE_FILE.get(novel_id)
    if not fname:
        return {}
    data = _load_yaml(STYLE_DIR / fname)
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------- #
# Canonicalization helpers (project, do not synthesize)
# --------------------------------------------------------------------------- #


def _clean_canon_token(value: str) -> str:
    v = str(value or "").strip()
    if "(" in v:
        v = v[: v.index("(")].strip()
    import re
    v = re.sub(r"\s+at\s+Ch\d+.*$", "", v, flags=re.IGNORECASE)
    return v.replace("_", " ").strip()


def _canon_weapon(token: str) -> str:
    """Normalize a weapon descriptor to a single canonical phrase (no synthesis
    beyond the frozen Bible's own tokens)."""
    t = _clean_canon_token(token).strip().lower()
    if t in _WEAPON_CANON:
        return _WEAPON_CANON[t]
    words = [w for w in re.split(r"[\s,]+", t) if w] if t else []
    if not words:
        return token
    base = next((w for w in words if w in _WEAPON_NOUNS), None)
    if base is None:
        return " ".join(words[:2])
    if "silver" in words and base in ("edged",):
        return "silver-edged sword"
    if base == "soulblade":
        return "Soulblade"
    idx = words.index(base)
    modifier = words[idx - 1] if idx > 0 and words[idx - 1] not in _WEAPON_NOUNS else ""
    return (modifier + " " + base).strip() if modifier else base


def _derive_state_from_weapon(phrase: str) -> str:
    p = phrase.lower()
    if "sheathed" in p:
        return "sheathed"
    if "drawn" in p or "in hand" in p or "gripped" in p:
        return "drawn"
    return ""


def _derive_attachment(phrase: str) -> Tuple[str, str, Tuple[str, ...]]:
    p = phrase.lower()
    if "sheathed" in p:
        if "left hip" in p:
            return "sheathed", "hip scabbard", ("hilt visible at left hip",)
        if "right hip" in p:
            return "sheathed", "hip scabbard", ("hilt visible at right hip",)
        return "sheathed", "scabbard", ("sheathed blade visible",)
    return "", "", ()


def _derive_gender(scene_text: str) -> str:
    words = re.findall(r"[a-z]+", str(scene_text or "").lower())
    for w in words:
        if w in _GENDER_PRONOUNS:
            return _GENDER_PRONOUNS[w]
    return ""


# IDENTITY_PRODUCTION_PLUMBING_20260929: flag-gated identity authority hooks.
# ENABLE_IDENTITY_PRESERVATION OFF (source default) -> every hook below is inert and
# the legacy projection / lock / milestone behaviour is byte-identical.
def _identity_on() -> bool:
    from tools.identity_preservation import is_identity_preservation_enabled
    return is_identity_preservation_enabled()


def _identity_record_gender(name: str, scene_text: str) -> str:
    """Legacy: scene-pronoun inference. Identity ON: sealed contract sex only (never pronouns)."""
    if not _identity_on():
        return _derive_gender(scene_text)
    from tools.identity_preservation import contract_sex_for_record
    return contract_sex_for_record(name)


def _identity_record_age(name: str, canon_age: str) -> str:
    """Identity ON: governed TEXT_CANON age (Jarek 16) replaces the absent/legacy YAML age."""
    if not _identity_on():
        return canon_age
    from tools.identity_preservation import contract_age_presentation
    return contract_age_presentation(name) or canon_age


def _as_str(v: Any, warnings: Optional[List[str]] = None, name: str = "?") -> str:
    """Coerce a canon value to a string without mutating the source."""
    if isinstance(v, dict):
        if warnings is not None:
            warnings.append(
                f"canon malformed entry for '{name}': YAML parsed {v!r} as a "
                f"mapping (likely an unquoted value with parentheses); "
                f"coerced to a string."
            )
        return " ".join(f"{k} {val}" for k, val in v.items())
    return str(v or "").replace("_", " ").strip()


def _as_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        return [_as_str(v)] if v else []
    return [_as_str(item) for item in v]


# --------------------------------------------------------------------------- #
# Projection builders (read-only; surface diagnostics; mark unresolved)
# --------------------------------------------------------------------------- #


def _project_character(profile: Dict[str, Any], scene_text: str,
                       warnings: List[str]) -> CharacterVisualRecord:
    name = str(profile.get("name") or "?")
    ap = profile.get("appearance") or {}

    clothing = _as_list(profile.get("clothing", []) or [])
    weapons = _as_list(profile.get("weapons", []) or [])

    has_pos = any(w and not any(b in w.lower() for b in _NEG_WEAPON) for w in weapons)
    has_neg = any(any(b in w.lower() for b in _NEG_WEAPON) for w in weapons)
    if has_pos and has_neg:
        warnings.append(
            f"canon contradiction for '{name}': weapon list mixes a positive "
            f"weapon with a 'no weapon' exception; projection keeps positive "
            f"descriptors, verify canonical default."
        )

    canonical_weapons = tuple(_canon_weapon(w) for w in weapons)

    identity = (_as_str(ap.get("hair"), warnings, name), _as_str(ap.get("eyes"), warnings, name),
                _as_str(ap.get("body_type"), warnings, name), " ".join(clothing))
    if not any(identity):
        warnings.append(
            f"canon incomplete for '{name}': no hair/eyes/body/clothing resolved; "
            f"character lock may be insufficient for consistent generation."
        )

    age = _as_str(ap.get("age") or profile.get("age"), warnings, name)
    canon_age = _AGE_CANON.get(age.strip().lower(), age)

    return CharacterVisualRecord(
        character_id=name.lower().replace(" ", "_"),
        name=name,
        novel=str(profile.get("novel") or "").lower(),
        gender=_identity_record_gender(name, scene_text),
        age=_identity_record_age(name, canon_age),
        build=_as_str(ap.get("body_type") or profile.get("body_type"), warnings, name),
        hair=_as_str(ap.get("hair", {}).get("style") if isinstance(ap.get("hair"), dict) else ap.get("hair")),
        eyes=_as_str(ap.get("eyes", {}).get("color") if isinstance(ap.get("eyes"), dict) else ap.get("eyes")),
        clothing=tuple(clothing),
        weapons=canonical_weapons,
        magic_style=_as_str(profile.get("magic_style")),
        lighting_preference=_as_str(profile.get("lighting_preference")),
        identity_constraints=(),
        forbidden_changes=tuple(),
        warnings=tuple(warnings),
    )


def _project_location(loc: Dict[str, Any], warnings: List[str]) -> LocationVisualRecord:
    name = str(loc.get("name") or "")
    novel = str(loc.get("novel") or "").lower()
    arch = str(loc.get("architecture") or "").replace("_", " ").strip()
    if arch:
        arch = ", ".join(b for b in arch.split(",") if "banner" not in b.lower())
    state_bits: List[str] = []
    dmg = str(loc.get("damage_state", "")).replace("_", " ").strip()
    if dmg and dmg.lower() not in ("n/a", "none", ""):
        state_bits.append(dmg)
    for key in ("weather", "fog_density", "ambient_particles"):
        v = str(loc.get(key, "")).replace("_", " ").strip()
        if v and v.lower() not in ("n/a", "none", ""):
            state_bits.append(v)
    banners = str(loc.get("banners") or loc.get("decorations") or "").replace("_", " ").strip()
    return LocationVisualRecord(
        location_id=str(loc.get("id") or name.lower().replace(" ", "_")),
        name=name,
        novel=novel,
        architecture=tuple(b.strip() for b in arch.split(",") if b.strip()),
        environment_state=", ".join(dict.fromkeys(state_bits)),
        lighting=str(loc.get("lighting") or "").replace("_", " ").strip(),
        magic_effects=str(loc.get("magic_effects") or "").replace("_", " ").strip(),
        banners_decorations=tuple(b.strip() for b in banners.split(",") if b.strip()),
        warnings=tuple(warnings),
    )


def _palette_phrase(palette: Dict[str, Any]) -> str:
    if not isinstance(palette, dict):
        return ""
    named = {k: v for k, v in palette.items() if isinstance(v, str) and v.startswith("#")}
    bits = []
    for key in ("primary", "secondary", "accent", "shadow", "magic", "combat"):
        if key in named:
            bits.append(f"{key.replace('_', ' ')} {named[key]}")
    if not bits:
        for key in ("palette", "color_grading", "mood"):
            if isinstance(palette.get(key), str):
                return palette[key].replace("_", " ")
    return ", ".join(bits)


def _project_style(novel: str, palette: Dict[str, Any]) -> StyleProfile:
    genre = NOVEL_GENRE_LABEL.get(str(novel).lower(), "fantasy illustration")
    # The novel style doc nests its colors under a `palette` sub-key; extract the
    # inner palette so palette_phrase carries the intended visual semantics.
    inner = palette.get("palette", palette) if isinstance(palette, dict) else palette
    return StyleProfile(
        novel=str(novel).lower(),
        genre_label=genre,
        palette_phrase=_palette_phrase(inner),
        line_shading_behavior="",
        material_treatment="",
    )


def _object_owner_character_id(profile: Dict[str, Any]) -> str:
    """Owning character id for objects listed on a profile.

    Uses the profile name when present (same id formula as CharacterVisualRecord).
    An explicit profile character_id is used only if the name is absent. Never
    invents ownership from novel or from another character.
    """
    name = str(profile.get("name") or "").strip()
    if name:
        return name.lower().replace(" ", "_")
    explicit = str(profile.get("character_id") or "").strip()
    if explicit:
        return explicit.lower().replace(" ", "_")
    return ""


def _project_objects(profiles: List[Dict[str, Any]],
                     warnings: List[str]) -> List[ObjectVisualRecord]:
    """Derive object/weapon records from RAW canon weapon strings.

    State and attachment evidence are derived from the raw (cleaned) weapon
    phrase so canonicalization does not strip 'sheathed at left hip' detail.
    """
    objs: List[ObjectVisualRecord] = []
    for profile in profiles:
        # Tag the profile owner only. Do not invent cross-novel ownership:
        # no name and no character_id leaves the object unscored.
        owner_id = _object_owner_character_id(profile)
        weapons = _as_list(profile.get("weapons", []) or [])
        raw_weapons = profile.get("weapons", []) or []
        if not isinstance(raw_weapons, list):
            raw_weapons = [raw_weapons] if raw_weapons else []
        for idx, w in enumerate(weapons):
            raw = _clean_canon_token(w)
            canon = _canon_weapon(w)
            state = _derive_state_from_weapon(raw)
            atype, mechanism, evidence = _derive_attachment(raw)
            entry_id = owner_id
            raw_entry = raw_weapons[idx] if idx < len(raw_weapons) else None
            if isinstance(raw_entry, dict):
                explicit = str(raw_entry.get("character_id") or "").strip()
                if explicit:
                    entry_id = explicit.lower().replace(" ", "_")
            objs.append(ObjectVisualRecord(
                object_id=canon.lower().replace(" ", "_"),
                state=state,
                canonical_phrase=canon,
                attachment_type=atype,
                attachment_mechanism=mechanism,
                required_visible_evidence=evidence,
                character_id=entry_id,
            ))
    return objs


def _select_subject_names(records: Tuple[CharacterVisualRecord, ...], scene_text: str) -> Tuple[str, ...]:
    """Read-only subject selection: names present in scene_text, else all canon names.

    Pure consumption of already-projected character records; no canon I/O.
    """
    found = [c.name for c in records if c.name and c.name.lower() in str(scene_text or "").lower()]
    if found:
        return tuple(dict.fromkeys(found))
    if records:
        return tuple(dict.fromkeys(c.name for c in records))
    return ()


def select_subject_names(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Tuple[str, ...]:
    """Public read-only consumption helper: the Studio Bible subject names relevant
    to a scene, selected from an already-built projection. Safe to reuse; performs
    no canon I/O and mutates nothing."""
    return _select_subject_names(projection.characters, scene_text)


def _matched_subject_names(
    records: Tuple[CharacterVisualRecord, ...], scene_text: str
) -> Tuple[str, ...]:
    """Names that are ACTUALLY present in scene_text (no all-names fallback).

    The all-names fallback in _select_subject_names is unsafe for selection
    because it would resolve to characters[0] when nothing matches. This returns
    only genuinely scene-named subjects so callers can keep multi-character
    selection deterministic (and mark subjects unresolved otherwise)."""
    found = [c.name for c in records if c.name and c.name.lower() in str(scene_text or "").lower()]
    return tuple(dict.fromkeys(found))


def _resolve_primary_character(
    records: Tuple[CharacterVisualRecord, ...], scene_text: str, novel: str = ""
) -> Optional[CharacterVisualRecord]:
    """Authoritative subject resolver (single source of truth).

    Deterministic, order-invariant selection:
      1. Names present in scene_text win (scene-named identity).
      2. With no scene match and exactly one character, return that unambiguous
         record.
      3. With no scene match and multiple characters, fall back to the canon
         protagonist of the requested novel (the character whose canon `novel`
         matches). This is the authoritative canon-grounded selection for a
         per-novel request whose scene/prompt does not name a subject, so EN
         resolves its protagonist and HA resolves its protagonist instead of
         silently using characters[0].
      4. Otherwise return None (genuinely unresolved / ambiguous). A named
         character that is not in the records, and that is not the single
         protagonist of the request novel, does not resolve to another novel's
         record.
    """
    scoped = _records_for_novel(records, novel)
    matched = _matched_subject_names(scoped, scene_text)
    if matched:
        lowered = [m.lower() for m in matched]
        for c in scoped:
            if c.name and c.name.lower() in lowered:
                return c
    if len(records) == 1:
        return records[0]
    nov = (novel or "").lower()
    if nov:
        protos = [c for c in records if (c.novel or "").lower() == nov]
        if len(protos) == 1:
            return protos[0]
    return None


def select_character_record(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Optional[CharacterVisualRecord]:
    """Resolve the scene-selected CharacterVisualRecord.

    Delegates to ``_resolve_primary_character`` so the same authoritative
    contract (scene-named identity, then novel-scoped protagonist) is reused
    everywhere. With multiple characters and no scene match and no single
    novel protagonist it returns None so the caller keeps the selection
    unresolved rather than silently picking [0].
    """
    return _resolve_primary_character(
        projection.characters, scene_text, projection.novel)


# Deterministic location alias cues (novel-scoped). First matching cue wins.
# "nexus city" is handled separately so it never collapses to en_nexus_pod.
_LOCATION_ALIAS_CUES: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    # (novel, cues, location_id)
    ("en", ("nexuspod", "nexus pod", "one-room apartment", "neon apartment", "apartment"), "en_nexus_pod"),
    ("en", ("portal chamber", "nexus portal", "portal"), "en_nexus_portal"),
    # City cues also handled by _en_city_alias_handled (preferred). Listed for
    # deterministic cue documentation; special-case runs first and never maps to pod.
    ("en", ("nexus city", "neon city", "nexus skyline", "neon skyline", "nexus urban", "neon urban", "city skyline"), "en_nexus_city"),
    ("ha", ("back alley", "rain-slick alley", "rainy alley", "convenience store", "alley"), "ha_alley"),
    ("hp", ("mountain sect", "sect courtyard", "jade hall", "sect"), "hp_sect"),
    ("hp", ("ancient ruins", "ruins"), "hp_ruins"),
    ("sf", ("soul-forge", "soul forge", "forge undercity", "undercity", "forge"), "sf_forge"),
    ("sf", ("sanctuary",), "sf_sanctuary"),
)

# Tokens that imply the scene names a setting. Unmatched imply -> fail closed
# (no pool[0] injection of an unrelated location such as en_nexus_pod).
_LOCATION_IMPLY_TOKENS: Tuple[str, ...] = (
    "city", "skyline", "street", "courtyard", "chamber", "apartment", "alley",
    "forge", "sect", "ruins", "sanctuary", "undercity", "portal", "temple",
    "hall", "pod", "nexuspod", "nexus pod", "plaza", "district", "tower",
    "mountain", "forest", "valley", "harbor", "dock", "station", "arena",
)


def _pool_by_id(pool: List[LocationVisualRecord], location_id: str) -> Optional[LocationVisualRecord]:
    want = (location_id or "").lower()
    for loc in pool:
        if (loc.location_id or "").lower() == want:
            return loc
    return None


def _scene_implies_location(scene_lower: str) -> bool:
    if not scene_lower:
        return False
    for tok in _LOCATION_IMPLY_TOKENS:
        if tok in scene_lower:
            return True
    return False


# EN city / skyline / urban cues (novel-scoped). Never map these to en_nexus_pod.
_EN_CITY_ALIAS_CUES: Tuple[str, ...] = (
    "nexus city",
    "neon city",
    "nexus skyline",
    "neon skyline",
    "nexus urban",
    "neon urban",
    "city skyline",
    "neon towers",
)


def _en_city_alias_handled(scene_lower: str) -> bool:
    """True when EN scene text intentionally names Nexus city / skyline / urban.

    Explicit apartment / NexusPod cues defer to the pod alias path.
    Portal-only scenes without city/skyline/urban do not count as city.
    """
    if not scene_lower:
        return False
    if "nexuspod" in scene_lower or "nexus pod" in scene_lower or "apartment" in scene_lower:
        return False
    for cue in _EN_CITY_ALIAS_CUES:
        if cue in scene_lower:
            return True
    # Bare novel-scoped "city" (word boundary; not portal; not undercity substring)
    # and bare "skyline".
    if "skyline" in scene_lower:
        return True
    if re.search(r"(?<![a-z])city(?![a-z])", scene_lower) and "portal" not in scene_lower:
        return True
    if re.search(r"(?<![a-z])urban(?![a-z])", scene_lower) and (
        "nexus" in scene_lower or "neon" in scene_lower
    ):
        return True
    return False


def _match_location_alias(
    novel: str, scene_lower: str, pool: List[LocationVisualRecord]
) -> Tuple[bool, Optional[LocationVisualRecord]]:
    """Return (handled, record).

    handled=True means an alias rule decided the outcome (including explicit
    unresolved for Nexus city with no city record). handled=False means no
    alias applied.
    """
    # EN Nexus city / neon skyline / urban -> en_nexus_city. NEVER en_nexus_pod.
    if novel == "en" and _en_city_alias_handled(scene_lower):
        hit = _pool_by_id(pool, "en_nexus_city")
        if hit is not None:
            return True, hit
        for loc in pool:
            blob = f"{loc.name or ''} {loc.location_id or ''}".lower()
            if "city" in blob and "pod" not in blob and "apartment" not in blob:
                return True, loc
        return True, None

    for nov, cues, loc_id in _LOCATION_ALIAS_CUES:
        if nov != novel:
            continue
        for cue in cues:
            if cue in scene_lower:
                hit = _pool_by_id(pool, loc_id)
                return True, hit
    return False, None


def select_location_record(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Optional[LocationVisualRecord]:
    """Resolve the scene-selected LocationVisualRecord (canon-grounded).

    Deterministic order:
      1. Prefer locations whose canon `novel` matches the request novel. This is
         the authoritative multi-location signal (an HA request never takes an
         EN location just because it is listed first) and is order-invariant.
      2. Within that novel-matched pool, prefer a location whose name or id
         appears in scene_text (longest name/id first).
      3. Deterministic alias matching (NexusPod/apartment, mountain sect,
         forge/undercity, alley, etc.). EN "Nexus city" / neon skyline / urban resolves to en_nexus_city
         when present, else unresolved - never en_nexus_pod.
      4. If the scene names/implies a setting that still does not match, fail
         closed (None). LOCATION_FALLBACK_REMOVED: no pool[0] injection for
         unmatched implied settings.
      5. Empty / non-implying scene text: first location in the novel pool
         (deterministic list order) — novel default only when no setting cue.

    If the request novel matches no location, return None (fail closed — no
    cross-novel leakage). Never invents a location absent from canon.
    """
    novel = (projection.novel or "").lower()
    locs = list(projection.locations)
    if not locs:
        return None
    pool = [l for l in locs if novel and (l.novel or "").lower() == novel] if novel else []
    if not pool:
        # Fail closed: never fall back to another novel's locations.
        if novel:
            return None
        pool = locs
    st = str(scene_text or "").lower()
    if st:
        # Longest name/id first so more specific labels win deterministically.
        ranked = sorted(
            pool,
            key=lambda l: (max(len(l.name or ""), len(l.location_id or "")), l.location_id or ""),
            reverse=True,
        )
        for l in ranked:
            nm = (l.name or "").lower()
            lid = (l.location_id or "").lower()
            if (nm and nm in st) or (lid and lid in st):
                return l
        handled, alias_hit = _match_location_alias(novel, st, pool)
        if handled:
            return alias_hit
        if _scene_implies_location(st):
            # Scene names/implies a setting that did not match — fail closed.
            return None
    # Empty scene or no location-implying cue: novel-pool default only.
    return pool[0]


def _scope_objects_to_character(
    objects: Tuple[ObjectVisualRecord, ...], character_id: str
) -> List[ObjectVisualRecord]:
    """Return only objects belonging to ``character_id``.

    Never falls back to the full multi-character object list: when no character
    is resolved (empty ``character_id``) or no object matches the resolved
    subject, the selection stays empty rather than leaking another novel's
    objects. An object with an empty character_id is not assigned to a selected
    character.
    """
    if not character_id:
        return []
    return [o for o in objects if o.character_id == character_id]


def _character_scoped_negative_guard(
    selected_records: List[CharacterVisualRecord],
) -> Tuple[str, ...]:
    """Existing Soulblade/sword negative guard, evaluated only on the selected character.

    Same tokens as the historical all-records check. Does not add physical-weapon
    or held-blade tokens. An unselected character's warnings cannot arm the guard.
    """
    if not selected_records:
        return ()
    notes = " ".join(str(c.warnings) for c in selected_records).lower()
    if "soulblade" in notes or "sword" in notes:
        return ("weapon became staff", "no spear", "no staff", "no polearm",
                "oversized weapon")
    return ()


def _records_for_novel(
    records: Tuple[CharacterVisualRecord, ...],
    novel: str,
) -> Tuple[CharacterVisualRecord, ...]:
    """Keep subject matching inside the requested novel when canon is tagged."""
    nov = (novel or "").lower()
    if not nov:
        return records
    scoped = tuple(c for c in records if (c.novel or "").lower() == nov)
    return scoped if scoped else records


def _subjects_for_selection(
    records: Tuple[CharacterVisualRecord, ...],
    scene_text: str,
    primary: Optional[CharacterVisualRecord],
) -> Tuple[str, ...]:
    scoped = _records_for_novel(records, primary.novel if primary else "")
    matched = _matched_subject_names(scoped, scene_text)
    if matched:
        return matched
    if primary:
        return (primary.name,)
    return ()



_DROP_VISUAL_TOKENS = frozenset({"", "n/a", "na", "none", "none physical", "null"})


def load_camera_intent_library() -> Dict[str, Dict[str, Any]]:
    data = _load_yaml(BIBLE_DIR / "camera_intents.yaml")
    if not isinstance(data, dict):
        return {}
    raw = data.get("camera_intents", data)
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def load_lighting_intent_library() -> Dict[str, Dict[str, Any]]:
    data = _load_yaml(BIBLE_DIR / "lighting_intents.yaml")
    if not isinstance(data, dict):
        return {}
    raw = data.get("lighting_intents", data)
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def load_cinematic_language() -> Dict[str, Dict[str, Any]]:
    data = _load_yaml(BIBLE_DIR / "cinematic_language.yaml")
    if not isinstance(data, dict):
        return {}
    raw = data.get("archetypes", data)
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): v
        for k, v in raw.items()
        if isinstance(v, dict) and k != "viewer_emotion"
    }


def _clip_visual_token(value: str) -> str:
    token = _clean_canon_token(value)
    token = " ".join(token.replace("_", " ").split())
    if token.casefold() in _DROP_VISUAL_TOKENS:
        return ""
    return token


# CLIP projection only. Canon YAML stays mashed tokens; these phrases keep
# ember / qi / HUD from collapsing into cyan lightning.
_GOLDEN_EMBER_CLIP = "small golden ember glow"
_AMBER_QI_CLIP = "thin amber qi threads, not lightning"
_PALE_BLUE_HUD_CLIP = (
    "separate translucent pale-blue rectangular system HUD"
)
_EFFECT_COLLISION_NEGATIVES = (
    "lightning bolts",
    "electric arcs",
    "cyan energy",
    "plasma",
    "energy beam",
)
_WARDROBE_HALLUCINATION_NEGATIVES = (
    "hoodie",
    "jacket",
    "backpack",
    "coat",
)


def _project_effect_clip(token: str) -> str:
    blob = (token or "").casefold()
    if not blob:
        return ""
    if "golden ember core amber qi threads" in blob:
        return f"{_GOLDEN_EMBER_CLIP}, {_AMBER_QI_CLIP}"
    if "pale-blue hud" in blob or "pale blue hud" in blob:
        return _PALE_BLUE_HUD_CLIP
    if "hud panel" in blob and "pale" in blob:
        return _PALE_BLUE_HUD_CLIP
    return token


def _effect_collision_negatives(character: Optional[CharacterVisualRecord]) -> Tuple[str, ...]:
    magic = _clip_visual_token(character.magic_style if character is not None else "")
    bits: List[str] = []
    if "golden ember core amber qi threads" in magic.casefold():
        bits.extend(_EFFECT_COLLISION_NEGATIVES)
    garments = " ".join(
        _clip_visual_token(g)
        for g in (character.clothing if character is not None else ())
    ).casefold()
    if "gray shirt" in garments:
        bits.extend(_WARDROBE_HALLUCINATION_NEGATIVES)
    return tuple(bits)


# Diagnostic still retained on disk; not auto-bound into CHARACTER_REFS.
# Milestone YAML assets continue to bind STYLE_REFS only via
# _milestone_style_bindings. Do not delete test_kai_ha.png.
_KAI_APPROVED_REFERENCE = Path(
    "C:/Users/David/Documents/Automation tool/loras/realistic_posts/test_kai_ha.png"
)


def _character_reference_bindings(
    primary: Optional[CharacterVisualRecord],
) -> Tuple[ReferenceBinding, ...]:
    """No hardcoded diagnostic CHARACTER_REFS auto-bind.

    Closed milestone assets enter STYLE_REFS only. Kai CHARACTER_REFS defaults
    to empty; other novels remain unbound. Does not invent a new face.
    """
    return ()


def retrieve_milestone_visual_reference(
    novel: str,
    character_id: str,
) -> Optional[MilestoneVisualReference]:
    """Load a milestone visual reference. Never full canon. Missing file = None."""
    novel_id = normalize_novel_id(novel, empty_ok=True)
    wanted = (character_id or "").strip().casefold()
    if not novel_id or not wanted:
        return None
    refs_dir = VISUAL_REFS_DIR
    if not refs_dir.is_dir():
        return None
    for path in sorted(refs_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if not isinstance(data, dict):
            continue
        if str(data.get("novel") or "").strip().casefold() != novel_id:
            continue
        cid = str(data.get("character_id") or "").strip().casefold()
        if cid != wanted:
            continue
        asset = Path(str(data.get("asset_path") or ""))
        if not asset.is_file():
            return None
        authority = tuple(
            str(x) for x in (data.get("allowed_authority") or []) if str(x).strip()
        )
        noncanon = tuple(
            str(x) for x in (data.get("noncanon_attributes") or []) if str(x).strip()
        )
        return MilestoneVisualReference(
            novel=novel_id,
            character_id=cid,
            reference_class=str(
                data.get("reference_class") or "MILESTONE_VISUAL_REFERENCE"
            ),
            asset_path=str(asset),
            asset_sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),
            allowed_authority=authority,
            noncanon_attributes=noncanon,
            build_canon=bool(data.get("build_canon")),
            wardrobe_logo_canon=bool(data.get("wardrobe_logo_canon")),
            amber_qi_canon=bool(data.get("amber_qi_canon")),
            golden_core_canon=bool(data.get("golden_core_canon")),
            wardrobe_canon=bool(data.get("wardrobe_canon")),
            glyph_layout_canon=bool(data.get("glyph_layout_canon")),
            exact_environment_geometry_canon=bool(
                data.get("exact_environment_geometry_canon")
            ),
        )
    return None


def _milestone_style_bindings(
    primary: Optional[CharacterVisualRecord],
) -> Tuple[ReferenceBinding, ...]:
    """Surface the milestone still on style_refs. Does not replace identity refs.

    Identity ON: never attached (NO_IDENTITY_REFERENCE_CONDITIONING). The milestone
    record itself is untouched and remains an audit / visual-direction reference
    (IdentitySpec.milestone_reference_id).
    """
    if primary is None:
        return ()
    if _identity_on():
        return ()
    rec = retrieve_milestone_visual_reference(primary.novel, primary.character_id)
    if rec is None:
        return ()
    return (
        ReferenceBinding(asset_path=rec.asset_path, asset_sha256=rec.asset_sha256),
    )


def identity_lock_phrase(character: Optional[CharacterVisualRecord]) -> str:
    """CLIP-safe hair / eyes / magic lock. No YAML keys, notes, or n/a."""
    if character is None:
        return ""
    bits: List[str] = []
    hair = _clip_visual_token(character.hair)
    if hair:
        bits.append(hair if "hair" in hair.lower() else f"{hair} hair")
    eyes = _clip_visual_token(character.eyes)
    if eyes:
        bits.append(eyes if "eye" in eyes.lower() else f"{eyes} eyes")
    build = _clip_visual_token(character.build)
    if build:
        bits.append(build)
    for garment in character.clothing:
        token = _clip_visual_token(garment)
        if token:
            bits.append(token)
    if any("gray shirt" in _clip_visual_token(g).casefold() for g in character.clothing):
        bits.append("faded printed logo on the shirt")
    magic = _project_effect_clip(_clip_visual_token(character.magic_style))
    if magic:
        bits.append(magic)
    return ", ".join(bits)


def identity_only_lock_phrase(character: Optional[CharacterVisualRecord]) -> str:
    """Identity ON lock: age / build / hair canon / eye canon / identity traits only.

    Governed characters use the TEXT_CANON identity contract; other characters keep
    only hair / eyes / build. No wardrobe, logo, accessories, weapons, props, HUD,
    glow, qi effects or environment.
    """
    if character is None:
        return ""
    from tools.identity_preservation import (
        get_identity_contract,
        identity_only_lock_phrase as _contract_lock,
        record_identity_only_lock,
    )
    contract = get_identity_contract(character.character_id or character.name)
    if contract is not None:
        return _contract_lock(contract)
    return record_identity_only_lock(
        _clip_visual_token(character.hair),
        _clip_visual_token(character.eyes),
        _clip_visual_token(character.build),
    )


def non_identity_descriptor_phrase(character: Optional[CharacterVisualRecord]) -> str:
    """The wardrobe / logo / effect tokens the legacy lock carried, unchanged.

    Identity ON only: routed to the existing non-identity content domain
    (content.narrative_intent) so wardrobe and effect prompt coverage is unchanged
    while the identity lock stays identity-only. WardrobeSpec (wardrobe lane),
    props / object identity (held-prop lane) are not touched.
    """
    if character is None:
        return ""
    bits: List[str] = []
    for garment in character.clothing:
        token = _clip_visual_token(garment)
        if token:
            bits.append(token)
    if any("gray shirt" in _clip_visual_token(g).casefold() for g in character.clothing):
        bits.append("faded printed logo on the shirt")
    magic = _project_effect_clip(_clip_visual_token(character.magic_style))
    if magic:
        bits.append(magic)
    return ", ".join(bits)


def _identity_mode_lock_and_effects(
    primary: Optional[CharacterVisualRecord], legacy_lock: str, magic_effects: str
) -> Tuple[str, str, str]:
    """(identity_lock, magic_effects, non_identity) for the current flag state."""
    if not _identity_on():
        return legacy_lock, magic_effects, ""
    lock = identity_only_lock_phrase(primary)
    non_identity = non_identity_descriptor_phrase(primary)
    effects = ", ".join(b for b in (non_identity, magic_effects) if b)
    return lock, effects, non_identity


def camera_intent_clip_phrase(intent_id: str, entry: Dict[str, Any]) -> str:
    label = str(intent_id or "").replace("_", " ").strip()
    if not label:
        return ""
    bits = [f"{label} shot"]
    lenses = entry.get("preferred_lenses") or []
    if isinstance(lenses, list) and lenses:
        bits.append(str(lenses[0]).replace("_", " "))
    composition = str(entry.get("composition") or "").replace("_", " ").strip()
    if composition:
        bits.append(composition)
    return ", ".join(bits)


def lighting_intent_clip_phrase(intent_id: str, entry: Dict[str, Any]) -> str:
    label = str(intent_id or "").replace("_", " ").strip()
    if not label:
        return ""
    bits = [f"{label} lighting"]
    temp = str(entry.get("color_temperature") or "").replace("_", " ").strip()
    if temp and temp.casefold() not in _DROP_VISUAL_TOKENS:
        bits.append(temp)
    vol = str(entry.get("volumetrics") or "").replace("_", " ").strip()
    if vol and vol.casefold() not in _DROP_VISUAL_TOKENS:
        bits.append(vol)
    return ", ".join(bits)


def _match_lighting_intent_id(text: str, library: Dict[str, Dict[str, Any]]) -> str:
    blob = _collapse_novel_key(text).replace("-", " ")
    compact = blob.replace(" ", "_")
    for intent_id in sorted(library, key=len, reverse=True):
        token = intent_id.replace("_", " ")
        if token and token in blob:
            return intent_id
        if intent_id and intent_id in compact:
            return intent_id
    return ""


def _normalize_policy_cue(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").split()).casefold()


def _scene_blob(scene_text: str) -> str:
    return _normalize_policy_cue(scene_text)


def _cue_in_scene(cue: Any, scene_blob: str) -> bool:
    token = _normalize_policy_cue(cue)
    return bool(token) and token in scene_blob


def _list_of_cues(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if value:
        return [str(value)]
    return []


def _camera_when_to_use_hit(
    intent_id: str,
    entry: Dict[str, Any],
    scene_blob: str,
) -> bool:
    if not scene_blob:
        return False
    if any(_cue_in_scene(cue, scene_blob) for cue in _list_of_cues(entry.get("avoid_when"))):
        return False
    return any(_cue_in_scene(cue, scene_blob) for cue in _list_of_cues(entry.get("when_to_use")))


def _bible_default_camera_id(cameras: Dict[str, Dict[str, Any]]) -> str:
    """First camera intent in Bible order tagged when_to_use: default."""
    token = _normalize_policy_cue(BIBLE_DEFAULT_WHEN_TO_USE_TOKEN)
    for intent_id, entry in cameras.items():
        tags = {_normalize_policy_cue(c) for c in _list_of_cues(entry.get("when_to_use"))}
        if token in tags:
            return intent_id
    return ""


def _first_library_id(candidates: Any, library: Dict[str, Dict[str, Any]]) -> str:
    for candidate in _list_of_cues(candidates):
        if candidate in library:
            return candidate
    return ""


def _archetype_id_in_scene(
    scene_blob: str,
    language: Dict[str, Dict[str, Any]],
) -> str:
    if not scene_blob:
        return ""
    for archetype_id, entry in language.items():
        if not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("camera"), list):
            continue
        if _cue_in_scene(archetype_id, scene_blob):
            return archetype_id
    return ""


def _archetype_for_camera(
    camera_id: str,
    language: Dict[str, Dict[str, Any]],
) -> str:
    if not camera_id:
        return ""
    for archetype_id, entry in language.items():
        if not isinstance(entry, dict):
            continue
        cameras = _list_of_cues(entry.get("camera"))
        if camera_id in cameras:
            return archetype_id
    return ""


def select_cinematography(
    scene_text: str,
    character: Optional[CharacterVisualRecord],
    location: Optional[LocationVisualRecord],
) -> Tuple[CameraIntent, LightingIntent, str]:
    """Select camera/lighting/shot from loaded Studio Bible records.

    Creative policy is the YAML. This function only matches scene text against
    Bible when_to_use lists, archetype ids, and lighting intent ids, in Bible
    file order. Unmatched scenes use the camera intent the Bible tags
    when_to_use: default, or stay unresolved if no such tag exists.
    """
    cameras = load_camera_intent_library()
    lights = load_lighting_intent_library()
    language = load_cinematic_language()
    empty_cam = CameraIntent()
    empty_lit = LightingIntent()
    if not cameras and not lights:
        return empty_cam, empty_lit, ""

    scene_blob = _scene_blob(scene_text)

    camera_from_when_to_use = ""
    for intent_id, entry in cameras.items():
        if _camera_when_to_use_hit(intent_id, entry, scene_blob):
            camera_from_when_to_use = intent_id
            break

    archetype_id = _archetype_id_in_scene(scene_blob, language)
    arch: Dict[str, Any] = language.get(archetype_id) if archetype_id else {}
    if not isinstance(arch, dict):
        arch = {}

    camera_id = ""
    if archetype_id:
        arch_cameras = _list_of_cues(arch.get("camera"))
        if camera_from_when_to_use and camera_from_when_to_use in arch_cameras:
            camera_id = camera_from_when_to_use
        else:
            camera_id = _first_library_id(arch_cameras, cameras)
    if not camera_id:
        camera_id = camera_from_when_to_use
    if not camera_id:
        camera_id = _bible_default_camera_id(cameras)
    if not archetype_id:
        archetype_id = _archetype_for_camera(camera_id, language)
        arch = language.get(archetype_id) if archetype_id else {}
        if not isinstance(arch, dict):
            arch = {}

    # Named-character identity scenes must not keep tiny-subject cameras unless
    # the scene explicitly asks for scale/lost-in-world framing. Wide shots stay
    # in the library for wasteland/exile/cityscape/arena/battlefield.
    if character is not None and camera_id:
        probe = cameras.get(camera_id) or {}
        if _normalize_policy_cue(probe.get("composition")) == "tiny subject":
            explicit_scale = any(
                _cue_in_scene(cue, scene_blob)
                for cue in ("wasteland", "exile", "cityscape", "arena", "battlefield")
            )
            if not explicit_scale:
                camera_id = _bible_default_camera_id(cameras)
                if camera_id:
                    archetype_id = _archetype_for_camera(camera_id, language) or archetype_id
                    arch = language.get(archetype_id) if archetype_id else {}
                    if not isinstance(arch, dict):
                        arch = {}

    lighting_id = _first_library_id(arch.get("lighting"), lights)
    loc_light = _clip_visual_token(location.lighting if location is not None else "")
    pref = _clip_visual_token(character.lighting_preference if character is not None else "")
    if not lighting_id:
        lighting_id = _match_lighting_intent_id(
            " ".join((loc_light, pref, scene_text or "")), lights
        )

    cam_entry = cameras.get(camera_id) or {}
    lit_entry = lights.get(lighting_id) or {}
    camera = (
        CameraIntent(intent_id=camera_id, description=camera_intent_clip_phrase(camera_id, cam_entry))
        if camera_id
        else empty_cam
    )
    lighting = (
        LightingIntent(
            intent_id=lighting_id,
            description=lighting_intent_clip_phrase(lighting_id, lit_entry),
        )
        if lighting_id
        else empty_lit
    )
    shot_bits: List[str] = []
    lenses = arch.get("lens") if isinstance(arch.get("lens"), list) else []
    if not lenses:
        lenses = cam_entry.get("preferred_lenses") or []
    if lenses:
        shot_bits.append(str(lenses[0]).replace("_", " "))
    movement = str(cam_entry.get("movement") or "").replace("_", " ").strip()
    if movement:
        shot_bits.append(movement)
    return camera, lighting, ", ".join(shot_bits)


def lighting_clip_phrase(
    location: Optional[LocationVisualRecord],
    character: Optional[CharacterVisualRecord],
    lighting_intent: LightingIntent,
) -> str:
    bits: List[str] = []
    loc_light = _clip_visual_token(location.lighting if location is not None else "")
    if loc_light:
        bits.append(loc_light)
    pref = _clip_visual_token(character.lighting_preference if character is not None else "")
    blob = " ".join(bits).casefold()
    if pref and pref.casefold() not in blob:
        bits.append(pref)
    intent_phrase = (lighting_intent.description or "").strip()
    if intent_phrase and intent_phrase.casefold() not in " ".join(bits).casefold():
        bits.append(intent_phrase)
    return ", ".join(bits)


def clip_cinematography_clauses(spec: GenerationSpec) -> Tuple[str, ...]:
    """CLIP clauses from existing GenerationSpec composition/style fields."""
    bits: List[str] = []
    focal = str(getattr(spec.composition, "focal_point", "") or "").strip()
    if focal:
        bits.append(focal)
    camera = str(getattr(spec.composition, "camera", "") or "").strip()
    if camera:
        bits.append(camera)
    distance = str(getattr(spec.composition, "shot_distance", "") or "").strip()
    if distance and distance.casefold() not in camera.casefold():
        bits.append(distance)
    framing = str(getattr(spec.composition, "framing", "") or "").strip()
    if framing and framing.casefold() not in " ".join(bits).casefold():
        bits.append(framing)
    lighting = str(
        getattr(spec.style, "lighting_design", "")
        or getattr(spec.conditioning, "lighting", "")
        or ""
    ).strip()
    if lighting:
        bits.append(lighting)
    magic = str(getattr(spec.content, "narrative_intent", "") or "").strip()
    if magic and magic.casefold() not in " ".join(bits).casefold():
        bits.append(magic)
    return tuple(bits)


def derive_spec_inputs(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Dict[str, Any]:
    """Read-only consumption of a StudioBibleProjection into the GenerationSpec
    field values the V2 pipelines should populate.

    This does NOT mutate the projection or the GenerationSpec; it returns a plain
    dict of canon-derived values that the caller merges into its own
    GenerationSpec construction (preserving each pipeline's asset/router contract).
    The projection logic (canon reading + canonicalization) stays inside the
    adapter; this only reads an already-built projection.
    """
    # Scene-selected subject and location. Never characters[0] / locations[0].
    primary = select_character_record(projection, scene_text)
    loc = select_location_record(projection, scene_text)
    style = projection.styles[0] if projection.styles else None
    primary_char_id = primary.character_id if primary else ""
    scoped = _scope_objects_to_character(projection.objects, primary_char_id)
    obj = scoped[0] if scoped else None

    if obj and obj.state == "sheathed":
        object_class = "sheathed_sword"
    elif obj and obj.state == "drawn":
        object_class = "drawn_sword"
    elif obj:
        object_class = "object"
    else:
        object_class = ""

    subjects = _subjects_for_selection(projection.characters, scene_text, primary)
    props = tuple(
        o.canonical_phrase
        for o in scoped
        if _clip_visual_token(o.canonical_phrase)
    )
    negative = tuple(
        dict.fromkeys(
            list(projection.negative_constraints.canon)
            + list(_character_scoped_negative_guard([primary] if primary else []))
        )
    )
    camera, lighting_intent, shot_language = select_cinematography(
        scene_text, primary, loc
    )
    identity_lock = identity_lock_phrase(primary)
    lighting_phrase = lighting_clip_phrase(loc, primary, lighting_intent)
    magic_effects = _project_effect_clip(
        _clip_visual_token(loc.magic_effects if loc is not None else "")
    )
    identity_lock, magic_effects, _non_identity = _identity_mode_lock_and_effects(
        primary, identity_lock, magic_effects
    )
    negative = tuple(
        dict.fromkeys(
            list(negative) + list(_effect_collision_negatives(primary))
        )
    )

    return {
        "character_id": primary_char_id,
        "subjects": subjects,
        "environment": loc.name if loc else "",
        "props": props,
        "palette": style.palette_phrase if style else "",
        "lighting_design": loc.lighting if loc else "",
        "object_class": object_class,
        "object_state": obj.state if obj else "",
        "object_identity": obj.canonical_phrase if obj else "",
        "lighting": loc.lighting if loc else "",
        "negative_constraints": negative,
        "unresolved_fields": tuple(projection.unresolved_fields),
        "canon_warnings": tuple(projection.canon_warnings),
        "hair": _clip_visual_token(primary.hair) if primary else "",
        "eyes": _clip_visual_token(primary.eyes) if primary else "",
        "magic_style": _clip_visual_token(primary.magic_style) if primary else "",
        "magic_effects": magic_effects,
        "identity_lock": identity_lock,
        "camera_phrase": camera.description,
        "shot_language": shot_language,
        "lighting_phrase": lighting_phrase,
        "camera_intent_id": camera.intent_id,
        "lighting_intent_id": lighting_intent.intent_id,
        **({"non_identity_descriptors": _non_identity} if _identity_on() else {}),
    }


def build_projection(novel: str, chapter: str, scene_text: str) -> StudioBibleProjection:
    """Read-only projection of Studio Bible canon for image generation.

    Missing canonical data is represented as absent/unresolved. Canon diagnostics
    are surfaced in `canon_warnings` and per-record `warnings`, never dropped.

    Live callers may pass full titles (NOVEL_NAMES); they are normalized to the
    Studio Bible short id before any canon lookup. Unknown titles fail closed.
    """
    warnings: List[str] = []
    unresolved: List[str] = []
    # Normalize before any short-id keyed lookup (palette / novel scoping).
    novel = normalize_novel_id(novel, empty_ok=True)

    profiles = load_character_profiles()
    if not profiles:
        unresolved.append("characters")
    # load_character_profiles returns duplicate values for full-name + first-token
    # alias keys (same dict object). Dedupe by identity so each canon character
    # projects exactly once.
    unique_profiles = list({id(p): p for p in profiles.values()}.values())
    locations = load_locations()
    palette = load_novel_palette(novel)

    char_records = [_project_character(p, scene_text, warnings)
                    for p in unique_profiles]
    # R21: legacy_prose_match: false entries are structured-authority-only and never enter the legacy
    # prose-selection projection (missing field == true, existing behavior preserved).
    loc_records = [_project_location(l, warnings) for l in locations
                   if not (isinstance(l, dict) and l.get("legacy_prose_match", True) is False)]
    style_records = [_project_style(novel, palette)] if palette else []
    if not palette:
        unresolved.append("style.palette")

    # Scene-named identity, then the request-novel protagonist. Not characters[0].
    primary = _resolve_primary_character(tuple(char_records), scene_text, novel)
    if char_records and primary is None:
        unresolved.append("content.subjects")

    obj_records = _project_objects(unique_profiles, warnings)

    neg_canon = CANON_NEGATIVE_CONSTRAINTS
    # Existing Soulblade/sword guard, scoped to the selected character only.
    neg_per = _character_scoped_negative_guard([primary] if primary else [])

    if not loc_records:
        unresolved.append("content.environment")
    if not obj_records:
        unresolved.append("conditioning.object_identity")

    loc_for_cine = select_location_record(
        StudioBibleProjection(
            novel=str(novel).lower(),
            locations=tuple(loc_records),
        ),
        scene_text,
    )
    cam_rec, lit_rec, _shot = select_cinematography(scene_text, primary, loc_for_cine)

    return StudioBibleProjection(
        novel=str(novel).lower(),
        chapter=str(chapter),
        scene_text=scene_text,
        characters=tuple(char_records),
        locations=tuple(loc_records),
        styles=tuple(style_records),
        objects=tuple(obj_records),
        camera_intents=(cam_rec,) if cam_rec.intent_id else (),
        lighting_intents=(lit_rec,) if lit_rec.intent_id else (),
        render_rules=RenderRules(),
        negative_constraints=NegativeConstraints(canon=neg_canon, per_character=neg_per),
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        canon_warnings=tuple(dict.fromkeys(warnings)),
    )


# --------------------------------------------------------------------------- #
# Projection -> GenerationSpec (consume contract; never mutate it)
# --------------------------------------------------------------------------- #


def projection_sha256(projection: StudioBibleProjection) -> str:
    import hashlib
    return hashlib.sha256(
        canonical_serialize_obj(_to_jsonable(projection)).encode("utf-8")
    ).hexdigest()


def _to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj



# WARDROBE_AUTO_ATTACHMENT_PLUMBING_20260924
def _apply_wardrobe_auto_attach(spec, *, character_id: str = "", novel_id: str = "", wardrobe_explicit=None, variant=None):
    """Flag-gated TEXT_CANON wardrobe auto-attach (ENABLE_WARDROBE_PRESERVATION)."""
    from tools.wardrobe_preservation import apply_auto_attached_wardrobe
    return apply_auto_attached_wardrobe(
        spec,
        character_id=character_id or "",
        novel_id=novel_id or "",
        wardrobe_explicit=wardrobe_explicit,
        variant=variant,
    )


# IDENTITY_PRODUCTION_PLUMBING_20260929
def _apply_identity_auto_attach(spec, *, character_id: str = "", novel_id: str = ""):
    """Flag-gated TEXT_CANON identity attach (ENABLE_IDENTITY_PRESERVATION). OFF: same object."""
    from tools.identity_preservation import apply_identity_to_generation_spec
    return apply_identity_to_generation_spec(spec, character_id=character_id or "", novel_id=novel_id or "")


def project_to_generation_spec(
    projection: StudioBibleProjection,
    pipeline: str = "",
    seed: int = 1_000_003,
    scene_text: str = "",
) -> GenerationSpec:
    """Map a StudioBibleProjection onto a GenerationSpec.

    Consumes the M1 contract: fills only canon-derived fields. Missing data stays
    absent/unresolved (empty), and the unresolved set is carried into the spec's
    provenance via `identity.reference_bindings` is NOT used for that; instead
    unresolved fields are returned alongside (see return note). The pipeline is
    supplied by the deterministic router (a later stage), defaulting to unresolved.

    Enforces M1_CONTRACT_MUTATION_AUTHORIZED=False: every target path must already
    exist on GenerationSpec, else ContractIncompatibilityError (exact path).
    """
    _require_contract_paths(REQUIRED_CONTRACT_PATHS)

    primary = select_character_record(projection, scene_text)
    loc = select_location_record(projection, scene_text)
    style = projection.styles[0] if projection.styles else None
    primary_char_id = primary.character_id if primary else ""
    scoped = _scope_objects_to_character(projection.objects, primary_char_id)
    obj = scoped[0] if scoped else None
    subjects = _subjects_for_selection(projection.characters, scene_text, primary)
    camera, lighting_intent, shot_language = select_cinematography(
        scene_text, primary, loc
    )
    identity_lock = identity_lock_phrase(primary)
    lighting_phrase = lighting_clip_phrase(loc, primary, lighting_intent)
    magic_effects = _project_effect_clip(
        _clip_visual_token(loc.magic_effects if loc is not None else "")
    )
    identity_lock, magic_effects, _non_identity = _identity_mode_lock_and_effects(
        primary, identity_lock, magic_effects
    )

    identity = IdentitySpec(
        character_id=primary.character_id if primary else "",
        character_version=primary.version if primary else "",
        studio_bible_binding=StudioBibleBinding(snapshot_ref="", snapshot_sha256=""),
        reference_bindings=_character_reference_bindings(primary),
    )

    content = ContentSpec(
        subjects=subjects,
        action="",
        environment=loc.name if loc else "",
        props=tuple(o.canonical_phrase for o in scoped),
        narrative_intent=magic_effects,
    )

    style_spec = StyleSpec(
        pipeline=pipeline,
        style_profile=style.genre_label if style else "",
        palette=style.palette_phrase if style else "",
        lighting_design=lighting_phrase or (loc.lighting if loc else ""),
    )

    conditioning = ConditioningSpec(
        object_class=("sheathed_sword" if obj and obj.state == "sheathed"
                      else "drawn_sword" if obj and obj.state == "drawn"
                      else "object" if obj else ""),
        object_state=obj.state if obj else "",
        object_identity=obj.canonical_phrase if obj else "",
        lighting=lighting_phrase or (loc.lighting if loc else ""),
        negative_constraints=tuple(
            dict.fromkeys(
                list(projection.negative_constraints.canon)
                + list(_character_scoped_negative_guard([primary] if primary else []))
                + list(_effect_collision_negatives(primary))
            )
        ),
    )

    attachment = AttachmentSpec(
        attachment_type=obj.attachment_type if obj else "",
        mechanism=obj.attachment_mechanism if obj else "",
        required_visible_evidence=obj.required_visible_evidence if obj else (),
    )

    references = ReferenceSpec(
        character_refs=_character_reference_bindings(primary),
        style_refs=_milestone_style_bindings(primary),
    )
    composition = CompositionSpec(
        camera=camera.description,
        shot_distance=shot_language,
        framing=shot_language,
        focal_point=identity_lock,
    )

    return _apply_identity_auto_attach(_apply_wardrobe_auto_attach(
        GenerationSpec(
        identity=identity,
        content=content,
        style=style_spec,
        composition=composition,
        conditioning=conditioning,
        attachment=attachment,
        references=references,
        run=RunConfig(seed=seed),
    ),
        character_id=(primary.character_id if primary else ""),
        novel_id=(projection.novel or ""),
    ),
        character_id=(primary.character_id if primary else ""),
        novel_id=(projection.novel or ""),
    )
