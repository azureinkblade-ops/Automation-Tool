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

def _appearance_lock(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten Bible appearance/clothing/weapon into a Director lock dict.

    Note: in the Bible YAML, body_type/age/height live UNDER `appearance:`,
    while clothing/weapons are top-level. Read both locations defensively.
    """
    ap = profile.get("appearance") or {}
    hair = ap.get("hair") or {}
    eyes = ap.get("eyes") or {}

    def _as_str(v: Any) -> str:
        # Bible YAML can contain malformed entries (e.g. an unquoted value with
        # parens parsed as a nested dict). Never crash; stringify safely.
        if isinstance(v, dict):
            return " ".join(f"{k} {val}" for k, val in v.items())
        return str(v or "").replace("_", " ").strip()

    def _as_list(v: Any) -> List[str]:
        if not isinstance(v, list):
            return [_as_str(v)] if v else []
        return [_as_str(item) for item in v]

    lock = {
        "name": profile.get("name"),
        "hair": _as_str(hair.get("style")),
        "eyes": _as_str(eyes.get("color")),
        # body_type / age may be under appearance OR top-level
        "body_type": _as_str(ap.get("body_type") or profile.get("body_type")),
        "age": _as_str(ap.get("age") or profile.get("age")),
        "height": _as_str(ap.get("height") or profile.get("height")),
        "clothing": _as_list(profile.get("clothing", []) or []),
        "weapons": _as_list(profile.get("weapons", []) or []),
        "magic_style": _as_str(profile.get("magic_style")),
        "lighting_preference": _as_str(profile.get("lighting_preference")),
    }
    return lock


def _character_lock_tokens(lock: Dict[str, Any]) -> List[str]:
    """Human-readable appearance tokens for prompt assembly.

    Editorial noise (parenthetical notes, per-chapter provenance, negation
    annotations like "carries NO weapon at Ch140") is stripped so malformed or
    over-annotated Bible data degrades gracefully instead of contaminating
    prompts. Only positive visual descriptors survive.
    """
    # tokens that describe a fact but NOT a usable visual attribute
    _NON_VISUAL = (
        "no weapon", "note", "accept", "dropped", "sdxl", "staff",
        "ch140", "chapter", "missing", "unknown",
    )

    def keep(token: str) -> bool:
        t = token.lower()
        if not t:
            return False
        if any(bad in t for bad in _NON_VISUAL):
            return False
        return True

    raw: List[str] = []
    if lock.get("hair"):
        raw.append(f"{_clean_canon_token(lock['hair'])} hair")
    if lock.get("eyes"):
        raw.append(f"{_clean_canon_token(lock['eyes'])} eyes")
    # age literals like "reborn_adult"/"young_adult" are abstract; convey the
    # concrete body_type instead so the generator gets a usable signal.
    if lock.get("body_type") and "unknown" not in lock["body_type"]:
        raw.append(_clean_canon_token(lock["body_type"]))
    for c in lock.get("clothing", []):
        cleaned = _clean_canon_token(c)
        if cleaned:
            raw.append(cleaned)
    for w in lock.get("weapons", []):
        cleaned = _clean_canon_token(w)
        if cleaned:
            raw.append(cleaned)
    # dedupe (case-insensitive) while preserving order
    seen: set[str] = set()
    tokens: List[str] = []
    for t in raw:
        key = t.lower()
        if key not in seen and keep(t):
            seen.add(key)
            tokens.append(t)
    return tokens


def _build_shot_plan(novel: str, characters: List[Dict[str, Any]], location: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Three-shot cinematic plan per the user's brief + Visual Creative Director
    priority (character identity > emotion > story moment > composition > style)."""
    primary = characters[0] if characters else {}
    primary_name = primary.get("name") or "the protagonist"
    env_name = location.get("name") if location else f"the {novel.upper()} setting"
    lighting = location.get("lighting") if location else primary.get("lighting_preference") or ""
    magic = primary.get("magic_style") or location.get("magic_effects") or ""

    shots = [
        {
            "type": "establishing",
            "camera": "wide cinematic",
            "purpose": "where are we / what is happening",
            "environment": env_name,
            "lighting": str(lighting).replace("_", " "),
        },
        {
            "type": "character",
            "camera": "close portrait",
            "purpose": "who matters / what emotion",
            "subject": primary_name,
            "emotion": "controlled resolve",
            "lighting": str(primary.get("lighting_preference") or "").replace("_", " ") or (str(location.get("lighting") or "") if location else ""),
        },
        {
            "type": "action",
            "camera": "low angle",
            "purpose": "why should the viewer care",
            "effect": str(magic).replace("_", " "),
        },
    ]
    return shots


def _negative_prompt(profile: Dict[str, Any]) -> List[str]:
    """Canon negative constraints + any character-specific forbidden changes."""
    neg = list(CANON_NEGATIVE_CONSTRAINTS)
    notes = str(profile.get("notes") or "").lower()
    if "silver sword became staff" in notes or "soulblade" in notes or "sword" in notes:
        # protect the canonical bladed weapon from model drift
        neg.append("weapon became staff")
    return neg


def _assemble_image_prompts(
    novel: str,
    chapter: str,
    scene_text: str,
    characters: List[Dict[str, Any]],
    shots: List[Dict[str, Any]],
    location: Optional[Dict[str, Any]],
    palette: Dict[str, Any],
) -> List[str]:
    """One Bible-enriched prompt string per shot. The existing generator consumes
    this list exactly like the legacy `image_prompts` list."""
    char_tokens = []
    for c in characters:
        char_tokens.extend(_character_lock_tokens(_appearance_lock(c)))
    char_line = ", ".join(dict.fromkeys(char_tokens)) if char_tokens else "the protagonist"
    env_line = ""
    if location:
        env_bits = [str(location.get("name", ""))]
        if location.get("architecture"):
            env_bits.append(str(location["architecture"]).replace("_", " "))
        if location.get("weather"):
            env_bits.append(str(location["weather"]).replace("_", " "))
        env_line = ", ".join(env_bits)
    palette_hint = _palette_phrase(palette)
    prompts: List[str] = []
    for shot in shots:
        parts = [f"Cultivation fantasy illustration, vertical 9:16."]
        parts.append(f"Scene: {scene_text}.")
        if char_line:
            parts.append(f"Subject: {char_line}.")
        if env_line:
            parts.append(f"Setting: {env_line}.")
        parts.append(f"Shot: {shot['type']} ({shot['camera']}).")
        if shot.get("lighting"):
            parts.append(f"Lighting: {shot['lighting']}.")
        if shot.get("effect"):
            parts.append(f"Power: {shot['effect']}.")
        if palette_hint:
            parts.append(f"Palette: {palette_hint}.")
        parts.append("Consistent character design, canon-accurate.")
        prompts.append(" ".join(p for p in parts if p))
    return prompts


def build_visual_scene_package(
    novel: str,
    chapter: str,
    scene_text: str,
) -> Dict[str, Any]:
    """Slice 1 entry point.

    Input:  novel abbreviation, chapter label, free-text scene description.
    Output: VisualScenePackage with character_locks, shot_plan,
            negative_prompt, and image_prompts (ready for metadata.json).
    """
    profiles = load_character_profiles()
    locations = load_locations()
    palette = load_novel_palette(novel)

    char_names = extract_character_names(scene_text, profiles)
    chars = [profiles[n] for n in char_names if n in profiles]
    location = match_location(scene_text, locations, novel)

    character_locks = [_appearance_lock(c) for c in chars]
    shots = _build_shot_plan(novel, chars, location)
    negative = _negative_prompt(chars[0]) if chars else list(CANON_NEGATIVE_CONSTRAINTS)
    image_prompts = _assemble_image_prompts(novel, chapter, scene_text, chars, shots, location, palette)

    return {
        "novel": novel,
        "chapter": chapter,
        "scene_summary": scene_text,
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
        # compatibility shim: downstream metadata.json expects these names
        "image_sources": [],
    }
