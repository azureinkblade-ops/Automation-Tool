"""Visual Director — Slice 1: Bible to Visual Scene Package.

This is the missing production layer between the Studio Bible (canon) and
image generation. It turns structured Bible knowledge into a
VisualScenePackage that enforces character/appearance locks, environment
rules, shot plans, and negative constraints — so the generator stops
receiving a generic unstructured string and starts receiving canon-locked
prompts.

Design constraints (per build_discipline + user brief):
- Reads the Studio Bible YAML directly. Does NOT depend on the frozen AIVSB
  composer lane (which returns a flat string). AIVSB can enrich later.
- No video, no animation, no provider change. The existing image generator is
  untouched; this module only produces structured prompts.
- Authority for rules comes from the Visual Creative Director skill:
  priority = character identity > emotion > story moment > cinematic
  composition > style. Negative constraints come from that skill's
  "AI Image Risks" + each character's continuity rules.
- Source of truth for Bible data is the separate AIVSB repo
  (Inkblade Author Studio/scripts/aivsb). Cross-repo reference by design.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.scene_environment import (
    HP_HARD_LANDMARKS,
    UNSPECIFIED,
    build_still_cameras_poses,
    match_studio_bible_location,
    resolve_scene_environment,
    reject_cross_novel_landmarks,
    vd_effective_lead,
)

# --- Bible (Studio Canon) location -----------------------------------------
# The Bible lives in the separate AIVSB repo. app.py does not track this path,
# so we define it here. Override with AIVSB_BIBLE_DIR if the repo moves.
_DEFAULT_BIBLE_DIR = Path(r"C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb")
BIBLE_DIR = Path(os.environ.get("AIVSB_BIBLE_DIR", str(_DEFAULT_BIBLE_DIR))).resolve()
CHARACTERS_DIR = BIBLE_DIR / "characters"
LOCATIONS_DIR = BIBLE_DIR / "locations"
STYLE_DIR = BIBLE_DIR / "style_guides"

# novel abbreviation -> style guide file
NOVEL_STYLE_FILE = {
    "en": "en.yaml",
    "ha": "ha.yaml",
    "hp": "hp.yaml",
    "sf": "sf.yaml",
}

# Per-novel genre label (from the Visual Creative Director novel identities).
# Used as the prompt opener so HP's "cultivation" wording never leaks into EN/SF/HA.
NOVEL_GENRE_LABEL = {
    "hp": "xianxia cultivation fantasy illustration",
    "en": "cyberpunk mystic fantasy illustration",
    "sf": "ashpunk industrial fantasy illustration",
    "ha": "system fantasy illustration",
}

# Reusable narrative-objective / camera / power vocabulary (Slice A). These are
# novel-agnostic visual primitives the Director composes per shot. Kept short
# and precise on purpose: the A/B showed structured > verbose.
SHOT_TAXONOMY = [
    "establishing", "environment", "travel", "character",
    "dialogue", "combat", "artifact", "reaction", "climax",
]
CAMERA_VOCAB = [
    "wide low-angle environmental shot", "over-the-shoulder tracking shot",
    "low-angle hero shot", "top-down reveal", "extreme close-up",
    "wide environmental reveal",
]
POWER_VOCAB = [
    "faint qi threads", "dormant formation lines", "jade mist",
    "sword aura", "pressure distortion", "spiritual motes",
]

# Canonical weapon normalization. The Bible YAML (frozen AIVSB repo) lists
# "silver_edged_weapon" under BOTH clothing and weapons, which the Director
# previously emitted twice ("silver edged weapon, silver edged"). We normalize
# to a single canonical bladed-weapon phrase here WITHOUT editing the frozen
# Bible data. The duplicate in liang.yaml is flagged separately for Bible
# hygiene (a different repo/authorization).
_WEAPON_CANON = {
    "silver edged weapon": "silver-edged sword",
    "silver edged": "silver-edged sword",
    "silver_edged_weapon": "silver-edged sword",
    "silver edged sword": "silver-edged sword",
}

# Abstract age literals the Bible uses that are not renderable; map to a
# concrete descriptor the generator can act on.
_AGE_CANON = {
    "reborn_adult": "young adult",
    "young_adult": "young adult",
    "young adult": "young adult",
}

# Derive character gender from scene-text pronouns (canon YAML has no gender
# field). Used to lock identity and prevent the A/B-observed gender flip.
_GENDER_PRONOUNS = {
    "he": "male", "him": "male", "his": "male", "himself": "male",
    "she": "female", "her": "female", "hers": "female", "herself": "female",
}

# Abstract state words in the frozen Bible's damage_state that CONTRADICT a
# 'ruined' scene cue (user finding #1). When present we drop them so SDXL does
# not draw an intact, maintained temple.
_RUIN_CONTRADICTORY = {"ordered", "pristine", "intact", "maintained", "well kept", "polished"}

# Visual Creative Director skill: negative constraints that protect canon.
# Mirrors the skill's "AI Image Risks" + per-character forbidden changes.
CANON_NEGATIVE_CONSTRAINTS = [
    "modern clothing",
    "modern objects",
    "incorrect weapon",
    "wrong clothing",
    "incorrect hairstyle",
    "changed eye color",
    "changed age",
    "extra limbs",
    "distorted hands",
    "generic fantasy appearance",
    "wrong setting",
    "missing character symbols",
]


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # available in the codex runtime (installed for AIVSB)
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


# --- Bible accessors -------------------------------------------------------

def load_character_profiles() -> Dict[str, Dict[str, Any]]:
    """Return {lower_full_name: profile} across all character YAML files.

    Each character file may be a single mapping (name at top) or a list of
    mappings (sf_protagonists.yaml). Also builds a first-token alias index
    (e.g. "kael veyra" -> "kael") for scene-text matching.
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
            entry.setdefault("_source", path.name)
            key = name.lower()
            profiles[key] = entry
            # first-token alias for scene matching (exact-token, not substring,
            # so "kael" never collides with "kai")
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


def _clean_canon_token(value: str) -> str:
    """Strip editorial annotations and inline notes from Bible tokens so
    malformed/verbose source data never contaminates a generation prompt.

    Examples handled:
      "silver_edged_weapon (NOTE: SDXL dropped to staff, accept)"
          -> "silver edged weapon"
      "jade sect robes" -> "jade sect robes"
    """
    v = str(value or "").strip()
    # drop anything from the first '(' (parenthetical notes)
    if "(" in v:
        v = v[: v.index("(")].strip()
    # drop trailing inline provenance like " at Ch140"
    v = re.sub(r"\s+at\s+Ch\d+.*$", "", v, flags=re.IGNORECASE)
    return v.replace("_", " ").strip()


