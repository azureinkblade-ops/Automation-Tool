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

NOVEL_STYLE_FILE = {"en": "en.yaml", "ha": "ha.yaml", "hp": "hp.yaml", "sf": "sf.yaml"}
NOVEL_GENRE_LABEL = {
    "hp": "xianxia cultivation fantasy illustration",
    "en": "cyberpunk mystic fantasy illustration",
    "sf": "ashpunk industrial fantasy illustration",
    "ha": "system fantasy illustration",
}

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
    novel: str = ""  # owning novel (canon `novel` key); enables novel-scoped selection
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
    novel: str = ""  # owning novel (canon `novel` key); enables scene-scoped selection
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
    character_id: str = ""  # owning character (for cross-character scoping)
    is_effect: bool = False  # True => non-physical qi manifestation (not a wielded object)
    warnings: Tuple[str, ...] = ()


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
    fname = NOVEL_STYLE_FILE.get(str(novel).lower())
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


# --------------------------------------------------------------------------- #
# Conditioning-facing descriptor projection (canon stays authoritative)
# --------------------------------------------------------------------------- #
# Canon descriptor tokens occasionally carry an AUTHORING annotation of the form
# "(NOTE: <legacy renderer workaround>)", e.g. kael.yaml clothing carries
# "Soulblade_at_side (NOTE: SDXL drops held blades, accept)". Such a note is a
# legacy model-workaround remark for a human reader; it is NOT a canon fact and
# NOT a render instruction. When it reaches positive CLIP conditioning it
# actively grants the renderer permission to omit the held object, which
# contradicts a scene whose structural contract requires a grip/wield.
#
# These helpers filter only the CONDITIONING-FACING projection. The canon
# records (and therefore projection_sha256) keep the descriptor exactly as canon
# supplies it, so canon remains authoritative and nothing is erased upstream.
_LEGACY_AUTHORING_NOTE_PATTERNS = (
    re.compile(r"\(\s*NOTE\b[^)]*\)", re.IGNORECASE),   # balanced "(NOTE: ...)"
    re.compile(r"\(\s*NOTE\b.*$", re.IGNORECASE),       # unbalanced tail
)

# Resting / carry LAYOUT tokens: where a physical object sits when it is NOT
# being actively used. A default layout convention, never a canon identity fact.
_RESTING_CARRY_LAYOUT_TOKENS = (
    "at side", "at the side", "at hip", "on hip", "at waist", "on back",
    "sheathed", "scabbard", "holstered", "slung", "stowed", "strapped",
)

# Scene object states that REQUIRE an active hand-to-object interaction.
_GRIP_INTERACTION_OBJECT_STATES = (
    "drawn", "held", "holding", "gripped", "grip", "wielded", "wielding",
    "in hand", "raised",
)


def strip_legacy_authoring_notes(value: Any) -> str:
    """Drop "(NOTE: ...)" authoring annotations from a canon descriptor token.

    The canon descriptor itself is preserved verbatim; only the parenthesised
    authoring note is removed, so a legitimate canon fact is never erased.
    """
    v = str(value or "")
    for pattern in _LEGACY_AUTHORING_NOTE_PATTERNS:
        v = pattern.sub("", v)
    return re.sub(r"\s{2,}", " ", v).strip().strip(",").strip()


def scene_requires_grip_interaction(
    object_identity: str = "", object_state: str = ""
) -> bool:
    """True when the scene's own object contract requires an active grip/wield.

    Requires BOTH a physical object identity and an active object state, so a
    no-physical-object subject (HA / Kai) can never be read as requiring a grip.
    """
    if not str(object_identity or "").strip():
        return False
    state = str(object_state or "").strip().lower().replace("_", " ")
    if not state:
        return False
    return any(token in state for token in _GRIP_INTERACTION_OBJECT_STATES)


