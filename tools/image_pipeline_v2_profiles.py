"""Semantic profile split for cinematic-promo vs photorealistic.

Canonical public profile for the existing azink_real / lora_realistic_posts
path is cinematic-promo. photorealistic is a distinct routing target with no
qualified photographic asset. Comic V2 is not authorized by this module.

This module does not load models, run GPU, or rename LoRA files.
Studio Bible projection is imported only when a canon contract is requested.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

CINEMATIC_PROMO_PROFILE = "cinematic-promo"
PHOTOREALISTIC_PROFILE = "photorealistic"
MAIN_POSTS_PROFILE = "main_posts"
COMIC_PROFILE = "comic"

# Internal V2 id and activation storage key for the existing cinematic route.
LEGACY_REALISTIC_PROFILE = "realistic"
LEGACY_REALISTIC_TRACK = "realistic-posts"

CINEMATIC_PROMO_LORA_ASSET_ID = "lora_realistic_posts"
CINEMATIC_PROMO_TRIGGER = "azink_real"
CINEMATIC_PROMO_LORA_RELATIVE = r"loras\realistic_posts\pytorch_lora_weights.safetensors"
CINEMATIC_PROMO_LORA_SHA256 = "FF795D7028D3473083901EBCE2CC7B284D12FF6C904E7834428A0213CD92C564"

PHOTOREALISTIC_MODEL_NAME = "RealVisXL_V5.0"
PHOTOREALISTIC_ASSET = "RealVisXL_V5.0_fp16"
PHOTOREALISTIC_ASSET_TYPE = "checkpoint"
PHOTOREALISTIC_BASE_FAMILY = "SDXL"
PHOTOREALISTIC_LICENSE = "CreativeML Open RAIL++-M (openrail++)"
PHOTOREALISTIC_CHECKPOINT_FILENAME = "RealVisXL_V5.0_fp16.safetensors"
PHOTOREALISTIC_CHECKPOINT_SHA256 = "6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80"
PHOTOREALISTIC_CHECKPOINT_PATH = Path(
    r"C:\Users\David\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\checkpoints"
) / PHOTOREALISTIC_CHECKPOINT_FILENAME
PHOTOREALISTIC_PROFILE_AVAILABLE = False
PHOTOREALISTIC_READY = False

PHOTOREALISTIC_UNAVAILABLE_MESSAGE = (
    "photorealistic profile is unavailable/unqualified: "
    "PHOTOREALISTIC_PROFILE_AVAILABLE=NO; no qualified photographic SDXL "
    "model or LoRA is installed. Refusing generation. Will not fall through "
    "to cinematic-promo, realistic-posts, main-posts, local SD, cloud, or stock."
)

# Exact style tokens that must route to photorealistic.
PHOTOREALISTIC_STYLE_TOKENS = frozenset({
    "photorealistic",
    "photoreal",
    "photo-real",
    "photo real",
    "photographic",
    "live action",
    "live-action",
})

# Prompt phrases checked before bare "realistic" so photorealistic cannot
# share the cinematic path. Longest phrases first.
PHOTOREALISTIC_PROMPT_TERMS: Tuple[str, ...] = (
    "photorealistic",
    "photo-real",
    "photo real",
    "photoreal",
    "photographic",
    "live-action",
    "live action",
)

LEGACY_REALISTIC_ALIASES_REMAINING: Dict[str, str] = {
    "realistic": (
        "Internal V2 profile id and activation storage key for the existing "
        "enabled cinematic route. Kept so the persisted activation flag and "
        "existing cinematic callers continue to mean cinematic-promo. Does "
        "not accept photoreal, photo-real, photographic, live action, or "
        "photorealistic."
    ),
    "realistic-posts": (
        "Style-track id and existing UI option. Temporary compatibility alias "
        "of cinematic-promo, not of photorealistic. Physical LoRA directory "
        "remains loras\\realistic_posts; the weights file is not renamed."
    ),
    "cinematic realism": (
        "Keyword only. Stays on the cinematic style-track alias because it is "
        "cinematic language, not a photorealistic request."
    ),
}

LEGACY_ALIAS_PURPOSE = (
    "Temporary compatibility for the existing cinematic route only. "
    "Photorealistic words are not aliases of cinematic-promo."
)


class PhotorealisticProfileUnavailableError(Exception):
    """Fail-closed: photorealistic was requested and no qualified asset exists."""

    def __init__(self, message: str = PHOTOREALISTIC_UNAVAILABLE_MESSAGE):
        super().__init__(message)
        self.profile = PHOTOREALISTIC_PROFILE
        self.available = PHOTOREALISTIC_PROFILE_AVAILABLE
        self.asset = PHOTOREALISTIC_ASSET



_SHA256_CACHE = {}


def _sha256_file(path: Path) -> str:
    stat = path.stat()
    key = "|".join((str(path), str(stat.st_size), str(stat.st_mtime_ns)))
    cached = _SHA256_CACHE.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _SHA256_CACHE[key] = value
    return value


def photorealistic_asset_status(path: Optional[Path] = None) -> Dict[str, Any]:
    """Disk + hash gate. Missing or mismatched file stays fail-closed.

    Does not fall back to sd_xl_base_1.0 or azink_real.
    """
    target = Path(path) if path is not None else PHOTOREALISTIC_CHECKPOINT_PATH
    exists = target.is_file()
    sha = ""
    match = False
    if exists:
        sha = _sha256_file(target)
        match = sha.lower() == PHOTOREALISTIC_CHECKPOINT_SHA256.lower()
    if not exists:
        reason = (
            "no qualified photographic SDXL checkpoint is installed at "
            f"{target}"
        )
    elif not match:
        reason = (
            "photorealistic checkpoint hash mismatch for "
            f"{target.name}: expected {PHOTOREALISTIC_CHECKPOINT_SHA256}, got {sha}"
        )
    else:
        reason = ""
    ready = bool(exists and match)
    message = PHOTOREALISTIC_UNAVAILABLE_MESSAGE
    if not ready and reason:
        message = (
            "photorealistic profile is unavailable/unqualified: "
            "PHOTOREALISTIC_PROFILE_AVAILABLE=NO; "
            f"{reason}. Refusing generation. Will not fall through "
            "to cinematic-promo, realistic-posts, main-posts, local SD, cloud, or stock."
        )
    return {
        "ready": ready,
        "available": ready,
        "exists": exists,
        "sha256": sha.upper() if sha else "",
        "expected_sha256": PHOTOREALISTIC_CHECKPOINT_SHA256.upper(),
        "path": str(target),
        "asset": PHOTOREALISTIC_ASSET if ready else "NONE",
        "checkpoint": PHOTOREALISTIC_CHECKPOINT_FILENAME if ready else None,
        "message": message,
        "loads_azink_real": False,
    }


def photorealistic_asset_ready(path: Optional[Path] = None) -> bool:
    return bool(photorealistic_asset_status(path)["ready"])


def normalize_style_token(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def is_explicit_photorealistic_style(style: str) -> bool:
    token = normalize_style_token(style).replace(" - ", "-")
    compact = token.replace(" ", "-") if token in {"live action", "photo real"} else token
    return token in PHOTOREALISTIC_STYLE_TOKENS or compact in PHOTOREALISTIC_STYLE_TOKENS


def is_photorealistic_prompt_request(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered for term in PHOTOREALISTIC_PROMPT_TERMS)


def refuse_photorealistic_if_requested(style: str = "", text: str = "") -> None:
    if is_explicit_photorealistic_style(style) or (
        not str(style or "").strip() and is_photorealistic_prompt_request(text)
    ):
        raise PhotorealisticProfileUnavailableError()


def canonical_v2_profile_for_public_style(style: str) -> Optional[str]:
    """Map a public style token onto a V2 profile, or None if not V2.

    realistic / realistic-posts remain temporary aliases of the cinematic
    route and still resolve to the internal id ``realistic`` so existing
    activation and live-seam callers stay equivalent. cinematic-promo is
    the canonical public name and resolves to itself.
    """
    token = normalize_style_token(style)
    if is_explicit_photorealistic_style(token):
        return PHOTOREALISTIC_PROFILE
    if token in {CINEMATIC_PROMO_PROFILE, "cinematic promo"}:
        return CINEMATIC_PROMO_PROFILE
    if token in {LEGACY_REALISTIC_PROFILE, LEGACY_REALISTIC_TRACK}:
        return LEGACY_REALISTIC_PROFILE
    if token in {"main-posts", "main posts", "main_posts"}:
        return MAIN_POSTS_PROFILE
    return None


def public_style_pack_track(style: str, known_tracks) -> str:
    """Normalize a live caller style token onto a pack track.

    Photographic aliases become the photorealistic profile and must not be
    coerced onto main-posts, cinematic-promo, or realistic-posts. Legacy
    realistic / realistic-posts stay whatever the caller already stored when
    they are members of known_tracks. Unknown non-photographic styles stay
    main-posts so existing default callers do not change.
    """
    if is_explicit_photorealistic_style(style):
        return PHOTOREALISTIC_PROFILE
    token = str(style or "").strip()
    if token in known_tracks:
        return token
    return "main-posts"


def activation_storage_key(profile: str) -> str:
    """cinematic-promo uses the existing enabled cinematic activation flag.

    Style-track ids such as realistic-posts are not activation keys. They stay
    fail-closed at the activation module; routing maps them separately.
    """
    token = normalize_style_token(profile).replace(" ", "-")
    if token in {CINEMATIC_PROMO_PROFILE, LEGACY_REALISTIC_PROFILE}:
        return LEGACY_REALISTIC_PROFILE
    if token in {"main posts", "main-posts"}:
        return MAIN_POSTS_PROFILE
    return token


def project_shared_studio_bible_canon(
    novel: str,
    chapter: str = "",
    scene_text: str = "",
) -> Dict[str, Any]:
    """Profile-independent Studio Bible canon projection.

    Style selection may change only the style slice. Character, location,
    object, wardrobe, and cross-novel isolation come from the same adapter
    selectors used by the qualified cinematic route.
    """
    from tools import studio_bible_adapter as sba

    scene = scene_text if scene_text is not None else ""
    novel_id = sba.normalize_novel_id(novel, empty_ok=False) if novel else ""
    projection = sba.build_projection(novel_id, chapter, scene)
    if novel_id:
        sba.require_resolved_canon(projection, scene_text=scene)
    derived = sba.derive_spec_inputs(projection, scene)
    primary = sba.select_character_record(projection, scene)
    wardrobe = tuple(primary.clothing) if primary is not None else ()
    location = sba.select_location_record(projection, scene)
    effects = ()
    if location is not None and getattr(location, "magic_effects", ""):
        effects = (str(location.magic_effects),)
    return {
        "character_id": derived.get("character_id") or "",
        "subjects": tuple(derived.get("subjects") or ()),
        "location": derived.get("environment") or "",
        "object_identity": derived.get("object_identity") or "",
        "object_state": derived.get("object_state") or "",
        "object_class": derived.get("object_class") or "",
        "props": tuple(derived.get("props") or ()),
        "wardrobe": wardrobe,
        "negative_constraints": tuple(derived.get("negative_constraints") or ()),
        "supernatural_effects": effects,
        "palette": derived.get("palette") or "",
        "lighting": derived.get("lighting") or "",
        "lighting_phrase": derived.get("lighting_phrase") or "",
        "identity_lock": derived.get("identity_lock") or "",
        "camera_phrase": derived.get("camera_phrase") or "",
        "shot_language": derived.get("shot_language") or "",
        "magic_effects": derived.get("magic_effects") or "",
        "hair": derived.get("hair") or "",
        "eyes": derived.get("eyes") or "",
        "magic_style": derived.get("magic_style") or "",
        "unresolved_fields": tuple(derived.get("unresolved_fields") or ()),
        "projection_sha256": sba.projection_sha256(projection),
        "style_independent": True,
    }


def photorealistic_canon_contract(
    novel: str,
    chapter: str = "",
    scene_text: str = "",
) -> Dict[str, Any]:
    """Canon contract for the photorealistic profile.

    Binds RealVisXL only when the installed file exists and the SHA-256
    matches. Does not resolve or bind azink_real / lora_realistic_posts.
    Fail-closed when the file is missing or the hash mismatches.
    """
    status = photorealistic_asset_status()
    canon = project_shared_studio_bible_canon(novel, chapter, scene_text)
    return {
        "profile": PHOTOREALISTIC_PROFILE,
        "available": bool(status["ready"]),
        "asset": status["asset"],
        "checkpoint": status["checkpoint"],
        "checkpoint_sha256": status["sha256"] if status["ready"] else None,
        "lora_asset_id": None,
        "trigger": None,
        "loads_azink_real": False,
        "style_profile": "photographic live-action style slice",
        "fail_closed": not status["ready"],
        "canon": canon,
    }


def cinematic_promo_identity() -> Dict[str, str]:
    return {
        "profile": CINEMATIC_PROMO_PROFILE,
        "lora_asset_id": CINEMATIC_PROMO_LORA_ASSET_ID,
        "trigger": CINEMATIC_PROMO_TRIGGER,
        "lora_relative": CINEMATIC_PROMO_LORA_RELATIVE,
        "sha256": CINEMATIC_PROMO_LORA_SHA256,
        "internal_pipeline_profile": LEGACY_REALISTIC_PROFILE,
    }


def legacy_alias_report() -> Mapping[str, str]:
    return dict(LEGACY_REALISTIC_ALIASES_REMAINING)