def _palette_phrase(palette: Dict[str, Any]) -> str:
    """Turn a style-guide palette dict into a short art-direction color phrase.

    The raw palette is a nested dict of hex values; dumping it into a prompt is
    noise. Extract the handful of named swatches and phrase them as colors.
    """
    if not isinstance(palette, dict):
        return ""
    named = {k: v for k, v in palette.items() if isinstance(v, str) and v.startswith("#")}
    # prefer the human-readable descriptive keys, fall back to any hex swatches
    phrase_bits = []
    for key in ("primary", "secondary", "accent", "shadow", "magic", "combat"):
        if key in named:
            phrase_bits.append(f"{key.replace('_', ' ')} {named[key]}")
    if not phrase_bits:
        # try descriptive non-hex keys (e.g. "palette: weathered stone, muted jade")
        for key in ("palette", "color_grading", "mood"):
            if isinstance(palette.get(key), str):
                return palette[key].replace("_", " ")
    return ", ".join(phrase_bits)


# --- Scene text -> canon extraction ----------------------------------------

def extract_character_names(scene_text: str, profiles: Dict[str, Dict[str, Any]]) -> List[str]:
    """Match known Bible character names present in the scene text.

    Slice 1 uses exact first-name token matching (case-insensitive, word
    boundary) so "Kael" matches "kael veyra" but never falsely matches "Kai".
    Full NLP scene parsing is a later slice.
    """
    # collect the set of distinct canonical first-name tokens present in profiles
    first_tokens = {k.split()[0] for k in profiles if k.split()}
    scene_words = {w for w in str(scene_text or "").lower().split() if w}
    matched_tokens = first_tokens & scene_words
    # map back to the full canonical profile key (first match wins, Bible order)
    found: List[str] = []
    for key in profiles:
        if key.split() and key.split()[0] in matched_tokens and key not in found:
            found.append(key)
    # de-dupe but preserve Bible order
    seen = set()
    ordered = []
    for n in found:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def match_location(scene_text: str, locations: List[Dict[str, Any]], novel: str) -> Optional[Dict[str, Any]]:
    """Find a recurring location whose name/id/architecture keywords appear in scene text.

    SCENE_ENVIRONMENT_CONSISTENCY_REMEDIATION: delegates to novel-scoped Studio Bible
    matcher (aliases + field haystack). Unknown -> None (UNSPECIFIED); never borrows
    another novel's landmarks.
    """
    return match_studio_bible_location(scene_text, locations, novel)



# --- Package builder -------------------------------------------------------