def is_resting_carry_layout_descriptor(
    descriptor: str, object_identity: str = ""
) -> bool:
    """True when a descriptor is a resting/carry LAYOUT for the scene's object.

    Only descriptors that name the scene's own physical object AND place it in a
    resting/carry position qualify (e.g. "Soulblade_at_side"). Generic clothing
    and unrelated accessories are never matched.
    """
    d = str(descriptor or "").strip().lower().replace("_", " ")
    obj = str(object_identity or "").strip().lower().replace("_", " ")
    if not d or not obj or obj not in d:
        return False
    return any(token in d for token in _RESTING_CARRY_LAYOUT_TOKENS)


def conditioning_clothing_descriptors(
    clothing: Any,
    *,
    object_identity: str = "",
    object_state: str = "",
) -> Tuple[str, ...]:
    """Project canon clothing descriptors for POSITIVE CONDITIONING use.

    Two narrow, evidence-backed filters, in order:

    1. Legacy authoring "(NOTE: ...)" annotations are stripped. They are not
       canon and must never enter renderer conditioning.
    2. When the scene's own object contract requires an active grip/wield, the
       DEFAULT RESTING/CARRY LAYOUT descriptor for that same object is dropped
       for that generation. The canon identity fact (the object exists and
       belongs to the subject) is carried by
       ``conditioning.object_identity`` / the wielding fragment, so nothing
       canonical is lost — only the contradictory layout instruction.

    When the scene does NOT require a grip, the resting-carry layout descriptor
    is preserved unchanged (it is the legitimate default layout).
    """
    grip_required = scene_requires_grip_interaction(object_identity, object_state)
    out: List[str] = []
    for token in tuple(clothing or ()):
        cleaned = strip_legacy_authoring_notes(token)
        if not cleaned:
            continue
        if grip_required and is_resting_carry_layout_descriptor(cleaned, object_identity):
            continue
        out.append(cleaned)
    return tuple(out)


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


# Mapping from a recognized canon weapon-class token to an ordinary-language
# grounding class that SDXL can interpret. This is CLASS grounding only (what
# kind of object the canon name denotes), never a visual appearance (shape,
# material, color, glow). Used to attach an interpretable class to an otherwise
# opaque canon object name without fabricating visual detail.
_WEAPON_CLASS_MAP = (
    ("soulblade", "blade"),
    ("blade", "blade"),
    ("sword", "sword"),
    ("jian", "sword"),
    ("katana", "sword"),
    ("saber", "sword"),
    ("sabre", "sword"),
    ("staff", "staff"),
    ("bow", "bow"),
    ("spear", "spear"),
    ("axe", "axe"),
    ("fan", "fan"),
    ("horn", "horn"),
)


def _derive_weapon_class(phrase: str) -> str:
    """Derive a truthful ordinary-language object class from a canon weapon phrase.

    Returns the grounding class (e.g. "blade", "sword") when the canon phrase
    itself contains a recognizable weapon-class token, otherwise "". The class is
    derivable from the canon name only (e.g. "Soulblade" embeds "blade"; "qi
    blade" embeds "blade"); it never invents shape/material/color/geometry. An
    empty result means no faithful class could be derived, in which case the
    caller keeps the generic "object" placeholder rather than fabricating one.
    """
    p = _clean_canon_token(phrase).lower()
    words = [w for w in re.split(r"[\s,]+", p) if w]
    if not words:
        return ""
    for token, cls in _WEAPON_CLASS_MAP:
        if token in words:
            return cls
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


def _classify_weapon(canonical_phrase: str) -> str:
    """Classify a canon weapon string for object/effect projection.

    Returns one of:
      - "constraint": a non-physical marker (e.g. ``none_physical (Qi_based)``).
        This is NOT a rendered object and NOT an effect; it is a contract that
        the character wields no physical weapon.
      - "effect": a non-physical qi manifestation (e.g. ``amber_qi_threads``,
        ``golden ember core``). Rendered as a visible effect, never "wielded".
      - "object": a physical weapon/object (e.g. ``Soulblade``).
    """
    low = canonical_phrase.lower()
    if "none physical" in low or low.startswith("none ") or "no physical" in low:
        return "constraint"
    if "amber qi" in low or "qi thread" in low or "golden ember" in low or "golden_ember" in low:
        return "effect"
    return "object"


