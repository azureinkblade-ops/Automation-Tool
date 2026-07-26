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
    """Find a recurring location whose name/id keywords appear in scene text."""
    text = str(scene_text or "").lower()
    nov = str(novel).lower()
    best: Optional[Dict[str, Any]] = None
    best_score = 0
    for loc in locations:
        if nov and str(loc.get("novel") or "").lower() != nov:
            continue
        hay = f"{loc.get('name', '')} {loc.get('id', '')} {loc.get('history', '')}".lower()
        score = sum(1 for word in hay.split() if len(word) > 3 and word in text)
        if score > best_score:
            best_score = score
            best = loc
    return best if best_score > 0 else None


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
    """Three-shot cinematic plan per the user's brief + Visual Creative Director
    priority (character identity > emotion > story moment > composition > style).

    Slice A: each shot now carries its OWN narrative objective (not the shared
    scene_text repeated 3x), a pose/action, explicit camera direction, emotion,
    and an ENVIRONMENT STATE block derived from the matched location's
    damage_state / weather / ambient_particles (so SDXL images the *condition*
    of the place, not just its name). This directly attacks the A/B findings:
    scene repetition, static descriptors, and 'beautiful but wrong location'.
    """
    primary = characters[0] if characters else {}
    primary_name = primary.get("name") or "the protagonist"
    env_name = location.get("name") if location else f"the {novel.upper()} setting"
    lighting = location.get("lighting") if location else primary.get("lighting_preference") or ""
    magic = primary.get("magic_style") or location.get("magic_effects") or ""

    gender = _derive_gender(scene_text) if scene_text else (
        _derive_gender(primary.get("notes", "")) if isinstance(primary, dict) else ""
    )

    # Environment STATE: location tells SDXL WHERE; state tells SDXL WHAT
    # HAPPENED THERE. Build from the matched location's damage/weather/particle
    # fields so a 'ruined' site renders ruined, not pristine.
    # Field-hygiene (user finding #1): the frozen Bible sometimes stores an
    # abstract state word like 'ordered' in damage_state that directly
    # CONTRADICTS a 'ruined' scene cue and makes SDXL draw intact temples. We
    # drop those contradictory abstract words and, when the scene text or the
    # location implies ruin, inject concrete ruin descriptors instead.
    state_bits: List[str] = []
    if location:
        def _skip(v: str) -> bool:
            vl = v.lower()
            return vl in ("intact", "n/a", "none", "") or "n/a" in vl or "none" in vl
        dmg = str(location.get("damage_state", "")).replace("_", " ").strip()
        if dmg and not _skip(dmg):
            # drop individual contradictory abstract tokens (e.g. 'ordered',
            # 'pristine') that conflict with a ruined scene, keep the rest.
            dmg_tokens = [t for t in dmg.split(",") if t.strip().lower() not in _RUIN_CONTRADICTORY]
            dmg_clean = ", ".join(dict.fromkeys(t.strip() for t in dmg_tokens if t.strip()))
            if dmg_clean:
                state_bits.append(dmg_clean)
        weather = str(location.get("weather", "")).replace("_", " ").strip()
        if weather and not _skip(weather):
            state_bits.append(weather)
        for key in ("fog_density", "ambient_particles"):
            v = str(location.get(key, "")).replace("_", " ").strip()
            if v and not _skip(v):
                state_bits.append(v)
    # Concrete ruin language when the scene or location implies abandonment.
    # This overrides the Bible's 'ordered' tendency (user finding #1).
    ruin_signals = ("ruin", "ruined", "collaps", "broken", "abandon", "wreck", "decay")
    implies_ruin = any(s in scene_text.lower() for s in ruin_signals) or (
        location and any(s in str(location.get("damage_state", "")).lower() for s in ("ruin", "ruined", "collaps", "broken"))
    )
    if implies_ruin and not any(s in " ".join(state_bits).lower() for s in ("ruin", "collaps", "broken", "abandon")):
        state_bits.append("abandoned for centuries, partially collapsed, cracked stone stairs, broken jade railings, fallen roof tiles, faded and torn banners, dust and mist inside the hall")
    env_state = ", ".join(dict.fromkeys(state_bits)) if state_bits else ""

    # Banners belong under SETTING (user finding #5 + #6), never in the
    # Character Identity block. Collect from the character's clothing placement
    # tokens and from the location; render as plain cloth with NO pseudo-text.
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

    # Per-image narrative objectives. If caller passes shots_text (the exact
    # per-image beats from the app), use them. Otherwise narrate a generic
    # arrival / ascent / climax arc so the three frames progress. The fallback
    # is novel-agnostic (uses the matched character + location) so non-HP
    # novels do not get HP-specific "sect ruins / jade altar" wording.
    if shots_text and len(shots_text) >= 3:
        objectives = [s.strip() for s in shots_text[:3]]
    else:
        place = env_name or f"the {novel.upper()} setting"
        objectives = [
            f"Establish {primary_name} arriving at {place}",
            f"Show {primary_name} advancing deeper into {place}",
            f"Reveal the hidden power as the moment turns",
        ]

    # Pose / action per shot (SDXL treats weak verbs as suggestions; user
    # finding #2/#4: 'climbing' -> standing near stairs, 'kneeling' -> standing
    # hero). Use STRONG bodily mechanics so the requested motion is unambiguous.
    poses = [
        "standing at the entrance, head tilted upward, looking at the ancient formations above the gateway",
        "midway up the broken staircase, one foot planted on a higher step, body leaning forward, robe trailing behind him, right hand hovering over the sword hilt",
        "kneeling on one knee before the altar, left hand pressed to the cold stone, silver qi visibly flowing through the dormant formation lines on the floor",
    ]
    # Camera language must AGREE with the pose (user finding #3): 'low-angle
    # hero shot' biased the kneeling frame to an upright stance, so the climax
    # uses a three-quarter side view from altar height instead.
    cameras = [
        # Slice A.5 (user-directed, evidence from Run 5): the bottleneck is
        # COMPOSITION, not wording. SDXL is trained to favor sweeping
        # environmental concept art, so "wide low-angle environmental shot"
        # demotes Liang to a speck. Reframe to keep Liang visually PROMINENT
        # (specify a relative framing ratio + environmental context retained)
        # without changing any prompt semantics elsewhere.
        # Slice A.7: make character SIZE an explicit, evaluable rule (Run 7
        # review) - target ~20-25% of frame height, recognizable at thumbnail.
        "full-body medium shot of Liang entering the ruined sect hall; Liang fills approximately 20 to 25 percent of the frame height and is immediately recognizable even at thumbnail size, while the towering ruined sect hall and gateway fill the background",
        "over-the-shoulder tracking shot from behind Liang as he climbs the broken stair; Liang fills approximately 20 to 25 percent of the frame height and is clearly visible and prominent, with the jade altar rising ahead",
        "three-quarter side view from altar height, Liang clearly the subject kneeling on one knee before the altar with the dormant formation glowing on the floor behind him; Liang fills approximately 20 to 25 percent of the frame height",
    ]
    emotions = ["awe and uncertainty", "determination", "discovery"]
    # Slice A.7 (user review Run 7): separate POSE (body mechanics) from
    # EXPRESSION (emotional face) so each constraint is explicit and tunable,
    # rather than combining them into one body+emotion blob.
    expressions = ["quiet awe", "determined focus", "solemn discovery"]
    shot_types = ["establishing", "travel", "climax"]

    shots = []
    for i in range(3):
        # Slice A.6 (user-directed, Run 6 evidence): for an INTERACTION /
        # RITUAL shot the narrative hinge is the pose, not the architecture. The
        # long environmental inventory (mist layers, falling leaves, qi motes,
        # cracked stairs, broken railings, roof tiles, banners, dust, hall)
        # competes for model attention with the kneeling / hand-on-stone /
        # formation interaction. Trim the env-state to a minimal location
        # establishing descriptor so attention is freed for the action. Non-
        # interaction shots keep the full descriptive env-state.
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
        parts = [f"{genre}, vertical 9:16."]
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