def _appearance_lock(profile: Dict[str, Any], warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """Flatten Bible appearance/clothing/weapon into a Director lock dict.

    Note: in the Bible YAML, body_type/age/height live UNDER `appearance:`,
    while clothing/weapons are top-level. Read both locations defensively.

    Any malformed or contradictory canon entry is recorded in `warnings`
    (explicit diagnostics) rather than silently dropped, so a prompt that LOOKS
    clean is never hiding an incomplete character lock.
    """
    name = str(profile.get("name") or "?")

    def _as_str(v: Any) -> str:
        # Bible YAML can contain malformed entries (e.g. an unquoted value with
        # parens parsed as a nested dict). Never crash; stringify safely AND
        # record the defect in warnings.
        if isinstance(v, dict):
            if warnings is not None:
                warnings.append(
                    f"canon malformed entry for '{name}': YAML parsed "
                    f"{v!r} as a mapping (likely an unquoted value with "
                    f"parentheses); coerced to a string."
                )
            return " ".join(f"{k} {val}" for k, val in v.items())
        return str(v or "").replace("_", " ").strip()

    def _as_list(v: Any) -> List[str]:
        if not isinstance(v, list):
            return [_as_str(v)] if v else []
        return [_as_str(item) for item in v]

    ap = profile.get("appearance") or {}
    hair = ap.get("hair") or {}
    eyes = ap.get("eyes") or {}

    clothing = _as_list(profile.get("clothing", []) or [])
    weapons = _as_list(profile.get("weapons", []) or [])

    # Detect a weapon list that mixes a positive weapon with a "no weapon"
    # chapter exception -> contradictory canon. Record, do not silently pick.
    _NEG = ("no weapon", "carries no", "missing weapon", "unarmed")
    has_positive_weapon = any(w and not any(b in w.lower() for b in _NEG) for w in weapons)
    has_negation = any(any(b in w.lower() for b in _NEG) for w in weapons)
    if has_positive_weapon and has_negation and warnings is not None:
        warnings.append(
            f"canon contradiction for '{name}': weapon list mixes a positive "
            f"weapon with a 'no weapon' exception (likely a chapter-specific "
            f"note); lock keeps only positive descriptors, verify canonical default."
        )

    lock = {
        "name": profile.get("name"),
        "hair": _as_str(hair.get("style")),
        "eyes": _as_str(eyes.get("color")),
        # body_type / age may be under appearance OR top-level
        "body_type": _as_str(ap.get("body_type") or profile.get("body_type")),
        "age": _as_str(ap.get("age") or profile.get("age")),
        "height": _as_str(ap.get("height") or profile.get("height")),
        "clothing": clothing,
        "weapons": weapons,
        "magic_style": _as_str(profile.get("magic_style")),
        "lighting_preference": _as_str(profile.get("lighting_preference")),
    }
    # Incomplete-lock warning: if the visible identity fields are all empty, the
    # character may be unrecognizable even though the prompt looks clean.
    identity = (lock["hair"], lock["eyes"], lock["body_type"], " ".join(lock["clothing"]))
    if warnings is not None and not any(identity):
        warnings.append(
            f"canon incomplete for '{name}': no hair/eyes/body/clothing resolved; "
            f"character lock may be insufficient for consistent generation."
        )
    return lock


def _canon_weapon(token: str) -> str:
    """Normalize a weapon descriptor to a single canonical bladed-weapon phrase.

    Handles the frozen Bible YAML's malformed entries:
      - 'silver_edged_weapon' (clothing) and 'silver_edged' (weapons) ->
        'silver-edged sword' (was emitting the duplicate
        'silver edged weapon, silver edged')
      - 'Soulblade_at_side (NOTE: ...)' and 'Soulblade (Eclipse Soulblade
        blueprint)' -> 'Soulblade' (was leaking parenthetical noise + dup)
    We normalize WITHOUT editing the frozen Bible data; the YAML duplication is
    flagged separately for Bible hygiene.
    """
    t = _clean_canon_token(token).strip().lower()
    # exact known mappings first
    if t in _WEAPON_CANON:
        return _WEAPON_CANON[t]
    # generic: strip parenthetical leftovers, keep the base weapon noun + a
    # short leading modifier, so 'soulblade at side' and
    # 'soulblade eclipse soulblade blueprint' both collapse to 'Soulblade'.
    words = [w for w in re.split(r"[\s,]+", t) if w]
    if not words:
        return token
    # find the first word that looks like a weapon noun
    _WEAPON_NOUNS = ("soulblade", "sword", "jian", "blade", "bow", "staff",
                     "spear", "fan", "horn", "axe", "saber", "sabre")
    base = None
    for w in words:
        if w in _WEAPON_NOUNS:
            base = w
            break
    if base is None:
        # not a recognized weapon noun; keep first two words as-is
        return " ".join(words[:2])
    # 'silver edged' style -> silver-edged sword
    if "silver" in words and base in ("edged",):
        return "silver-edged sword"
    if base == "soulblade":
        return "Soulblade"
    # default: a short '<modifier> <noun>' form
    idx = words.index(base)
    modifier = words[idx - 1] if idx > 0 and words[idx - 1] not in _WEAPON_NOUNS else ""
    return (modifier + " " + base).strip() if modifier else base


def _is_scene_placement(token: str) -> bool:
    """True if a clothing/prop token describes SCENE PLACEMENT (where banners
    hang), not the character's persistent appearance. Such tokens must be
    emitted under Setting, never inside the Character Identity block (user
    finding #6: 'red banners nearby' in the identity block caused robe-color
    mixing / the red robe in Director 1)."""
    t = token.lower()
    return "banner" in t or "banners" in t or "nearby" in t or "around" in t


# One exact, unambiguous weapon lock. The frozen Bible's 'silver_edged' +
# 'silver_edged_weapon' tokens are collapsed to this single precise descriptor
# so SDXL cannot drift the weapon into a staff / polearm (user finding #4).
_WEAPON_LOCK = "one standard-length Chinese jian, straight double-edged blade, simple silver guard, sheathed at his left hip"


def _weapon_lock_phrase() -> str:
    return _WEAPON_LOCK


def _looks_like_weapon(token: str) -> bool:
    """True if an appearance token is a (loose) weapon word that should be
    replaced by the precise _WEAPON_LOCK phrase (user finding #4)."""
    t = token.lower()
    return any(w in t for w in ("sword", "jian", "blade", "weapon", "spear", "staff", "polearm", "saber", "sabre"))


# IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929 (Part A). Everything below is used ONLY
# when ENABLE_IDENTITY_PRESERVATION is ON; flag-OFF prompts are byte-identical to legacy.
# The jian lock is Liang's canon weapon (Bible 'silver_edged' -> 'silver-edged sword'), so it
# is emitted only for a character whose canon weapon normalizes to that, in its own Weapon
# section (never inside the Character Identity block) and with no pronoun.
_JIAN_CANON_WEAPON = "silver-edged sword"
_WEAPON_LOCK_NEUTRAL = "one standard-length Chinese jian, straight double-edged blade, simple silver guard, sheathed at the left hip"
_ID_ON_NON_WEAPON = ("none", "unknown", "ui", "holo", "qi", "n/a")


def _primary_canon_weapons(primary: Any) -> List[str]:
    """Canon positive weapon phrases for the SELECTED character (flag ON only)."""
    if not isinstance(primary, dict):
        return []
    out: List[str] = []
    for w in list(primary.get("weapons", []) or []):
        cleaned = _clean_canon_token(str(w)).lower()
        if not cleaned or any(re.search(rf"\b{re.escape(b)}\b", cleaned) for b in _ID_ON_NON_WEAPON):
            continue
        if any(b in cleaned for b in ("no weapon", "carries no", "unarmed")):
            continue
        canon = _canon_weapon(str(w))
        if canon and canon not in out:
            out.append(canon)
    return out


def _primary_has_jian_canon(primary: Any) -> bool:
    return _JIAN_CANON_WEAPON in _primary_canon_weapons(primary)


def _primary_wardrobe_tokens(primary: Any) -> List[str]:
    """Bible clothing for the Wardrobe section (flag ON): no scene placement, no weapons."""
    if not isinstance(primary, dict):
        return []
    out: List[str] = []
    for c in list(primary.get("clothing", []) or []):
        cleaned = _clean_canon_token(str(c))
        if not cleaned or _is_scene_placement(cleaned) or _looks_like_weapon(cleaned):
            continue
        if cleaned.lower() not in [o.lower() for o in out]:
            out.append(cleaned)
    return out


def _identity_on_governed_primary(novel: str) -> Optional[str]:
    """Flag ON, no character named in the scene text: the single governed character bound by
    structured context (ambient IdentityProductionContext, else the novel id/abbreviation)."""
    try:
        from tools.identity_preservation import (current_identity_context, governed_character_keys_for_novel,
                                                 resolve_production_novel_alias)
    except Exception:  # pragma: no cover
        return None
    ctx = current_identity_context()
    if ctx is not None and (ctx.character_id or ctx.character_name):
        from tools.identity_preservation import normalize_identity_character_key
        key = normalize_identity_character_key(ctx.character_id or ctx.character_name)
        if key:
            return key
    nid = None
    if ctx is not None:
        nid = resolve_production_novel_alias(ctx.novel_id) or resolve_production_novel_alias(ctx.novel_abbreviation)
    nid = nid or resolve_production_novel_alias(novel)
    keys = governed_character_keys_for_novel(nid) if nid else []
    if len(keys) == 1:
        return keys[0]
    return None


def _identity_contract_for(primary: Any):
    """(identity_flag_on, governed IdentityContract or None). Flag OFF -> (False, None)."""
    try:
        from tools.identity_preservation import get_identity_contract, is_identity_preservation_enabled
    except Exception:  # pragma: no cover - module always present with this source
        return False, None
    if not is_identity_preservation_enabled():
        return False, None
    name = primary.get("name", "") if isinstance(primary, dict) else ""
    return True, get_identity_contract(name)


def _identity_contract_sex(contract: Any) -> str:
    """Sealed TEXT_CANON sex only (Jarek male); '' for UNSPECIFIED / scene-dependent / ungoverned."""
    if contract is None or not getattr(contract, "sex", None):
        return ""
    if not str(contract.authority().get("SEX", "")).startswith("TEXT_CANON"):
        return ""
    return str(contract.sex)


def _derive_gender(scene_text: str) -> str:
    """Infer character gender from scene-text pronouns (canon YAML has none).

    Returns 'male' / 'female' / '' (unknown). Used to lock identity and prevent
    the A/B-observed gender flip within a sequence.
    """
    words = re.findall(r"[a-z]+", str(scene_text or "").lower())
    for w in words:
        if w in _GENDER_PRONOUNS:
            return _GENDER_PRONOUNS[w]
    return ""


def _character_lock_tokens(
    lock: Dict[str, Any],
    name: str = "",
    warnings: Optional[List[str]] = None,
    scene_text: str = "",
) -> List[str]:
    """Human-readable appearance tokens for prompt assembly.

    Editorial noise (parenthetical notes, per-chapter provenance, negation
    annotations like 'carries NO weapon at Ch140') is stripped AND recorded in
    warnings so the filter is explicit, not silent. Only positive visual
    descriptors survive. Weapon descriptors are canonicalized + deduped.
    """
    _NON_VISUAL = (
        "no weapon", "note", "accept", "dropped", "sdxl", "staff",
        "ch140", "chapter", "missing", "unknown", "carries no", "unarmed",
        "none physical", "(qi based)", "n/a", "none",
    )

    def keep(token: str) -> bool:
        t = token.lower()
        if not t:
            return False
        # drop tokens that merely carry non-visual / chapter-exception noise
        if any(bad in t for bad in _NON_VISUAL):
            if warnings is not None:
                warnings.append(
                    f"canon filtered '{token}' from '{name}' lock: non-visual / "
                    f"chapter-exception annotation, not a usable appearance descriptor."
                )
            return False
        return True

    raw: List[str] = []
    if lock.get("hair"):
        raw.append(f"{_clean_canon_token(lock['hair'])} hair")
    if lock.get("eyes"):
        raw.append(f"{_clean_canon_token(lock['eyes'])} eyes")
    # age literals like reborn_adult / young_adult are abstract; convey the
    # concrete body_type instead so the generator gets a usable signal.
    if lock.get("body_type") and "unknown" not in lock["body_type"]:
        raw.append(_clean_canon_token(lock["body_type"]))
    if lock.get("age") and "unknown" not in lock["age"]:
        canon_age = _AGE_CANON.get(lock["age"].strip().lower())
        if canon_age:
            raw.append(canon_age)
    for c in lock.get("clothing", []):
        cleaned = _clean_canon_token(c)
        # Clothing tokens that describe SCENE PLACEMENT (banners near the
        # character), not the character's persistent appearance, must NOT live
        # in the Character Identity block (user finding #6: contamination caused
        # robe-color mixing). They are emitted under Setting instead.
        if _is_scene_placement(cleaned):
            continue
        # clothing may itself name a weapon (e.g. 'silver_edged_weapon'); route
        # it through the same canonicalizer so it dedups with the weapons list.
        if "weapon" in cleaned.lower() or "sword" in cleaned.lower() or "blade" in cleaned.lower():
            cleaned = _canon_weapon(c)
        if cleaned:
            raw.append(cleaned)
    for w in lock.get("weapons", []):
        cleaned = _clean_canon_token(w)
        if cleaned:
            # canonicalize weapons (collapses the Bible duplicated silver token)
            raw.append(_canon_weapon(w))
    # dedupe (case-insensitive) while preserving order
    seen: set[str] = set()
    tokens: List[str] = []
    for t in raw:
        key = t.lower()
        if key not in seen and keep(t):
            seen.add(key)
            tokens.append(t)
    return tokens


def _build_shot_plan(
    novel: str,
    characters: List[Dict[str, Any]],
    location: Optional[Dict[str, Any]],
    shots_text: Optional[List[str]] = None,
    scene_text: str = "",
) -> List[Dict[str, Any]]:
    """Three-shot cinematic plan with novel-scoped SceneEnvironmentSpec.

    SCENE_ENVIRONMENT_CONSISTENCY_REMEDIATION:
    - Cameras/poses derive from resolved environment + scene action (no generic HP hardcode).
    - HP landmarks (ruined sect hall / jade altar) only when HP scene supports them.
    - Authority: TEXT_CANON_SCENE > STUDIO_BIBLE_LOCATION > SCENE_CONTEXT > VISUAL_DIRECTION > MODEL_PRIOR.
    """
    primary = characters[0] if characters else {}
    primary_name = primary.get("name") or "the protagonist"
    lighting = location.get("lighting") if location else primary.get("lighting_preference") or ""
    if _identity_contract_for(primary)[0]:
        magic = primary.get("magic_style") or (location or {}).get("magic_effects") or ""
    else:
        magic = primary.get("magic_style") or (location.get("magic_effects") if location else "") or ""

    gender = _derive_gender(scene_text) if scene_text else (
        _derive_gender(primary.get("notes", "")) if isinstance(primary, dict) else ""
    )
    _id_on, _id_contract = _identity_contract_for(primary)
    if _id_on:
        gender = _identity_contract_sex(_id_contract)

    # Resolve environment for the package (still_index 0 base; per-shot role applied below).
    base_spec = resolve_scene_environment(
        novel,
        scene_text,
        location=location,
        still_index=0,
        composition_goal=(shots_text[0] if shots_text else None),
        shots_text=shots_text,
    )
    env_name = (
        base_spec.location_name
        if base_spec.location_name and base_spec.location_name != UNSPECIFIED
        else base_spec.place_phrase
    )
    env_state = base_spec.environment_state

    # Banners belong under SETTING, never in Character Identity.
    banner_bits: List[str] = []
    if primary:
        for c in primary.get("clothing", []) or []:
            if _is_scene_placement(str(c)):
                banner_bits.append(_clean_canon_token(c))
    if location:
        for key in ("banners", "decorations"):
            v = str(location.get(key, "")).replace("_", " ").strip()
            if v and "n/a" not in v.lower() and "none" not in v.lower():
                banner_bits.append(v)
    banner_line = ", ".join(dict.fromkeys(banner_bits)) if banner_bits else ""

    has_jian = bool(_id_on and _primary_has_jian_canon(primary))
    # SCENE_ENV_IDENTITY_OFF_LEGACY_HP_CAMERAS:
    # SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Part I, option A) + R3 Phase 4:
    # Do NOT apply landmark/template content merely because NOVEL_ID=HP or hp_landmarks_allowed.
    # Require scene/location support for EACH specific landmark (altar / broken staircase /
    # gateway formations). Outside-gate: exterior gate ok; interior altar/staircase not unless
    # source supports them. Preferred: build from SceneEnvironmentSpec like other novels.
    _hp_supported = list((base_spec.observability or {}).get("SUPPORTED_HP_LANDMARKS") or [])
    _has_hall = any("sect hall" in s or "ruined sect" in s for s in _hp_supported)
    _has_stair = any("stair" in s for s in _hp_supported)
    _has_altar = any("altar" in s for s in _hp_supported)
    _has_formation = any("formation" in s for s in _hp_supported)
    _has_gate = any("gate" in s for s in _hp_supported)
    _hp_interior_ok = _has_hall or _has_stair or _has_altar or _has_formation
    if (not _id_on and str(novel).lower() == "hp" and base_spec.hp_landmarks_allowed and _hp_interior_ok):
        place = env_name or f"the {str(novel).upper()} setting"
        bg0 = "the ruined sect hall and gateway" if _has_hall else ("the sect gate exterior" if _has_gate else place)
        climb = (
            "as he climbs the broken stair" if _has_stair else f"as he advances through {place}"
        )
        ahead = "with the jade altar rising ahead" if _has_altar else f"with {place} ahead"
        climax = (
            "kneeling on one knee before the altar with the dormant formation glowing on the floor behind him"
            if (_has_altar and _has_formation) else (
                "kneeling on one knee before the altar" if _has_altar else
                f"at the decisive beat within {place}"
            )
        )
        cameras = [
            (
                f"full-body medium shot of Liang {'entering the ruined sect hall' if _has_hall else f'at {place}'}; "
                f"Liang fills approximately 20 to 25 percent of the frame height and is immediately recognizable "
                f"even at thumbnail size, while {bg0} fill the background"
            ),
            (
                f"over-the-shoulder tracking shot from behind Liang {climb}; "
                f"Liang fills approximately 20 to 25 percent of the frame height and is clearly visible and "
                f"prominent, {ahead}"
            ),
            (
                f"three-quarter side view, Liang clearly the subject {climax}; "
                f"Liang fills approximately 20 to 25 percent of the frame height"
            ),
        ]
        gate_look = (
            "looking at the ancient formations above the gateway" if (_has_formation and _has_gate)
            else ("looking toward the sect gate" if _has_gate else f"looking into {place}")
        )
        mid = (
            "midway up the broken staircase, one foot planted on a higher step, body leaning forward, robe trailing behind him, right hand hovering over the sword hilt"
            if _has_stair else
            f"midway through the advance through {place}, body leaning forward, robe trailing behind him, right hand hovering over the sword hilt"
        )
        end = (
            "kneeling on one knee before the altar, left hand pressed to the cold stone, silver qi visibly flowing through the dormant formation lines on the floor"
            if (_has_altar and _has_formation) else (
                "kneeling on one knee before the altar, left hand pressed to the cold stone" if _has_altar else
                f"holding at the turning moment within {place}"
            )
        )
        poses = [
            f"standing at the entrance, head tilted upward, {gate_look}",
            mid,
            end,
        ]
        place = env_name or f"the {str(novel).upper()} setting"
        # R2 round 4: action-first default objectives (same rule as build_still_cameras_poses) so the
        # scene beat lands inside the CLIP-77 window after the long legacy HP poses.
        _act = str(base_spec.composition_goal or base_spec.scene_action or "").strip()
        if _act:
            default_objectives = [
                f"{_act} (establishing Liang at {place})",
                f"{_act} (advancing deeper into {place})",
                f"{_act} (the hidden power as the moment turns)",
            ]
        else:
            default_objectives = [
                f"Establish Liang arriving at {place}",
                f"Show Liang advancing deeper into {place}",
                f"Reveal the hidden power as the moment turns",
            ]
        if shots_text and len(shots_text) >= 3:
            objectives = [s.strip() for s in shots_text[:3]]
        else:
            objectives = default_objectives
        emotions = ["awe and uncertainty", "determination", "discovery"]
        expressions = ["quiet awe", "determined focus", "solemn discovery"]
        shot_types = ["establishing", "travel", "climax"]
        shots = []
        for i in range(3):
            shot_env_state = env_state
            if shot_types[i] in _INTERACTION_SHOT_TYPES:
                shot_env_state = _trim_env_for_interaction(env_state)
            shots.append({
                "type": shot_types[i],
                "camera": cameras[i],
                "purpose": objectives[i],
                "narrative_objective": objectives[i],
                "subject": primary_name,
                "gender": gender,
                "action": poses[i],
                "expression": expressions[i],
                "emotion": emotions[i],
                "environment": env_name,
                "environment_state": shot_env_state,
                "banner_line": banner_line,
                "lighting": str(lighting).replace("_", " "),
                "effect": str(magic).replace("_", " "),
                "still_index": i,
                "still_role": shot_types[i],
                "composition_goal": objectives[i],
                "location_id": base_spec.location_id,
                "environment_authority": base_spec.authority,
                "scene_environment_observability": {
                    **base_spec.observability,
                    "identity_off_legacy_hp_cameras": True,
                    "still_index": i,
                    "still_role": shot_types[i],
                },
                "effective_lead": vd_effective_lead(base_spec, cameras[i], still_index=i, still_role=shot_types[i]),
            })
        return shots

    cameras, poses, default_objectives = build_still_cameras_poses(
        base_spec,
        primary_name,
        identity_on=bool(_id_on),
        has_jian=has_jian,
    )

    # Per-image narrative objectives from caller shots_text when provided.
    if shots_text and len(shots_text) >= 3:
        objectives = [s.strip() for s in shots_text[:3]]
        # Rebuild cameras/poses per still so composition tracks each scene beat.
        cameras = []
        poses = []
        for i in range(3):
            role = ["establishing", "travel", "climax"][i]
            spec_i = resolve_scene_environment(
                novel,
                scene_text,
                location=location,
                still_index=i,
                still_role=role,
                composition_goal=shots_text[i],
                shots_text=shots_text,
            )
            cam_i, pose_i, _obj = build_still_cameras_poses(
                spec_i, primary_name, identity_on=bool(_id_on), has_jian=has_jian
            )
            cameras.append(cam_i[i])
            poses.append(pose_i[i])
    else:
        # Scene-specific: even without shots_text, differentiate via scene_text clauses.
        objectives = default_objectives
        # When scene_text differs across packages, place/action in cameras already differ
        # via base_spec. For multi-still within one package, role clauses differ.
        cameras = []
        poses = []
        for i in range(3):
            role = ["establishing", "travel", "climax"][i]
            spec_i = resolve_scene_environment(
                novel,
                scene_text,
                location=location,
                still_index=i,
                still_role=role,
                composition_goal=scene_text,
                shots_text=shots_text,
            )
            cam_i, pose_i, _obj = build_still_cameras_poses(
                spec_i, primary_name, identity_on=bool(_id_on), has_jian=has_jian
            )
            cameras.append(cam_i[i])
            poses.append(pose_i[i])
        objectives = default_objectives

    emotions = ["awe and uncertainty", "determination", "discovery"]
    expressions = ["quiet awe", "determined focus", "solemn discovery"]
    shot_types = ["establishing", "travel", "climax"]

    shots = []
    for i in range(3):
        shot_env_state = env_state
        if shot_types[i] in _INTERACTION_SHOT_TYPES:
            shot_env_state = _trim_env_for_interaction(env_state)
        # Strip HP hard landmarks from non-HP shots (defense in depth).
        cam = cameras[i]
        act = poses[i]
        if str(novel).lower() != "hp" or not base_spec.hp_landmarks_allowed:
            for lm in HP_HARD_LANDMARKS:
                if lm in cam.lower():
                    cam = re.sub(re.escape(lm), env_name or "the setting", cam, flags=re.I)
                if lm in act.lower():
                    act = re.sub(re.escape(lm), "the focal point", act, flags=re.I)
        spec_obs = resolve_scene_environment(
            novel,
            scene_text,
            location=location,
            still_index=i,
            still_role=shot_types[i],
            composition_goal=objectives[i],
            shots_text=shots_text,
        )
        obs = spec_obs.observability
        shots.append({
            "type": shot_types[i],
            "camera": cam,
            "purpose": objectives[i],
            "narrative_objective": objectives[i],
            "subject": primary_name,
            "gender": gender,
            "action": act,
            "expression": expressions[i],
            "emotion": emotions[i],
            "environment": env_name,
            "environment_state": shot_env_state,
            "banner_line": banner_line,
            "lighting": str(lighting).replace("_", " "),
            "effect": str(magic).replace("_", " "),
            "still_index": i,
            "still_role": shot_types[i],
            "composition_goal": objectives[i],
            "location_id": base_spec.location_id,
            "environment_authority": base_spec.authority,
            "scene_environment_observability": obs,
            "effective_lead": vd_effective_lead(spec_obs, cam, still_index=i, still_role=shot_types[i]),
        })
    return shots



# Shot types whose narrative hinge is NOT primarily "show the epic environment,"
# so we trim the verbose ambiance inventory (Slice A.6 + Run 7: apply the trim
# selectively). 'establishing' keeps the FULL descriptive env-state because its
# job IS to sell the location (shot 1 scores 9.5 on that richness); 'travel' and
# 'climax'/'ritual'/'action' shots free attention for the subject + pose.
_INTERACTION_SHOT_TYPES = {"travel", "climax", "ritual", "action", "interaction"}

# Words that belong to the verbose "ambiance" inventory rather than the core
# location identity. For interaction shots we drop these so the environment
# still establishes WHERE without stealing attention from the pose.
_ENV_TRIM_TOKENS = (
    "mist", "mist layers", "falling leaves", "leaves", "qi motes", "motes",
    "abandoned for centuries", "partially collapsed", "cracked stone stairs",
    "broken jade railings", "fallen roof tiles", "faded and torn banners",
    "dust", "dust and mist", "fog", "fog density", "ambient particles",
)


def _trim_env_for_interaction(env_state: str) -> str:
    """For an interaction/ritual shot, keep only the core location-establishing
    descriptors (short, identity-bearing) and drop the long ambiance inventory
    (mist layers, falling leaves, qi motes, cracked stairs, broken railings,
    roof tiles, banners, dust, hall) that competes with the pose for attention.
    """
    if not env_state:
        return env_state
    kept = []
    for tok in env_state.split(","):
        t = tok.strip()
        if not t:
            continue
        tl = t.lower()
        if tl in _ENV_TRIM_TOKENS:
            continue
        # drop any token that is a substring of a trim phrase (e.g. 'roof tiles')
        if any(tl in phrase or phrase in tl for phrase in _ENV_TRIM_TOKENS):
            continue
        kept.append(t)
    return ", ".join(dict.fromkeys(kept))


def _negative_prompt(profile: Dict[str, Any]) -> List[str]:
    """Canon negative constraints + any character-specific forbidden changes."""
    neg = list(CANON_NEGATIVE_CONSTRAINTS)
    notes = str(profile.get("notes") or "").lower()
    if "silver sword became staff" in notes or "soulblade" in notes or "sword" in notes:
        # protect the canonical bladed weapon from model drift
        neg.append("weapon became staff")
    # User finding #4: the model drifts the locked jian into a staff / polearm /
    # oversized weapon. Force-exclude those so the weapon lock holds.
    neg.extend(["spear", "staff", "polearm", "oversized weapon", "no spear", "no staff", "no polearm"])
    return neg


def _assemble_image_prompts(
    novel: str,
    chapter: str,
    scene_text: str,
    characters: List[Dict[str, Any]],
    shots: List[Dict[str, Any]],
    location: Optional[Dict[str, Any]],
    palette: Dict[str, Any],
    warnings: Optional[List[str]] = None,
) -> List[str]:
    """One Bible-enriched prompt string per shot. The existing generator consumes
    this list exactly like the legacy `image_prompts` list.

    Slice A structure (precise, not verbose; per the user's brief):
      <genre>, vertical 9:16.
      Narrative Objective: <per-image objective>
      Character Identity: <permanent block: name, gender, age, build, hair,
                           face, clothing, weapon, aura>
      Action: <pose/action>
      Setting: <location name>
      Environment State: <condition of the place>
      Camera: <explicit direction>
      Lighting: <...>
      Power: <magic effect>
      Emotion: <...>
      Consistent character design, canon-accurate.
    """
    char_tokens = []
    for c in characters:
        char_tokens.extend(_character_lock_tokens(
            _appearance_lock(c, warnings), name=c.get("name", ""), warnings=warnings,
            scene_text=scene_text,
        ))

    # Permanent character-identity block (appears in EVERY image so SDXL keeps
    # the same person across the sequence). Built from canon + derived gender.
    # Field hygiene (user finding #6): the block carries ONLY persistent identity
    # (name/gender/age/build/hair/eyes/robe/weapon). Scene placement like
    # banners is NOT included here; it is emitted under Setting.
    primary = characters[0] if characters else {}
    gender = shots[0].get("gender", "") if shots else ""
    age_canon = _AGE_CANON.get(str(primary.get("age", "")).strip().lower(), "young adult") if isinstance(primary, dict) else "young adult"
    # IDENTITY_PRODUCTION_PLUMBING_20260929: identity ON -> governed TEXT_CANON age
    # (Jarek 16, never the "young adult" fallback); gender line only from sealed canon.
    _id_on, _id_contract = _identity_contract_for(primary)
    if _id_on:
        if _id_contract is not None:
            age_canon = _id_contract.vd_age
        gender = _identity_contract_sex(_id_contract)
    body = _clean_canon_token(primary.get("body_type") or "") if isinstance(primary, dict) else ""
    # Build the appearance line, then FORCE the precise weapon lock so the model
    # cannot drift to a staff/polearm (user finding #4). Strip any loose weapon
    # word the Bible contributed; the lock phrase is the single source of truth.
    appearance_tokens = [t for t in char_tokens if not _looks_like_weapon(t)]
    appearance_line = ", ".join(dict.fromkeys(appearance_tokens)) if appearance_tokens else "the protagonist"
    identity_bits = [f"Name: {primary.get('name', 'the protagonist')}"]
    if gender:
        identity_bits.append(f"Gender: {gender}")
    identity_bits.append(f"Age: {age_canon}")
    if body:
        identity_bits.append(f"Build: {body}")
    identity_bits.append(f"Appearance: {appearance_line}")
    # Explicit, unambiguous weapon lock appended to the identity block.
    identity_bits.append(f"Weapon: {_weapon_lock_phrase()}")
    identity_block = "; ".join(identity_bits)
    wardrobe_line = ""
    weapon_line = ""
    if _id_on:
        # Part A (flag ON): the Character Identity block is identity-only. Wardrobe and the
        # character's OWN canon weapon move to separate domain sections (not identity
        # authority); HUD / qi / glyph effects stay out of the block (Power line unchanged).
        from tools.identity_preservation import (identity_lock_denylist_hits, record_identity_only_lock,
                                                 visual_director_identity_bits)
        pname = primary.get("name", "the protagonist") if isinstance(primary, dict) else "the protagonist"
        if _id_contract is not None:
            identity_bits = [f"Name: {pname}"] + visual_director_identity_bits(_id_contract)
        else:
            lock = _appearance_lock(primary, None) if isinstance(primary, dict) and primary else {}
            hair = _clean_canon_token(lock.get("hair", "")) if lock.get("hair") else ""
            eyes = _clean_canon_token(lock.get("eyes", "")) if lock.get("eyes") else ""
            only = record_identity_only_lock(hair, eyes, body)
            identity_bits = [f"Name: {pname}", f"Age: {age_canon}"]
            if only and not identity_lock_denylist_hits(only):
                identity_bits.append(f"Appearance: {only}")
        identity_block = "; ".join(identity_bits)
        wardrobe_line = ", ".join(_primary_wardrobe_tokens(primary))
        weapons = _primary_canon_weapons(primary)
        weapon_line = ", ".join(_WEAPON_LOCK_NEUTRAL if w == _JIAN_CANON_WEAPON else w for w in weapons)

    env_line = ""
    if location:
        env_bits = [str(location.get("name", ""))]
        if location.get("architecture"):
            arch = str(location["architecture"]).replace("_", " ")
            # Strip banner references from architecture: banners are NOT emitted
            # positively (Slice A.3: a positive banner cue gives SDXL a strong
            # surface to invent pseudo-calligraphy; the global negative already
            # discourages text). Keep only the structural architecture.
            arch = ", ".join(b for b in arch.split(",") if "banner" not in b.lower())
            if "n/a" not in arch and "none" not in arch.lower() and arch.strip():
                env_bits.append(arch)
        env_line = ", ".join(b for b in env_bits if b)

    palette_hint = _palette_phrase(palette)
    prompts: List[str] = []
    genre = NOVEL_GENRE_LABEL.get(str(novel).lower(), "fantasy illustration")
    for shot in shots:
        # Slice A.4 (user-directed, evidence from Run 4): ordering experiments
        # hit diminishing returns — Run 4 action fidelity FELL 7.5->5.5 because
        # SDXL treats the labeled "Narrative Objective:" / "Action:" headings as
        # descriptive prose, not hard constraints. Replace those two labeled
        # sections with ONE imperative scene description ("Depict <event>.")
        # that encodes the visible event as a direct instruction. Everything
        # else (Setting, Environment State, Character Identity, Camera,
        # Lighting, Power, Emotion, Palette, Consistency) is unchanged.
        # SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Part E/F): STILL_ROLE + CAMERA + LOCATION lead in the
        # first sentence so they survive the 77-token CLIP window; beat/action/subject follow in 'Depict'.
        _lead = str(shot.get("effective_lead") or "").strip()
        parts = [f"{genre}, vertical 9:16, {_lead}." if _lead else f"{genre}, vertical 9:16."]
        imperative = _imperative_scene(shot, primary.get("name", "the protagonist") if isinstance(primary, dict) else "the protagonist")
        if imperative:
            parts.append(imperative)
        setting_bits = [env_line] if env_line else []
        setting_line = ", ".join(b for b in setting_bits if b)
        if setting_line:
            parts.append(f"Setting: {setting_line}.")
        if shot.get("environment_state"):
            parts.append(f"Environment State: {shot['environment_state']}.")
        parts.append(f"Character Identity: {identity_block}.")
        if wardrobe_line:
            parts.append(f"Wardrobe: {wardrobe_line}.")
        if weapon_line:
            parts.append(f"Weapon: {weapon_line}.")
        parts.append(f"Camera: {shot.get('camera', 'wide cinematic')}.")
        # Slice A.7: explicit POSE (body mechanics) + EXPRESSION (face) as two
        # independent fields so each constraint is separately tunable, instead
        # of one combined body+emotion blob.
        if shot.get("action"):
            parts.append(f"Pose: {shot['action']}.")
        if shot.get("expression"):
            parts.append(f"Expression: {shot['expression']}.")
        if shot.get("lighting"):
            parts.append(f"Lighting: {shot['lighting']}.")
        if shot.get("effect"):
            parts.append(f"Power: {shot['effect']}.")
        if palette_hint:
            parts.append(f"Palette: {palette_hint}.")
        parts.append("Consistent character design, canon-accurate.")
        prompts.append(" ".join(p for p in parts if p))
    return prompts


def _imperative_scene(shot: Dict[str, Any], name: str = "the protagonist") -> str:
    """Collapse the labeled Narrative Objective + Action into one imperative
    scene description (Slice A.4). SDXL reads this as a direct instruction
    rather than descriptive prose, which improved event adherence in testing.
    The Action phrase carries the physical event; we prefix it with 'Depict'
    and the character NAME (the action text has no subject of its own) and,
    when the objective adds context the action lacks, append it as a clause.
    """
    obj = (shot.get("narrative_objective") or "").strip().rstrip(".")
    act = (shot.get("action") or "").strip().rstrip(".")
    # ensure the event is bound to the protagonist (action text is subjectless)
    subject = name if name and name.lower() not in act.lower() else ""
    core = f"{subject} {act}".strip() if subject else act
    if act and obj and obj.lower() not in act.lower():
        # objective supplies context (the 'why'/scene) the action omits
        scene = f"Depict {core}, as {obj}."
    elif act:
        scene = f"Depict {core}."
    elif obj:
        scene = f"Depict {obj}."
    else:
        return ""
    return scene


def _identity_vd_structured_intent(scene_composition: Any):
    """IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Part G, flag ON only): the structured scene
    composition supplied by the upstream request (explicit scene_composition, else the ambient
    ImageIntent bound by the production caller). Returns (request or None, non-depiction class or "").
    Only STRUCTURED fields count (scene subject / asset role / background-only marker); free text never."""
    from tools.identity_preservation import (ASSET_ROLE_CLASSES, NON_DEPICTION_INTENT_CLASSES,
                                             SCENE_SUBJECT_CLASSES, _merge_intent_requests, _vocab_key,
                                             coerce_image_intent_request, current_image_intent)
    req = _merge_intent_requests(current_image_intent(), coerce_image_intent_request(scene_composition))
    if req is None or req.depicted_characters:
        return req, ""
    subj = _vocab_key(req.scene_subject)
    if subj:
        cls = SCENE_SUBJECT_CLASSES.get(subj, "")
        return req, (cls if cls in NON_DEPICTION_INTENT_CLASSES else "")
    for rv in (req.asset_role, req.requested_asset_type):
        cls = ASSET_ROLE_CLASSES.get(_vocab_key(rv), "")
        if cls:
            return req, (cls if cls in NON_DEPICTION_INTENT_CLASSES else "")
    if req.background_only is True:
        return req, "ENVIRONMENT_ONLY"
    return req, ""


def _assemble_non_depiction_prompts(novel: str, shots: List[Dict[str, Any]], location: Optional[Dict[str, Any]],
                                    palette: Dict[str, Any], scene_text: str, shots_text: Optional[List[str]],
                                    intent_class: str) -> List[str]:
    """Flag ON, structured non-depiction scene with no named character: scenery / environment / object
    prompts with NO Character Identity block and NO protagonist subject (Part G). Environment wording
    is taken from the same location / shot data as the character path (not remediated here)."""
    genre = NOVEL_GENRE_LABEL.get(str(novel).lower(), "fantasy illustration")
    env_line = ""
    if location:
        env_line = ", ".join(b for b in [str(location.get("name", ""))] if b)
    palette_hint = _palette_phrase(palette)
    focus = {"OBJECT_ONLY": "object still life", "ENVIRONMENT_ONLY": "environment plate",
             "SCENERY_ONLY": "establishing scenery", "ABSTRACT": "abstract composition"}.get(intent_class, "scenery")
    prompts: List[str] = []
    beats = list(shots_text or []) or [scene_text]
    for i, shot in enumerate(shots or [{}]):
        beat = str(beats[i] if i < len(beats) else beats[-1] if beats else "").strip().rstrip(".")
        _lead = str(shot.get("effective_lead") or "").strip()
        parts = [f"{genre}, vertical 9:16, {focus}, {_lead}." if _lead else f"{genre}, vertical 9:16, {focus}."]
        if beat:
            parts.append(f"Depict {beat}.")
        if env_line:
            parts.append(f"Setting: {env_line}.")
        if shot.get("environment_state"):
            parts.append(f"Environment State: {shot['environment_state']}.")
        parts.append(f"Camera: {shot.get('camera', 'wide cinematic')}.")
        if shot.get("lighting"):
            parts.append(f"Lighting: {shot['lighting']}.")
        if palette_hint:
            parts.append(f"Palette: {palette_hint}.")
        parts.append("No people, no figures, no characters.")
        prompts.append(" ".join(p for p in parts if p))
    return prompts


def build_visual_scene_package(
    novel: str,
    chapter: str,
    scene_text: str,
    shots_text: Optional[List[str]] = None,
    *,
    scene_composition: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Slice 1 entry point.

    Input:  novel abbreviation, chapter label, free-text scene description.
            Optional shots_text: the EXACT per-image narrative beats (so each
            shot gets its own objective instead of the whole scene repeated).
    Output: VisualScenePackage with character_locks, shot_plan,
            negative_prompt, and image_prompts (ready for metadata.json).
    """
    # SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Part A/H): canonical novel id before palette, genre,
    # location resolution and composition ('Eternal Nexus' / 'EN' / ' en ' -> 'en'). Unknown values pass
    # through unchanged (no guess) and resolve no Bible canon.
    _input_novel = novel
    try:
        from tools.novel_id import normalize_novel_id as _normalize_novel_id
        novel = _normalize_novel_id(novel) or novel
    except Exception:  # noqa: BLE001
        pass
    profiles = load_character_profiles()
    locations = load_locations()
    palette = load_novel_palette(novel)

    warnings: List[str] = []
    char_names = extract_character_names(scene_text, profiles)
    chars = [profiles[n] for n in char_names if n in profiles]
    _id_on = _identity_contract_for({})[0]
    _intent_req, _nondepiction = (None, "")
    _intent_extra: Dict[str, Any] = {}
    if _id_on:
        # IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Part G): depiction intent from VD scene
        # structure. Named characters -> depicted subjects; no names + structured non-depiction
        # composition -> scenery (no protagonist injection); otherwise the protagonist injection
        # below stays (safe default: potentially governed).
        _intent_req, _nondepiction = _identity_vd_structured_intent(scene_composition)
        if chars:
            _nondepiction = ""
    if not chars and _id_on and not _nondepiction:
        _gov = _identity_on_governed_primary(novel)
        if _gov and _gov in profiles:
            chars = [profiles[_gov]]
    location = match_location(scene_text, locations, novel)
    scene_env_spec = resolve_scene_environment(
        novel, scene_text, location=location, locations=locations,
        shots_text=shots_text,
    )

    character_locks = [_appearance_lock(c, warnings) for c in chars]
    shots = _build_shot_plan(novel, chars, location, shots_text=shots_text, scene_text=scene_text)
    negative = _negative_prompt(chars[0]) if chars else list(CANON_NEGATIVE_CONSTRAINTS)
    if _id_on and _nondepiction:
        image_prompts = _assemble_non_depiction_prompts(
            novel, shots, location, palette, scene_text, shots_text, _nondepiction)
    else:
        image_prompts = _assemble_image_prompts(
            novel, chapter, scene_text, chars, shots, location, palette, warnings=warnings
        )
    if _id_on:
        from tools.identity_preservation import (ImageIntentRequest, normalize_identity_character_key,
                                                 register_prompt_image_intent)
        if _nondepiction:
            _vd_req = ImageIntentRequest(
                scene_subject={"SCENERY_ONLY": "scenery", "ENVIRONMENT_ONLY": "environment",
                               "OBJECT_ONLY": "object", "ABSTRACT": "abstract"}[_nondepiction],
                background_only=True if _nondepiction == "ENVIRONMENT_ONLY" else None,
                origin="visual_director.structured_scene_composition")
            _vd_source = "STRUCTURED_SCENE_SUBJECT"
        elif char_names:
            _vd_req = ImageIntentRequest(
                depicted_characters=tuple(str(c.get("name", "")) for c in chars if isinstance(c, dict) and c.get("name")),
                origin="visual_director.scene_named_characters")
            _vd_source = "STRUCTURED_DEPICTED_CHARACTER"
        elif _intent_req is not None and _intent_req.depicted_characters:
            _vd_req = ImageIntentRequest(depicted_characters=tuple(_intent_req.depicted_characters),
                                         origin="visual_director.upstream_depicted_characters")
            _vd_source = "STRUCTURED_DEPICTED_CHARACTER"
        elif chars:
            # injected governed protagonist (no names, no structured non-depiction marker): novel
            # membership is NOT depiction evidence, so no structured intent is registered; the emitted
            # Character Identity block forces governed review downstream (safe default).
            _vd_req = ImageIntentRequest(origin="visual_director.safe_default_protagonist")
            _vd_source = "SAFE_DEFAULT_NO_STRUCTURED_INTENT"
        else:
            _vd_req = ImageIntentRequest(origin="visual_director.no_structured_intent")
            _vd_source = "SAFE_DEFAULT_NO_STRUCTURED_INTENT"
        for _p in image_prompts:
            register_prompt_image_intent(_p, _vd_req)
        _intent_extra["image_intent"] = {
            "IMAGE_INTENT_CLASS": _nondepiction or (
                "GOVERNED_CHARACTER_DEPICTION" if any(normalize_identity_character_key(c.get("name", ""))
                                                      for c in chars if isinstance(c, dict))
                else "NON_GOVERNED_CHARACTER_DEPICTION" if chars else "UNDETERMINED"),
            "IMAGE_INTENT_SOURCE": _vd_source,
            "request": _vd_req.to_dict(),
            "upstream_request": _intent_req.to_dict() if _intent_req is not None else None,
        }

    return {
        "novel": novel,
        "input_novel": _input_novel,
        "normalized_novel_id": novel if str(novel) in ("ha", "en", "hp", "sf") else "UNRESOLVED",
        "chapter": chapter,
        "scene_summary": scene_text,
        "shots_text": shots_text or [],
        "characters": chars,
        "character_locks": character_locks,
        "environment": (
            location
            if location
            else {
                "novel": novel,
                "palette_ref": palette.get("color_grading", ""),
                "location_id": scene_env_spec.location_id,
                "location_name": scene_env_spec.location_name,
                "authority": scene_env_spec.authority,
                "place_phrase": scene_env_spec.place_phrase,
                "unknown_location": scene_env_spec.unknown_location,
            }
        ),
        "scene_environment": scene_env_spec.to_dict(),
        "shots": shots,
        "style_constraints": {
            "novel": novel,
            "palette_ref": palette.get("color_grading", ""),
            "priority": ["character_identity", "emotion", "story_moment", "composition", "style"],
        },
        "image_prompts": image_prompts,
        "negative_prompt": negative,
        # explicit diagnostics: malformed/contradictory canon is surfaced, never
        # silently dropped (prerequisite for integration review).
        "canon_warnings": warnings,
        # compatibility shim: downstream metadata.json expects these names
        "image_sources": [],
        **_intent_extra,
    }