def _derive_gender(scene_text: str) -> str:
    words = re.findall(r"[a-z]+", str(scene_text or "").lower())
    for w in words:
        if w in _GENDER_PRONOUNS:
            return _GENDER_PRONOUNS[w]
    return ""


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
        gender=_derive_gender(scene_text),
        age=canon_age,
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


def _project_objects(profiles: List[Dict[str, Any]],
                      warnings: List[str]) -> List[ObjectVisualRecord]:
    """Derive object/weapon/effect records from RAW canon weapon strings.

    Consumes the raw (un-canonicalized) profile weapon strings so state and
    attachment evidence (e.g. 'sheathed at left hip') are not stripped by
    canonicalization. Each weapon is classified (constraint / effect / object)
    and tagged with the owning character so later selection can be scoped to the
    requested subject (no cross-character object contamination). A
    ``none_physical`` marker is a constraint, not a rendered object; amber-qi /
    golden-ember manifestations are non-physical EFFECTS (never "wielded");
    everything else is a physical object.
    """
    objs: List[ObjectVisualRecord] = []
    for profile in profiles:
        cid = str(profile.get("name") or "").lower().replace(" ", "_")
        magic_style = str(profile.get("magic_style") or "")
        for w in _as_list(profile.get("weapons", []) or []):
            raw = _clean_canon_token(w)
            canon = _canon_weapon(w)
            kind = _classify_weapon(canon)
            if kind == "constraint":
                # none_physical: a contract that no physical weapon is wielded.
                # Not rendered as an object and not an effect.
                continue
            if kind == "effect":
                objs.append(ObjectVisualRecord(
                    object_id="effect_" + canon.lower().replace(" ", "_"),
                    canonical_phrase=canon,
                    character_id=cid,
                    is_effect=True,
                ))
                continue
            state = _derive_state_from_weapon(raw)
            atype, mechanism, evidence = _derive_attachment(raw)
            objs.append(ObjectVisualRecord(
                object_id=canon.lower().replace(" ", "_"),
                state=state,
                canonical_phrase=canon,
                attachment_type=atype,
                attachment_mechanism=mechanism,
                required_visible_evidence=evidence,
                character_id=cid,
                is_effect=False,
            ))
        # Golden-ember manifestation (authoritative: ha.yaml magic_effects
        # "golden_ember_core (chest)" + thumbnail "golden ember glowing in
        # chest" + studio_memory qi_state golden_ember_awake). Derived from the
        # canon magic_style token, never synthesized.
        ms = magic_style.lower()
        if "golden ember" in ms or "golden_ember" in ms:
            objs.append(ObjectVisualRecord(
                object_id="effect_golden_ember_core",
                canonical_phrase="golden ember glowing in chest",
                character_id=cid,
                is_effect=True,
            ))
    return objs


def _scope_objects_to_character(
    objects: Tuple[ObjectVisualRecord, ...], character_id: str
) -> List[ObjectVisualRecord]:
    """Return only objects belonging to ``character_id``.

    Never falls back to the full multi-character object list: when no character
    is resolved (empty ``character_id``) or no object matches the resolved
    subject, the selection stays empty rather than leaking another novel's
    objects/effects (e.g. a Kai request must never receive Kael's Soulblade, and
    an unresolved EN request must never receive Kai's amber qi / golden ember)."""
    if not character_id:
        return []
    return [o for o in objects if o.character_id == character_id]


def render_nonphysical_effects_fragment(
    subject_str: str, effects: Tuple[str, ...]
) -> str:
    """Render non-physical qi EFFECTS as visible manifestations explicitly bound
    to the scene-selected subject and to any canon-encoded spatial attachment.

    General contract (preserves subject -> effect -> spatial relationship when
    canon supplies it):
      - The fragment always begins with the canonical effect phrasing (e.g.
        'visible amber qi, golden ember glowing in chest') so the model's
        existing signal and downstream assertions are preserved.
      - When a subject is resolved, an explicit clarification is appended that
        binds the effects to that subject and to the canon-encoded body region
        ('in chest' -> "<subject>'s chest"), so the supernatural relationship is
        unambiguous (not merely scene lighting / color grading). It does not
        synthesize new weapons, clothing, locations, or character traits.
    """
    base = "visible " + ", ".join(effects)
    if not subject_str:
        return base
    subj = subject_str.split(",")[0].strip()
    if not subj:
        return base
    poss = subj + "'s"
    clarification = (
        f"{subj} with a clearly visible glowing golden ember core centered in "
        f"{poss} chest, bright amber qi threads visibly emanating from {poss} "
        f"chest and wrapping around {subj}'s torso and arms"
    )
    return f"{base}, and {clarification}"