def build_visual_scene_package(
    novel: str,
    chapter: str,
    scene_text: str,
    shots_text: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Slice 1 entry point.

    Input:  novel abbreviation, chapter label, free-text scene description.
            Optional shots_text: the EXACT per-image narrative beats (so each
            shot gets its own objective instead of the whole scene repeated).
    Output: VisualScenePackage with character_locks, shot_plan,
            negative_prompt, and image_prompts (ready for metadata.json).
    """
    profiles = load_character_profiles()
    locations = load_locations()
    palette = load_novel_palette(novel)

    warnings: List[str] = []
    char_names = extract_character_names(scene_text, profiles)
    chars = [profiles[n] for n in char_names if n in profiles]
    location = match_location(scene_text, locations, novel)

    character_locks = [_appearance_lock(c, warnings) for c in chars]
    shots = _build_shot_plan(novel, chars, location, shots_text=shots_text, scene_text=scene_text)
    negative = _negative_prompt(chars[0]) if chars else list(CANON_NEGATIVE_CONSTRAINTS)
    image_prompts = _assemble_image_prompts(
        novel, chapter, scene_text, chars, shots, location, palette, warnings=warnings
    )

    return {
        "novel": novel,
        "chapter": chapter,
        "scene_summary": scene_text,
        "shots_text": shots_text or [],
        "characters": chars,
        "character_locks": character_locks,
        "environment": location or {"novel": novel, "palette_ref": palette.get("color_grading", "")},
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
    }