def _has_physical_weapon(char_records: List[CharacterVisualRecord]) -> bool:
    return any(
        _classify_weapon(_canon_weapon(w)) == "object"
        for c in char_records for w in c.weapons
    )


def _has_none_physical_constraint(char_records: List[CharacterVisualRecord]) -> bool:
    return any(
        _classify_weapon(_canon_weapon(w)) == "constraint"
        for c in char_records for w in c.weapons
    )


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


# --------------------------------------------------------------------------- #
# Authoritative scene-scoped selection contract (single source of truth)
# --------------------------------------------------------------------------- #
# Every Studio Bible-derived field consumed by a V2 request must resolve from the
# SAME scene-selected subject and scene-selected location. These helpers provide
# that one deterministic contract, reused by derive_spec_inputs,
# project_to_generation_spec, and pipeline prompt construction. They never fall
# back to projection.characters[0] / projection.locations[0] as a substitute for
# a resolved identity when multiple characters or locations exist.


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
         resolves Kael and HA resolves Kai instead of staying unresolved and
         leaking cross-novel objects/effects downstream.
      4. Otherwise return None (genuinely unresolved / ambiguous)."""
    matched = _matched_subject_names(records, scene_text)
    if matched:
        lowered = [m.lower() for m in matched]
        for c in records:
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
    unresolved rather than silently picking [0]."""
    return _resolve_primary_character(
        projection.characters, scene_text, projection.novel)


def select_location_record(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Optional[LocationVisualRecord]:
    """Resolve the scene-selected LocationVisualRecord (canon-grounded).

    Deterministic order:
      1. Prefer locations whose canon `novel` matches the request novel. This is
         the authoritative multi-location signal (e.g. HA request -> ha_alley,
         never Kael's en apartment) and is inherently order-invariant.
      2. Within that novel-matched pool, prefer a location whose name or id
         appears in scene_text.
      3. Otherwise the first location in load order (deterministic file order).
    Never invents a location absent from canon."""
    novel = (projection.novel or "").lower()
    locs = list(projection.locations)
    if not locs:
        return None
    pool = [l for l in locs if novel and (l.novel or "").lower() == novel] if novel else []
    if not pool:
        pool = locs
    st = str(scene_text or "").lower()
    if st:
        for l in pool:
            nm = (l.name or "").lower()
            lid = (l.location_id or "").lower()
            if (nm and nm in st) or (lid and lid in st):
                return l
    return pool[0]


def character_visual_phrase(
    char_record: Optional[CharacterVisualRecord],
    *,
    object_identity: str = "",
    object_state: str = "",
) -> str:
    """Canon-grounded character visual description from a resolved record.

    Consumes ONLY canon-supplied appearance fields (gender, age, build, hair,
    eyes, clothing). Returns "" when no record is resolved (so OFF builds stay
    byte-identical and unresolved scenes are not fabricated).

    ``object_identity`` / ``object_state`` describe the SCENE's own object
    contract. They are used only to resolve the layout-vs-interaction conflict
    (see ``conditioning_clothing_descriptors``): when the scene requires an
    active grip/wield, the same object's default resting/carry layout descriptor
    is not emitted as a competing instruction. Legacy "(NOTE: ...)" authoring
    annotations are always stripped from conditioning text."""
    if not char_record:
        return ""
    c = char_record
    bits: List[str] = []
    if c.gender:
        bits.append(c.gender)
    if c.age:
        bits.append(c.age)
    if c.build:
        bits.append(c.build.replace("_", " "))
    if c.hair:
        bits.append(f"{c.hair} hair")
    if c.eyes:
        bits.append(f"{c.eyes} eyes")
    clothing = conditioning_clothing_descriptors(
        c.clothing, object_identity=object_identity, object_state=object_state
    )
    if clothing:
        bits.append(", ".join(clothing))
    return ", ".join(bits)


def _character_scoped_negative_guard(
    selected_records: List[CharacterVisualRecord],
) -> Tuple[str, ...]:
    """Per-character negative guard computed ONLY from the selected character(s).

    Kael's Soulblade (a global physical weapon) must never suppress Kai's
    none_physical guard: the guard is evaluated on the selected subject's own
    records, not the whole projection."""
    neg_per: Tuple[str, ...] = ()
    if not selected_records:
        return neg_per
    notes = " ".join(str(c.warnings) for c in selected_records).lower()
    if "soulblade" in notes or "sword" in notes:
        neg_per = ("weapon became staff", "no spear", "no staff", "no polearm",
                   "oversized weapon")
    if _has_none_physical_constraint(selected_records) and not _has_physical_weapon(selected_records):
        neg_per = tuple(dict.fromkeys(neg_per + ("physical weapon", "held blade")))
    return neg_per


def scene_selected_negative_guard(
    projection: StudioBibleProjection, scene_text: str = ""
) -> Tuple[str, ...]:
    """Final per-character negative guard for the scene-selected subject."""
    selected = select_character_record(projection, scene_text)
    return _character_scoped_negative_guard([selected] if selected else [])


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
    # Authoritative scene-scoped selection: the same subject and location feed
    # every downstream field. Resolves from scene-named identity, never [0].
    primary = select_character_record(projection, scene_text)
    loc = select_location_record(projection, scene_text)
    style = projection.styles[0] if projection.styles else None

    # Scope object/effect selection to the requested subject so a full
    # multi-character projection never leaks another character's object/effect
    # (e.g. a Kai request must never receive Kael's Soulblade).
    primary_char_id = primary.character_id if primary else ""
    scoped = _scope_objects_to_character(projection.objects, primary_char_id)
    phys = [o for o in scoped if not o.is_effect]
    effects = [o for o in scoped if o.is_effect]
    obj = phys[0] if phys else None

    if obj and obj.state == "sheathed":
        object_class = "sheathed_sword"
    elif obj and obj.state == "drawn":
        object_class = "drawn_sword"
    elif obj:
        # Surface a truthful, derivable ordinary-language class so an otherwise
        # opaque canon name (e.g. "Soulblade") carries interpretable grounding
        # for the model. Falls back to the generic "object" when no faithful
        # class can be derived (never fabricated visual detail).
        object_class = _derive_weapon_class(obj.canonical_phrase) or "object"
    else:
        object_class = ""

    matched = _matched_subject_names(projection.characters, scene_text)
    if matched:
        subjects_out = matched
    elif primary:
        subjects_out = (primary.name,)
    else:
        subjects_out = ()

    # Negative constraints: global canon identity set + the per-character guard
    # evaluated ONLY for the selected subject (Kael's Soulblade cannot suppress
    # Kai's none_physical guard).
    negative = tuple(
        dict.fromkeys(
            list(projection.negative_constraints.canon)
            + list(scene_selected_negative_guard(projection, scene_text))
        )
    )

    return {
        "character_id": primary_char_id,
        "subjects": subjects_out,
        "environment": loc.name if loc else "",
        # props carry both the physical object identity (EN) and the
        # non-physical qi effects (HA); the composer renders them distinctly.
        "props": tuple(o.canonical_phrase for o in phys + effects),
        "palette": style.palette_phrase if style else "",
        "lighting_design": loc.lighting if loc else "",
        "object_class": object_class,
        "object_state": obj.state if obj else "",
        "object_identity": obj.canonical_phrase if obj else "",
        "lighting": loc.lighting if loc else "",
        "negative_constraints": negative,
        "unresolved_fields": tuple(projection.unresolved_fields),
        "canon_warnings": tuple(projection.canon_warnings),
    }


def build_projection(novel: str, chapter: str, scene_text: str) -> StudioBibleProjection:
    """Read-only projection of Studio Bible canon for image generation.

    Missing canonical data is represented as absent/unresolved. Canon diagnostics
    are surfaced in `canon_warnings` and per-record `warnings`, never dropped.
    """
    warnings: List[str] = []
    unresolved: List[str] = []

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
    loc_records = [_project_location(l, warnings) for l in locations]
    style_records = [_project_style(novel, palette)] if palette else []
    if not palette:
        unresolved.append("style.palette")

    # scene-named subject selection (no all-names fallback), then novel-scoped
    # protagonist fallback for a per-novel request whose scene/prompt names no
    # subject. Uses the same authoritative resolver as select_character_record.
    primary = _resolve_primary_character(tuple(char_records), scene_text, novel)
    if primary is None:
        unresolved.append("content.subjects")
    selected_records = [primary] if primary is not None else []

    obj_records = _project_objects(unique_profiles, warnings)

    neg_canon = CANON_NEGATIVE_CONSTRAINTS
    # Per-character guard is SCOPED to the selected subject only. Kael's
    # Soulblade (a global physical weapon) must not suppress Kai's none_physical
    # guard: evaluating the whole projection would let another character's
    # physical weapon erase this subject's no-physical-weapon protection.
    neg_per = _character_scoped_negative_guard(selected_records)

    if not loc_records:
        unresolved.append("content.environment")
    if not obj_records:
        unresolved.append("conditioning.object_identity")

    return StudioBibleProjection(
        novel=str(novel).lower(),
        chapter=str(chapter),
        scene_text=scene_text,
        characters=tuple(char_records),
        locations=tuple(loc_records),
        styles=tuple(style_records),
        objects=tuple(obj_records),
        camera_intents=(),
        lighting_intents=(),
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

    # Authoritative scene-scoped selection (single contract reused everywhere):
    # the same selected subject and location feed identity, content, and
    # conditioning. Never projection.characters[0] / projection.locations[0].
    primary = select_character_record(projection, scene_text)
    loc = select_location_record(projection, scene_text)
    style = projection.styles[0] if projection.styles else None

    # Scope object/effect selection to the selected character so a full
    # multi-character projection does not leak another character's object/effect.
    primary_char_id = primary.character_id if primary else ""
    scoped = _scope_objects_to_character(projection.objects, primary_char_id)
    phys = [o for o in scoped if not o.is_effect]
    effects = [o for o in scoped if o.is_effect]
    obj = phys[0] if phys else None

    identity = IdentitySpec(
        character_id=primary.character_id if primary else "",
        character_version=primary.version if primary else "",
        studio_bible_binding=StudioBibleBinding(snapshot_ref="", snapshot_sha256=""),
        reference_bindings=(),
    )

    content = ContentSpec(
        subjects=(primary.name,) if primary else (),
        action="",
        environment=loc.name if loc else "",
        props=tuple(o.canonical_phrase for o in phys + effects),
        narrative_intent="",
    )

    style_spec = StyleSpec(
        pipeline=pipeline,
        style_profile=style.genre_label if style else "",
        palette=style.palette_phrase if style else "",
        lighting_design=loc.lighting if loc else "",
    )

    conditioning = ConditioningSpec(
        object_class=("sheathed_sword" if obj and obj.state == "sheathed"
                      else "drawn_sword" if obj and obj.state == "drawn"
                      else (_derive_weapon_class(obj.canonical_phrase) or "object") if obj
                      else ""),
        object_state=obj.state if obj else "",
        object_identity=obj.canonical_phrase if obj else "",
        lighting=loc.lighting if loc else "",
        negative_constraints=tuple(
            list(projection.negative_constraints.canon)
            + list(scene_selected_negative_guard(projection, scene_text))
        ),
    )

    attachment = AttachmentSpec(
        attachment_type=obj.attachment_type if obj else "",
        mechanism=obj.attachment_mechanism if obj else "",
        required_visible_evidence=obj.required_visible_evidence if obj else (),
    )

    references = ReferenceSpec()

    return GenerationSpec(
        identity=identity,
        content=content,
        style=style_spec,
        conditioning=conditioning,
        attachment=attachment,
        references=references,
        run=RunConfig(seed=seed),
    )
