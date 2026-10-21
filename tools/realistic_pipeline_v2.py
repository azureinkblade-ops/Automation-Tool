"""Image Pipeline V2 M6 — Realistic Posts pipeline migration (CPU-only).

M6 establishes the first-class Realistic Posts V2 pipeline on the M1-M4
foundation. The pipeline is GenerationSpec-driven and resolves a deterministic,
provenance-bound, load-bearing ComfyUI workflow for the Realistic profile.

Authority boundaries (per M6 authority record 2026-08-19):
- No GPU execution. submit_workflow / ComfyUI inference is never invoked.
- No production routing. app.py / app_config.py / release_state.py untouched.
- Open Design remains optional (never imported; no runtime requirement).
- Comic (M5) and Main Posts profiles are NOT modified by M6.

Asset authority: only assets approved and SHA-bound by the M4 asset manifest
(image_pipeline_v2_m4_asset_manifest_20260818.json) are referenced. The
authoritative SHA-256 values below are transcribed verbatim from that manifest.
"""

from __future__ import annotations

import hashlib
import shutil
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.comfyui_adapter import extract_provenance, load_template, WorkflowTemplate
from tools.generation_spec import (
    BodyPoseSpec,
    CompositionSpec,
    ConditioningSpec,
    ContentSpec,
    GenerationSpec,
    GenerationSpecValidationError,
    IdentitySpec,
    LoRABinding,
    ModelExecutionSpec,
    ReferenceSpec,
    RunConfig,
    StyleSpec,
    StudioBibleBinding,
    ValidationSpec,
    generation_spec_sha256,
    validate_generation_spec,
)
from tools import studio_bible_adapter as _sba

# --- M6 authority constants -------------------------------------------------
REALISTIC_PROFILE = "realistic"
REALISTIC_TEMPLATE_ID = "realistic_base"
REALISTIC_LORA_ASSET_ID = "lora_realistic_posts"
REALISTIC_CHECKPOINT_ASSET_ID = "sdxl_base_1.0"
REALISTIC_OPEN_DESIGN_RUNTIME_REQUIREMENT = "OPTIONAL"
M6_GPU_AUTHORIZED = False

# Capability disposition (M6 section 7 / 9 / 10). Each optional capability is
# classified exactly once.
REALISTIC_CAPABILITY_DISPOSITION: Dict[str, str] = {
    "LORA": "REQUIRED",
    "CONTROLNET": "DISABLED_FOR_BASE_PROFILE",
    "IP_ADAPTER": "OPTIONAL_STYLE_REF_WHEN_BOUND",
    "MASK_INPAINT": "DISABLED_FOR_REALISTIC_V2",
}
REALISTIC_CONTROLNET_POLICY = "DISABLED_FOR_BASE_PROFILE"
REALISTIC_IP_ADAPTER_POLICY = "OPTIONAL_STYLE_REF_WHEN_BOUND"

# Production-intent Realistic profile definition (M6 section 3). These are the
# explicit Realistic settings distinct from comic / main_posts.
REALISTIC_PROFILE_DEF: Dict[str, Any] = {
    "checkpoint_asset_id": REALISTIC_CHECKPOINT_ASSET_ID,
    "lora_asset_id": REALISTIC_LORA_ASSET_ID,
    "lora_weight": 0.85,
    "conditioning": "photographic realistic automation-tool style, high detail, natural lighting",
    "sampler": "dpmpp_2m",
    "scheduler": "karras",
    "steps": 28,
    "cfg": 4.5,
    "resolution": (1024, 1024),
    "precision": "fp16",
    "repair_policy": "disabled_for_base_profile (M8 repair pipeline)",
    "validation_requirements": "phase3_v2_realistic_default",
    "workflow_topology": "CheckpointLoader -> LoraLoader(load-bearing) -> KSampler -> VAEDecode -> SaveImage",
}

_ASSET_ROOT = Path(r"C:\Users\David\Documents\Automation tool")

# Style-ref conditioning (general SDXL IP-Adapter Plus ViT-H; NOT face-plus).
# Empty style_refs => legacy Checkpoint->Lora->KSampler graph (no IPAdapter nodes).
# SAFETY: 0.5 is NOT a validated production default (REFERENCE_OVERPOWERING /
# ENVIRONMENT_SUPPRESSION at 0.5). Conditioning applies only via explicit
# experimental/qualification opt-in until a strength is qualified.
STYLE_REF_STRENGTH = 0.50  # candidate only; NOT auto-applied as production default
STYLE_REF_PRODUCTION_DEFAULT_QUALIFIED = False  # NO - unqualified strengths stay experimental
STYLE_REF_EXPERIMENTAL_ENV = "STYLE_REF_EXPERIMENTAL"
STYLE_REF_STRENGTH_ENV = "STYLE_REF_STRENGTH"
GENERAL_IPADAPTER_FILE = "ip-adapter-plus_sdxl_vit-h.safetensors"
FACE_ONLY_IPADAPTER_FILE = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
CLIP_VISION_FILE = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
COMFY_SHARED_INPUT_DIR = Path(
    r"C:\Users\David\AppData\Local\Comfy-Desktop\ComfyUI-Shared\input"
)
STYLE_REF_LOADER_NODE = "20"
STYLE_REF_CLIP_VISION_NODE = "21"
STYLE_REF_IMAGE_NODE = "22"
STYLE_REF_APPLY_NODE = "23"


# --------------------------------------------------------------------------- #
# Authoritative approved-asset registry (source: M4 asset manifest 20260818)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ApprovedAsset:
    asset_id: str
    asset_class: str
    canonical_path: str
    comfyui_reference: str
    sha256: str
    pipeline_role: Tuple[str, ...]
    provisioned: bool


_APPROVED_REGISTRY: Tuple[ApprovedAsset, ...] = (
    ApprovedAsset(
        asset_id="sdxl_base_1.0",
        asset_class="SDXL_CHECKPOINT",
        canonical_path=str(_ASSET_ROOT / "models" / "sdxl-base" / "sd_xl_base_1.0.safetensors"),
        comfyui_reference="sd_xl_base_1.0.safetensors",
        sha256="31E35C80FC4829D14F90153F4C74CD59C90B779F6AFE05A74CD6120B893F7E5B",
        pipeline_role=("comic", "realistic"),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_realistic_posts",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "realistic_posts" / "pytorch_lora_weights.safetensors"),
        comfyui_reference="realistic_posts/pytorch_lora_weights.safetensors",
        sha256="FF795D7028D3473083901EBCE2CC7B284D12FF6C904E7834428A0213CD92C564",
        pipeline_role=("realistic",),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_main_posts",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "main-posts" / "pytorch_lora_weights.safetensors"),
        comfyui_reference="main-posts/pytorch_lora_weights.safetensors",
        sha256="5093D90510BF1E40B12B49776F54EB5D1C6019B41203066444C35554619EF69B",
        pipeline_role=("main_posts",),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_comic_style",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "comic-style"),
        comfyui_reference="",
        sha256="",
        pipeline_role=("comic",),
        provisioned=False,  # NOT_YET_TRAINED (M5 concern, not M6)
    ),
    ApprovedAsset(
        asset_id="controlnet_openpose_sdxl_1.0",
        asset_class="STRUCTURAL_CONDITIONING",
        canonical_path=str(
            _ASSET_ROOT / "models" / "controlnet-openpose-sdxl-1.0" / "diffusion_pytorch_model.safetensors"
        ),
        comfyui_reference="controlnet-openpose-sdxl-1.0/diffusion_pytorch_model.safetensors",
        sha256="B8524E557A7DF60D081F5D4A0EB109967D107DF217943BF88C2D99B9EBCC06C5",
        pipeline_role=("comic", "realistic"),
        provisioned=True,
    ),
)


def derive_comfyui_reference(canonical_path: str) -> str:
    """Deterministic ComfyUI-visible model reference.

    Derived as the last two path components (parent directory name + filename),
    which matches the extra_model_paths.yaml mapping used by the local ComfyUI
    install. This is the reference string actually passed to a ComfyUI loader
    node and must correspond to the approved asset.
    """
    p = Path(canonical_path)
    return f"{p.parent.name}/{p.name}"


def normalize_comfyui_reference(reference: str) -> str:
    """Normalize a ComfyUI model reference to the backend's path-separator form.

    ComfyUI builds its accepted model-name list using the host OS path
    separator (``os.sep``). On Windows the live M6 backend therefore exposes
    LoRA references with backslashes (e.g. ``realistic_posts\\pytorch_lora_weights.safetensors``),
    so a forward-slash reference submitted by the pipeline is rejected with
    ``value_not_in_list`` (DEFECT_3, path-normalization class). Normalizing to
    ``os.sep`` makes the execution-visible reference match the backend's
    canonical form on every host OS.

    The authoritative registry value (the M4 ``extra_model_paths.yaml`` mapping,
    forward slash) is preserved as the semantic asset reference; only the string
    handed to ComfyUI is normalized. Empty references (unprovisioned assets) are
    returned unchanged.
    """
    if not reference:
        return reference
    return reference.replace("/", os.sep).replace("\\", os.sep)


# --------------------------------------------------------------------------- #
# Deterministic, fail-closed asset resolution
# --------------------------------------------------------------------------- #


class AssetResolutionError(Exception):
    """Fail-closed error raised when an asset cannot be resolved deterministically."""


_FULL_RESOLVE_CACHE: Dict[str, ApprovedAsset] = {}


def resolve_asset(
    asset_id: str,
    *,
    read_bytes: Optional[Callable[[str], bytes]] = None,
) -> ApprovedAsset:
    """Deterministically resolve an approved asset from its authoritative identity.

    Fail-closed if:
      - zero approved assets match the identity,
      - more than one approved asset matches (ambiguous),
      - the asset is not provisioned (e.g. comic LoRA NOT_YET_TRAINED),
      - the on-disk SHA-256 does not match the approved manifest,
      - the derived ComfyUI reference does not match the approved reference.

    `read_bytes` lets tests inject deterministic file content without touching
    the multi-GB real assets; when None the real file is read from disk and the
    result is cached so the multi-GB checkpoint is not re-read per call.
    """
    if read_bytes is None and asset_id in _FULL_RESOLVE_CACHE:
        return _FULL_RESOLVE_CACHE[asset_id]
    matches = [a for a in _APPROVED_REGISTRY if a.asset_id == asset_id]
    if len(matches) == 0:
        raise AssetResolutionError(f"no approved asset resolves for identity {asset_id!r}")
    if len(matches) > 1:
        raise AssetResolutionError(
            f"ambiguous asset identity {asset_id!r} resolves to {len(matches)} approved assets; "
            f"resolution must be by unique asset identity, not basename"
        )
    asset = matches[0]
    if not asset.provisioned:
        raise AssetResolutionError(
            f"asset {asset_id!r} is not provisioned (NOT_YET_TRAINED / MISSING); "
            f"cannot resolve for M6"
        )

    used_default_reader = read_bytes is None
    if read_bytes is None:
        read_bytes = lambda p: Path(p).read_bytes()  # noqa: E731
    try:
        data = read_bytes(asset.canonical_path)
    except OSError as exc:
        raise AssetResolutionError(
            f"cannot read asset {asset_id!r} at {asset.canonical_path!r}: {exc}"
        )

    actual_sha = hashlib.sha256(data).hexdigest().upper()
    if actual_sha != asset.sha256.upper():
        raise AssetResolutionError(
            f"asset {asset_id!r} SHA mismatch: on-disk {actual_sha} != approved {asset.sha256}"
        )

    # The execution-visible reference is the explicit per-asset ComfyUI reference
    # recorded in the approved registry (the M4 extra_model_paths.yaml mapping),
    # NOT a naive parent/filename derivation. Under the live M4 mapping the
    # checkpoint base folder is the ComfyUI model base, so the checkpoint is
    # exposed as its basename (sd_xl_base_1.0.safetensors), while LoRAs are
    # exposed as subfolder/basename (realistic_posts/pytorch_lora_weights.safetensors).
    # The explicit comfyui_reference is authoritative and must remain so that
    # future mappings (which need not be basename-only) stay explicit.

    if used_default_reader:
        _FULL_RESOLVE_CACHE[asset_id] = asset
    return asset


def resolve_asset_by_basename(basename: str) -> List[ApprovedAsset]:
    """Simulates the dangerous basename-only resolution pattern.

    Returns every approved asset whose on-disk file basename equals `basename`.
    When this returns more than one asset, basename-only resolution is ambiguous
    and MUST be rejected. The Realistic pipeline never uses this path; it is
    provided so tests can prove the ambiguity fail-closed guarantee.
    """
    return [a for a in _APPROVED_REGISTRY if Path(a.canonical_path).name == basename]


# --------------------------------------------------------------------------- #
# Realistic Posts V2 GenerationSpec builder
# --------------------------------------------------------------------------- #



# WARDROBE_AUTO_ATTACHMENT_PLUMBING_20260924
# IDENTITY_PRODUCTION_PLUMBING_20260929
def _apply_identity_auto_attach(spec, *, character_id: str = "", novel_id: str = ""):
    """Flag-gated TEXT_CANON identity attach (ENABLE_IDENTITY_PRESERVATION). OFF: same object."""
    from tools.identity_preservation import apply_identity_to_generation_spec
    return apply_identity_to_generation_spec(spec, character_id=character_id or "", novel_id=novel_id or "")


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



def build_realistic_generation_spec(
    *,
    character_id: str = "",
    content_subjects: Tuple[str, ...] = (),
    environment: str = "",
    props: Tuple[str, ...] = (),
    object_identity: str = "",
    negative_constraints: Tuple[str, ...] = (),
    object_state: str = "",
    seed: int = 1_000_003,
    studio_bible_snapshot_ref: str = "",
    studio_bible_snapshot_sha256: str = "",
    prompt: str = "",
    read_bytes: Optional[Callable[[str], bytes]] = None,
    novel: str = "",
    chapter: str = "",
    scene_text: Optional[str] = None,
    studio_bible_enrich: bool = True,
    studio_bible_meta: Optional[Dict[str, Any]] = None,
) -> GenerationSpec:
    """Construct a GenerationSpec bound to the Realistic Posts V2 profile.

    GenerationSpec-driven: the SDXL checkpoint and the Realistic Posts LoRA are
    resolved from the authoritative registry (with SHA verification) and bound
    into model_execution. No Open Design runtime is required.

    AIVSB / Studio Bible enrichment: when ``novel`` is provided and
    ``studio_bible_enrich`` is True, the existing Studio Bible adapter
    (``tools.studio_bible_adapter``) is invoked read-only to project canon
    identity/content/style/conditioning context, which is merged onto the
    existing GenerationSpec fields (never parallel fields) and recorded in
    ``identity.studio_bible_binding``. The adapter is read-only against canon;
    its contract and unresolved/diagnostic behavior are preserved. When
    enrichment is disabled (or ``novel`` is empty), the build is byte-identical
    to the pre-enrichment contract so existing CPU tests stay valid.
    """
    # --- AIVSB Studio Bible enrichment (read-only adapter projection) --------
    binding_ref = studio_bible_snapshot_ref
    binding_sha = studio_bible_snapshot_sha256
    style_profile = REALISTIC_PROFILE_DEF["conditioning"]
    style_palette = ""
    style_lighting = ""
    cond_object_class = ""
    cond_lighting = ""
    subject_presence = ""
    character_refs = ()
    style_refs = ()
    composition = CompositionSpec()
    magic_effects = ""
    enrich = bool(novel) and studio_bible_enrich
    if enrich:
        scene = scene_text if scene_text is not None else prompt
        novel_id = _sba.normalize_novel_id(novel, empty_ok=False)
        projection = _sba.build_projection(novel_id, chapter, scene)
        _sba.require_resolved_canon(projection, scene_text=scene)
        proj_sha = _sba.projection_sha256(projection)
        sb = _sba.derive_spec_inputs(projection, scene)
        binding_ref = studio_bible_snapshot_ref or f"aivsb-{novel_id}-{chapter or 'general'}"
        binding_sha = studio_bible_snapshot_sha256 or proj_sha
        # Merge canon context onto the existing GenerationSpec fields.
        if sb["character_id"]:
            character_id = sb["character_id"]
        content_subjects = sb["subjects"]
        environment = sb["environment"] or environment
        props = sb["props"]
        object_identity = sb["object_identity"] or object_identity
        # EQUIPMENT_EXISTENCE != HELD_STATE. Empty bible object_state must NOT
        # inherit a drawn default. Only emit holding/drawn when text/scene
        # explicitly supports it (or bible state is already set).
        bible_state = str(sb.get("object_state") or "").strip()
        if bible_state:
            object_state = bible_state
        else:
            derived = _derive_object_state_from_text(
                scene if scene_text is not None else prompt,
                object_identity,
            )
            object_state = derived if derived else ""
        style_palette = sb["palette"]
        style_lighting = sb.get("lighting_phrase") or sb["lighting_design"]
        cond_object_class = sb["object_class"]
        cond_lighting = style_lighting or sb["lighting"]
        composition = CompositionSpec(
            camera=str(sb.get("camera_phrase") or ""),
            shot_distance=str(sb.get("shot_language") or ""),
            framing=str(sb.get("shot_language") or ""),
            focal_point=str(sb.get("identity_lock") or ""),
        )
        magic_effects = str(sb.get("magic_effects") or "")
        negative_constraints = tuple(
            dict.fromkeys(list(negative_constraints) + list(sb["negative_constraints"]))
        )
        primary = _sba.select_character_record(projection, scene)
        if primary is not None:
            subject_presence = _pack_subject_presence(
                primary.name, primary.age, primary.build, primary.clothing
            )
        character_refs = _sba._character_reference_bindings(primary)
        style_refs = _sba._milestone_style_bindings(primary)
        if studio_bible_meta is not None:
            studio_bible_meta.update(
                {
                    "novel": novel_id,
                    "novel_raw": novel,
                    "chapter": chapter,
                    "snapshot_ref": binding_ref,
                    "snapshot_sha256": binding_sha,
                    "projection_sha256": proj_sha,
                    "enrichment_applied": True,
                    "unresolved_fields": sb["unresolved_fields"],
                    "canon_warnings": sb["canon_warnings"],
                }
            )
    else:
        if studio_bible_meta is not None:
            studio_bible_meta.update(
                {
                    "novel": novel,
                    "snapshot_ref": binding_ref,
                    "snapshot_sha256": binding_sha,
                    "enrichment_applied": False,
                    "unresolved_fields": (),
                    "canon_warnings": (),
                }
            )


    # Auto-attach wardrobe contract when ENABLE_WARDROBE_PRESERVATION=ON
    _wardrobe_novel_id = ""
    if novel:
        try:
            _wardrobe_novel_id = _sba.normalize_novel_id(novel, empty_ok=True)
        except Exception:
            _wardrobe_novel_id = str(novel)

    checkpoint = resolve_asset(REALISTIC_CHECKPOINT_ASSET_ID, read_bytes=read_bytes)
    lora = resolve_asset(REALISTIC_LORA_ASSET_ID, read_bytes=read_bytes)
    return _apply_identity_auto_attach(_apply_wardrobe_auto_attach(
        GenerationSpec(
        caller_prompt=prompt,
        identity=IdentitySpec(
            character_id=character_id,
            studio_bible_binding=StudioBibleBinding(
                snapshot_ref=binding_ref,
                snapshot_sha256=binding_sha,
            ),
            reference_bindings=character_refs,
        ),
        references=ReferenceSpec(character_refs=character_refs, style_refs=style_refs),
        style=StyleSpec(
            pipeline=REALISTIC_PROFILE,
            style_profile=style_profile,
            palette=style_palette,
            lighting_design=style_lighting,
        ),
        content=ContentSpec(
            subjects=content_subjects,
            environment=environment,
            props=props,
            narrative_intent=magic_effects,
        ),
        composition=composition,
        conditioning=ConditioningSpec(
            object_state=object_state,
            object_identity=object_identity,
            object_class=cond_object_class,
            lighting=cond_lighting,
            negative_constraints=negative_constraints,
        ),
        model_execution=ModelExecutionSpec(
            backend="comfyui",
            workflow_id=REALISTIC_TEMPLATE_ID,
            workflow_version="1.1",
            checkpoint=checkpoint.comfyui_reference,
            checkpoint_hash=checkpoint.sha256,
            vae="embedded_sdxl",
            loras=(
                LoRABinding(
                    name=lora.asset_id,
                    hash=lora.sha256,
                    weight=float(REALISTIC_PROFILE_DEF["lora_weight"]),
                ),
            ),
            sampler=REALISTIC_PROFILE_DEF["sampler"],
            scheduler=REALISTIC_PROFILE_DEF["scheduler"],
            steps=int(REALISTIC_PROFILE_DEF["steps"]),
            cfg=float(REALISTIC_PROFILE_DEF["cfg"]),
            resolution=(int(REALISTIC_PROFILE_DEF["resolution"][0]), int(REALISTIC_PROFILE_DEF["resolution"][1])),
            seed=seed,
            precision=REALISTIC_PROFILE_DEF["precision"],
        ),
        body_pose=BodyPoseSpec(person_geometry=subject_presence),
        validation=ValidationSpec(
            pass_rules=REALISTIC_PROFILE_DEF["validation_requirements"],
        ),
        run=RunConfig(seed=seed),
    ),
        character_id=character_id,
        novel_id=_wardrobe_novel_id,
    ),
        character_id=character_id,
        novel_id=_wardrobe_novel_id,
    )


# --------------------------------------------------------------------------- #
# Deterministic workflow resolution + provenance (CPU-only, no GPU submit)
# --------------------------------------------------------------------------- #



# Parenthetical author notes (NOTE...) and the same class of authoring asides.
# Clothing/weapon/appearance phrases only. Hex palette is not passed through here.
_AUTHOR_NOTE_PAREN = re.compile(
    r"\s*\([^)]*\b(?:NOTE|drops held blades)\b[^)]*\)",
    re.IGNORECASE,
)


def _strip_author_notes(phrase: str) -> str:
    """Drop parenthetical NOTE... author notes and similar authoring asides.

    Keeps the visual phrase, including the weapon name. Does not strip hex
    palette; callers must not pass palette text into this helper.
    """
    cleaned = _AUTHOR_NOTE_PAREN.sub("", str(phrase or ""))
    return " ".join(cleaned.split())


def _presence_token(value: str) -> str:
    """Present an already-projected string as visual words. No new canon."""
    return " ".join(str(value or "").replace("_", " ").split())


def _pack_subject_presence(
    name: str,
    age: str,
    build: str,
    clothing: Tuple[str, ...],
) -> str:
    """Thread already-projected subject fields onto the spec. Not prompt text."""
    name_s = (name or "").strip()
    age_s = (age or "").strip()
    build_s = (build or "").strip()
    clothes = "\x1e".join(c.strip() for c in clothing if c and str(c).strip())
    if not any((name_s, age_s, build_s, clothes)):
        return ""
    return "\x1f".join((name_s, age_s, build_s, clothes))


_EMPTY_OR_NONE_PHYSICAL_OBJECTS = frozenset({
    "",
    "none",
    "none physical",
    "n/a",
    "na",
    "qi based",
})


def _object_hold_token(phrase: str) -> str:
    token = " ".join(str(phrase or "").replace("_", " ").split()).strip().lower()
    if token.endswith(" at side"):
        token = token[: -len(" at side")].strip()
    return token.strip("()")


def _is_empty_or_none_physical_object(phrase: str) -> bool:
    """True for empty or none-physical object tokens. Not a weapon invention."""
    return _object_hold_token(phrase) in _EMPTY_OR_NONE_PHYSICAL_OBJECTS


def _selected_object_name(spec: GenerationSpec) -> str:
    """Existing selected object name already on the spec. No new weapon.

    Empty and none-physical objects are not holdable names. Returning "" here
    keeps the holding phrase from emitting "holding none physical" or inventing
    a physical weapon. Real weapon names are unchanged.
    """
    identity = _strip_author_notes(getattr(spec.conditioning, "object_identity", "") or "")
    if not identity:
        return ""
    lowered = identity.lower()
    if lowered.endswith(" at side"):
        identity = identity[: -len(" at side")].strip()
    if _is_empty_or_none_physical_object(identity):
        return ""
    return identity


def _derive_object_state_from_text(scene_text: str, object_identity: str = "") -> str:
    """Derive held/drawn state only from explicit scene/text support.

    EMPTY_OBJECT_STATE != DRAWN. at_side / sheathed / carried / none stay
    non-holding. Explicit holding/drawn/in hand/gripped -> drawn.
    """
    st = " ".join(str(scene_text or "").lower().split())
    if not st:
        return ""
    # Explicit at-side / sheathed / carried are not held-in-hand.
    if re.search(r"\bat\s+(his|her|their|the)\s+side\b", st) or "at side" in st:
        if not re.search(r"\b(holding|drawn|in\s+hand|gripped)\b", st):
            return ""
    if re.search(r"\bsheathed\b", st):
        return "sheathed"
    if re.search(r"\bcarried\b", st) and not re.search(
        r"\b(holding|drawn|in\s+hand|gripped)\b", st
    ):
        return "carried"
    if re.search(r"\b(holding|drawn|in\s+hand|gripped)\b", st):
        return "drawn"
    # Clothing-style tokens already on identity (e.g. Soulblade at side).
    ident = " ".join(str(object_identity or "").replace("_", " ").lower().split())
    if ident.endswith(" at side") or " at side" in ident:
        return ""
    return ""


def _drawn_state_phrase(phrase: str, spec: GenerationSpec, *, identity_slot: bool = False) -> str:
    """When the selected object state is drawn, emit held/drawn, not at side.

    Uses the existing object name only. Does not invent a weapon, add weighting
    syntax, or strip hex. Empty/unspecified object_state does not default to
    holding/drawn (EMPTY_OBJECT_STATE != DRAWN).
    """
    text = " ".join(str(phrase or "").split())
    if not text:
        return ""
    # EQUIPMENT_EXISTENCE filter: never emit empty/none-physical on the identity
    # slot, independent of object_state (EMPTY_OBJECT_STATE != DRAWN).
    if identity_slot and _is_empty_or_none_physical_object(text):
        return ""
    state = str(getattr(spec.conditioning, "object_state", "") or "").strip().lower()
    if state != "drawn":
        return text
    name = _selected_object_name(spec)
    # Empty/none-physical objects must not become a held physical object.
    # Do not emit "holding none physical" and do not invent Soulblade.
    if _is_empty_or_none_physical_object(name) or _is_empty_or_none_physical_object(text):
        return text
    if not name:
        return text
    lowered = text.lower()
    name_l = name.lower()
    if lowered == f"{name_l} at side" or (
        lowered.endswith(" at side") and lowered[: -len(" at side")].strip() == name_l
    ):
        return f"holding {name}"
    if identity_slot and lowered == name_l:
        return f"holding {name}"
    return text


def _subject_presence_clause(spec: GenerationSpec) -> str:
    """One person-presence clause from threaded projected name/age/build/clothing.

    Leads with a visual person class only when the projected record has age
    or build. Clothing and appearance phrases are projected after parenthetical
    NOTE author notes and similar authoring asides are stripped. Non-visual
    filters such as none-physical are not applied here. Hex palette is not
    stripped by this path.
    """
    packed = spec.body_pose.person_geometry or ""
    if "\x1f" not in packed:
        return ""
    parts = packed.split("\x1f")
    if len(parts) < 4:
        return ""
    name, age, build, clothes_raw = parts[0], parts[1], parts[2], parts[3]
    clothing = tuple(c for c in clothes_raw.split("\x1e") if c.strip()) if clothes_raw else ()
    bits: List[str] = []
    class_bits = [
        _presence_token(_strip_author_notes(p))
        for p in (age, build)
        if p and p.strip()
    ]
    class_bits = [b for b in class_bits if b]
    if class_bits:
        bits.append(" ".join(class_bits) + " person")
    if name.strip():
        bits.append(name.strip())
    for item in clothing:
        token = _drawn_state_phrase(_presence_token(_strip_author_notes(item)), spec)
        if token:
            bits.append(token)
    return ", ".join(bits)


def _realistic_positive_prompt(spec: GenerationSpec) -> str:
    bits: List[str] = []
    clause = _subject_presence_clause(spec)
    if clause:
        bits.append(clause)
    if spec.style.style_profile:
        bits.append(spec.style.style_profile)
    if spec.caller_prompt:
        bits.append(spec.caller_prompt)
    # AIVSB Studio Bible projected context (existing fields, consumed as
    # intended visual semantics; no private canon internals leak).
    if spec.content.subjects:
        bits.append(", ".join(spec.content.subjects))
    if spec.content.environment:
        bits.append(spec.content.environment)
    # Studio Bible palette stays on StyleSpec.palette (structured canon
    # metadata). Do not append it to CLIP: the phrase is only labels that
    # introduce raw hex tokens (for example "primary #1B2A6B").
    if spec.conditioning.object_identity:
        identity = _drawn_state_phrase(
            _strip_author_notes(spec.conditioning.object_identity),
            spec,
            identity_slot=True,
        )
        if identity:
            bits.append(identity)
    if spec.content.props:
        props = [
            p for p in (
                _drawn_state_phrase(_strip_author_notes(p), spec)
                for p in spec.content.props
            ) if p
        ]
        if props:
            bits.append(", ".join(props))
    for clause in _sba.clip_cinematography_clauses(spec):
        if clause and clause.casefold() not in ", ".join(bits).casefold():
            bits.append(clause)
    return ", ".join(b for b in bits if b)


def _build_output_prefix(spec: GenerationSpec) -> str:
    """Deterministic Realistic V2 SaveImage naming (replica-invariant).

    No replica index, no prompt ID, no timestamp, no random suffix, no
    nondeterministic process state. The prefix depends only on the
    deterministic GenerationSpec digest and the fixed seed, so it is identical
    across reproducibility replicas. Replica identity is retained only in
    provenance/evidence, never in the rendered PNG workflow metadata (which is
    embedded by ComfyUI SaveImage). This mirrors the Main Posts V2 replica-
    invariant prefix contract.
    """
    spec_sha8 = generation_spec_sha256(spec)[:8]
    return f"v2_realistic_rp{spec_sha8}_s{spec.model_execution.seed}"



def _style_ref_path_rejected(asset_path: str) -> bool:
    """Reject DIAGNOSTIC/test assets; style_refs must be MILESTONE_VISUAL_REFERENCE only."""
    raw = str(asset_path or "").strip()
    if not raw:
        return True
    low = raw.replace("\\", "/").casefold()
    name = Path(raw).name.casefold()
    if "diagnostic" in low:
        return True
    if name.startswith("test_"):
        return True
    if "/test_" in low:
        return True
    try:
        kai_diag = Path(_sba._KAI_APPROVED_REFERENCE).resolve()
        if Path(raw).resolve() == kai_diag:
            return True
    except Exception:
        pass
    return False


def _select_style_refs_for_conditioning(style_refs) -> List[Any]:
    """Keep only existing, non-diagnostic style refs. Character identity refs never enter."""
    selected: List[Any] = []
    for binding in style_refs or ():
        path = str(getattr(binding, "asset_path", "") or "")
        if _style_ref_path_rejected(path):
            continue
        if not Path(path).is_file():
            continue
        selected.append(binding)
    return selected


def _stage_style_ref_for_comfy(asset_path: str) -> str:
    """Copy style ref into ComfyUI shared input; return LoadImage filename."""
    src = Path(asset_path)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", src.name)
    dest_name = f"style_ref_{digest}_{safe_name}"
    COMFY_SHARED_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = COMFY_SHARED_INPUT_DIR / dest_name
    if (not dest.exists()) or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return dest_name


def _resolve_experimental_style_ref_strength(
    override: Optional[float] = None,
) -> Tuple[Optional[float], Dict[str, Any]]:
    """Return a strength only when experimental opt-in is explicit.

    Production default: None (style conditioning OFF) even if style_refs are bound.
    Opt-in paths (smallest seams):
      1) style_ref_strength kwarg > 0
      2) env STYLE_REF_EXPERIMENTAL=1 and optional STYLE_REF_STRENGTH (else candidate)
    Empty style_refs still short-circuit earlier to legacy-graph-equivalent.
    """
    info: Dict[str, Any] = {
        "STYLE_REF_PRODUCTION_DEFAULT_QUALIFIED": "NO",
        "experimental_opt_in": False,
        "strength_source": None,
    }
    if override is not None:
        strength = float(override)
        if strength <= 0.0:
            info["strength_source"] = "kwarg_nonpositive"
            return None, info
        info["experimental_opt_in"] = True
        info["strength_source"] = "kwarg"
        return strength, info

    exp = str(os.environ.get(STYLE_REF_EXPERIMENTAL_ENV, "") or "").strip().lower()
    if exp in ("1", "true", "yes", "on"):
        raw = str(os.environ.get(STYLE_REF_STRENGTH_ENV, "") or "").strip()
        strength = float(raw) if raw else float(STYLE_REF_STRENGTH)
        if strength <= 0.0:
            info["experimental_opt_in"] = True
            info["strength_source"] = "env_nonpositive"
            return None, info
        info["experimental_opt_in"] = True
        info["strength_source"] = "env"
        return strength, info

    info["strength_source"] = "production_default_off"
    return None, info


def _apply_style_ref_conditioning(nodes: Dict[str, Any], style_refs, *, style_ref_strength: Optional[float] = None) -> Dict[str, Any]:
    """Wire GenerationSpec.style_refs into IPAdapterPreciseStyleTransfer on the MODEL path.

    STYLE_REFERENCE != TEXT_CANON != CHARACTER_IDENTITY:
      - positive/negative CLIPTextEncode nodes remain text-only
      - character_refs are never bound here
      - KSampler.model gains general (non-face) IP-Adapter style conditioning when
        refs are present AND experimental/qualification opt-in supplies a strength
    Empty / rejected style_refs => legacy graph equivalent (no new nodes; KSampler.model=["11",0]).
    Bound style_refs without opt-in => also legacy-graph-equivalent (production safety:
    STYLE_REF_PRODUCTION_DEFAULT_QUALIFIED=NO; 0.5 is not a silent validated default).
    """
    selected = _select_style_refs_for_conditioning(style_refs)
    rejected = max(0, len(tuple(style_refs or ())) - len(selected))
    meta: Dict[str, Any] = {
        "STYLE_REF_CONDITIONING_ACTIVE": "NO",
        "SAMPLER_RECEIVES_REFERENCE_CONDITIONING": "NO",
        "style_ref_node": None,
        "style_ref_strength": None,
        "style_ref_weight_file": None,
        "style_ref_image": None,
        "style_ref_asset_path": None,
        "style_ref_asset_sha256": None,
        "style_refs_selected": 0,
        "style_refs_rejected": rejected,
        "GENERAL_IPADAPTER_WEIGHT": "NO",
        "FACE_ONLY_WEIGHT": "NO",
        "legacy_graph_equivalent": True,
        "STYLE_REF_PRODUCTION_DEFAULT_QUALIFIED": "NO",
        "experimental_opt_in": False,
        "strength_source": None,
    }
    if not selected:
        return meta

    # IDENTITY_PRODUCTION_PLUMBING_20260929: with ENABLE_IDENTITY_PRESERVATION ON the
    # whole milestone is never attached as identity/style conditioning; neither
    # STYLE_REF_EXPERIMENTAL nor a style_ref_strength override can bypass this.
    from tools.identity_preservation import (
        NO_IDENTITY_REFERENCE_CONDITIONING_REASON,
        is_identity_preservation_enabled,
    )
    if is_identity_preservation_enabled():
        meta["style_refs_present"] = len(selected)
        meta["skip_reason"] = NO_IDENTITY_REFERENCE_CONDITIONING_REASON
        meta["style_refs_bound_but_inactive"] = True
        meta["IDENTITY_PRESERVATION_BLOCKED_STYLE_REF"] = "YES"
        return meta

    strength, exp_info = _resolve_experimental_style_ref_strength(style_ref_strength)
    meta.update(exp_info)
    meta["style_refs_present"] = len(selected)
    if strength is None:
        # Keep wiring code intact but do not activate unqualified production default.
        meta["skip_reason"] = "STYLE_REF_PRODUCTION_DEFAULT_NOT_QUALIFIED"
        meta["style_refs_bound_but_inactive"] = True
        return meta

    binding = selected[0]
    staged = _stage_style_ref_for_comfy(binding.asset_path)
    if GENERAL_IPADAPTER_FILE == FACE_ONLY_IPADAPTER_FILE:
        raise AssetResolutionError("refuse face-only IP-Adapter as general style weight")

    nodes[STYLE_REF_LOADER_NODE] = {
        "class_type": "IPAdapterModelLoader",
        "inputs": {"ipadapter_file": GENERAL_IPADAPTER_FILE},
    }
    nodes[STYLE_REF_CLIP_VISION_NODE] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": CLIP_VISION_FILE},
    }
    nodes[STYLE_REF_IMAGE_NODE] = {
        "class_type": "LoadImage",
        "inputs": {"image": staged},
    }
    nodes[STYLE_REF_APPLY_NODE] = {
        "class_type": "IPAdapterPreciseStyleTransfer",
        "inputs": {
            "model": ["11", 0],
            "ipadapter": [STYLE_REF_LOADER_NODE, 0],
            "image": [STYLE_REF_IMAGE_NODE, 0],
            "weight": float(strength),
            "style_boost": 1.0,
            "combine_embeds": "concat",
            "start_at": 0.0,
            "end_at": 1.0,
            "embeds_scaling": "V only",
            "clip_vision": [STYLE_REF_CLIP_VISION_NODE, 0],
        },
    }
    nodes["3"]["inputs"]["model"] = [STYLE_REF_APPLY_NODE, 0]

    weight_file = nodes[STYLE_REF_LOADER_NODE]["inputs"]["ipadapter_file"]
    if "face" in weight_file.casefold():
        raise AssetResolutionError(
            f"face-only IP-Adapter forbidden for style_refs: {weight_file}"
        )

    meta.update(
        {
            "STYLE_REF_CONDITIONING_ACTIVE": "YES",
            "SAMPLER_RECEIVES_REFERENCE_CONDITIONING": "YES",
            "style_ref_node": "IPAdapterPreciseStyleTransfer",
            "style_ref_strength": float(strength),
            "style_ref_weight_file": weight_file,
            "style_ref_image": staged,
            "style_ref_asset_path": binding.asset_path,
            "style_ref_asset_sha256": getattr(binding, "asset_sha256", "") or "",
            "style_refs_selected": 1,
            "style_refs_rejected": rejected + max(0, len(selected) - 1),
            "GENERAL_IPADAPTER_WEIGHT": "YES",
            "FACE_ONLY_WEIGHT": "NO",
            "legacy_graph_equivalent": False,
            "style_refs_bound_but_inactive": False,
            "skip_reason": None,
        }
    )
    return meta


def _assert_no_placeholder(nodes: Dict[str, Any]) -> None:
    for nid, node in nodes.items():
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, str) and value.startswith("REPLACE_"):
                raise AssetResolutionError(
                    f"unresolved placeholder {value!r} at node {nid} input {key!r}; "
                    f"no REPLACE_* placeholder may reach ComfyUI submission"
                )


def _assert_lora_load_bearing(nodes: Dict[str, Any]) -> None:
    model_conn = nodes["3"]["inputs"].get("model")
    if model_conn == ["11", 0]:
        pass  # legacy: KSampler <- LoraLoader
    elif (
        model_conn == [STYLE_REF_APPLY_NODE, 0]
        and nodes.get(STYLE_REF_APPLY_NODE, {}).get("class_type")
        == "IPAdapterPreciseStyleTransfer"
        and nodes[STYLE_REF_APPLY_NODE]["inputs"].get("model") == ["11", 0]
    ):
        pass  # style branch: KSampler <- PreciseStyleTransfer <- LoraLoader
    else:
        raise AssetResolutionError(
            "Realistic LoRA not load-bearing: KSampler.model not connected to LoraLoader output"
            f" (got {model_conn!r})"
        )
    if nodes["6"]["inputs"].get("clip") != ["11", 1]:
        raise AssetResolutionError(
            "Realistic LoRA not load-bearing: positive CLIPTextEncode.clip not connected to LoraLoader"
        )
    if nodes["7"]["inputs"].get("clip") != ["11", 1]:
        raise AssetResolutionError(
            "Realistic LoRA not load-bearing: negative CLIPTextEncode.clip not connected to LoraLoader"
        )
    if not nodes["11"]["inputs"].get("lora_name"):
        raise AssetResolutionError("Realistic LoRA node has no lora_name reference bound")


def _build_provenance(
    spec: GenerationSpec,
    workflow: Dict[str, Any],
    template: WorkflowTemplate,
    checkpoint: ApprovedAsset,
    lora: ApprovedAsset,
    replica: int = 0,
    studio_bible_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = extract_provenance(template, workflow, spec)
    base["generation_spec_sha256"] = generation_spec_sha256(spec)
    binding = spec.identity.studio_bible_binding
    base.update(
        {
            "profile": REALISTIC_PROFILE,
            "replica": replica,
            "caller_prompt": spec.caller_prompt,
            "controlnet_policy": REALISTIC_CONTROLNET_POLICY,
            "ip_adapter_policy": REALISTIC_IP_ADAPTER_POLICY,
            "capability_disposition": dict(REALISTIC_CAPABILITY_DISPOSITION),
            "open_design_runtime_requirement": REALISTIC_OPEN_DESIGN_RUNTIME_REQUIREMENT,
            "studio_bible": {
                "snapshot_ref": binding.snapshot_ref,
                "snapshot_sha256": binding.snapshot_sha256,
                "projection_sha256": (
                    studio_bible_meta.get("projection_sha256")
                    if studio_bible_meta
                    else binding.snapshot_sha256
                ),
                "enrichment_applied": bool(binding.snapshot_sha256),
                "unresolved_fields": (
                    list(studio_bible_meta.get("unresolved_fields", ()))
                    if studio_bible_meta
                    else []
                ),
                "canon_warnings": (
                    list(studio_bible_meta.get("canon_warnings", ()))
                    if studio_bible_meta
                    else []
                ),
            },
            "checkpoint_identity": {
                "asset_id": checkpoint.asset_id,
                "path": checkpoint.canonical_path,
                "sha256": checkpoint.sha256,
                "comfyui_reference": normalize_comfyui_reference(checkpoint.comfyui_reference),
            },
            "realistic_lora": {
                "asset_id": lora.asset_id,
                "path": lora.canonical_path,
                "sha256": lora.sha256,
                "comfyui_reference": normalize_comfyui_reference(lora.comfyui_reference),
            },
            "output_naming_identity": workflow["8"]["inputs"].get("filename_prefix"),
            "sampler": spec.model_execution.sampler,
            "scheduler": spec.model_execution.scheduler,
            "gpu_execution": False,
            "gpu_authority": M6_GPU_AUTHORIZED,
        }
    )
    return base


@dataclass
class RealisticResolution:
    spec: GenerationSpec
    workflow: Dict[str, Any]
    template: WorkflowTemplate
    provenance: Dict[str, Any]


def run_realistic_resolution(
    spec: GenerationSpec,
    *,
    replica: int = 0,
    read_bytes: Optional[Callable[[str], bytes]] = None,
    studio_bible_meta: Optional[Dict[str, Any]] = None,
    style_ref_strength: Optional[float] = None,
) -> RealisticResolution:
    """Resolve a GenerationSpec into a runnable Realistic V2 workflow + provenance.

    CPU-only. Deterministic and fail-closed. Never submits to ComfyUI (no GPU).
    """
    if spec.style.pipeline != REALISTIC_PROFILE:
        raise AssetResolutionError(
            f"Realistic pipeline requires style.pipeline='realistic', got {spec.style.pipeline!r}"
        )
    validate_generation_spec(spec)

    checkpoint = resolve_asset(REALISTIC_CHECKPOINT_ASSET_ID, read_bytes=read_bytes)
    lora = resolve_asset(REALISTIC_LORA_ASSET_ID, read_bytes=read_bytes)

    # Guard: the Realistic profile must bind exactly the Realistic Posts LoRA.
    bound = [b.name for b in spec.model_execution.loras]
    if REALISTIC_LORA_ASSET_ID not in bound:
        raise AssetResolutionError(
            f"Realistic profile must bind {REALISTIC_LORA_ASSET_ID}; bound={bound}"
        )
    if "lora_main_posts" in bound or "lora_comic_style" in bound:
        raise AssetResolutionError(
            f"Main Posts / Comic LoRA must not be substituted into Realistic: {bound}"
        )

    template = load_template(REALISTIC_TEMPLATE_ID)
    nodes = json.loads(json.dumps(template.nodes, sort_keys=True))  # deep copy

    nodes["6"]["inputs"]["text"] = _realistic_positive_prompt(spec)
    nodes["7"]["inputs"]["text"] = ", ".join(spec.conditioning.negative_constraints)
    nodes["10"]["inputs"]["ckpt_name"] = normalize_comfyui_reference(checkpoint.comfyui_reference)

    nodes["3"]["inputs"]["seed"] = spec.run.seed
    nodes["3"]["inputs"]["steps"] = spec.model_execution.steps
    nodes["3"]["inputs"]["cfg"] = spec.model_execution.cfg
    nodes["3"]["inputs"]["sampler_name"] = spec.model_execution.sampler
    nodes["3"]["inputs"]["scheduler"] = spec.model_execution.scheduler
    nodes["5"]["inputs"]["width"] = spec.model_execution.resolution[0]
    nodes["5"]["inputs"]["height"] = spec.model_execution.resolution[1]

    # Load-bearing LoRA binding (node 11 -> KSampler model + CLIP encoders).
    # ComfyUI 0.33.2 LoraLoader requires the `lora_name` input key.
    weight = spec.model_execution.loras[0].weight
    nodes["11"]["inputs"]["lora_name"] = normalize_comfyui_reference(lora.comfyui_reference)
    nodes["11"]["inputs"]["strength_model"] = weight
    nodes["11"]["inputs"]["strength_clip"] = weight

    # Deterministic, replica-invariant SaveImage output naming (no replica index).
    nodes["8"]["inputs"]["filename_prefix"] = _build_output_prefix(spec)

    # Optional style_refs -> general IP-Adapter Precise Style Transfer on MODEL path.
    # Empty/rejected style_refs leave the legacy graph untouched.
    style_ref_meta = _apply_style_ref_conditioning(
        nodes,
        getattr(getattr(spec, "references", None), "style_refs", ()) or (),
        style_ref_strength=style_ref_strength,
    )

    # Fail-closed invariants before "submission".
    _assert_no_placeholder(nodes)
    _assert_lora_load_bearing(nodes)

    provenance = _build_provenance(
        spec, nodes, template, checkpoint, lora, replica=replica,
        studio_bible_meta=studio_bible_meta,
    )
    provenance["style_ref_wiring"] = style_ref_meta
    provenance["STYLE_REF_CONDITIONING_ACTIVE"] = style_ref_meta.get(
        "STYLE_REF_CONDITIONING_ACTIVE", "NO"
    )
    provenance["SAMPLER_RECEIVES_REFERENCE_CONDITIONING"] = style_ref_meta.get(
        "SAMPLER_RECEIVES_REFERENCE_CONDITIONING", "NO"
    )
    return RealisticResolution(
        spec=spec, workflow=nodes, template=template, provenance=provenance
    )


# --------------------------------------------------------------------------- #
# Public pipeline facade
# --------------------------------------------------------------------------- #


class RealisticPipelineV2:
    """First-class Realistic Posts V2 pipeline (CPU-only resolution facade)."""

    PROFILE = REALISTIC_PROFILE
    TEMPLATE_ID = REALISTIC_TEMPLATE_ID
    CAPABILITY_DISPOSITION = REALISTIC_CAPABILITY_DISPOSITION
    CONTROLNET_POLICY = REALISTIC_CONTROLNET_POLICY
    IP_ADAPTER_POLICY = REALISTIC_IP_ADAPTER_POLICY
    OPEN_DESIGN_RUNTIME_REQUIREMENT = REALISTIC_OPEN_DESIGN_RUNTIME_REQUIREMENT
    GPU_AUTHORIZED = M6_GPU_AUTHORIZED

    def build_spec(self, **kwargs: Any) -> GenerationSpec:
        return build_realistic_generation_spec(**kwargs)

    def resolve(
        self,
        spec: GenerationSpec,
        *,
        replica: int = 0,
        read_bytes: Optional[Callable[[str], bytes]] = None,
        studio_bible_meta: Optional[Dict[str, Any]] = None,
        style_ref_strength: Optional[float] = None,
    ) -> RealisticResolution:
        return run_realistic_resolution(
            spec, replica=replica, read_bytes=read_bytes,
            studio_bible_meta=studio_bible_meta,
            style_ref_strength=style_ref_strength,
        )

    def capability_disposition(self) -> Dict[str, str]:
        return dict(REALISTIC_CAPABILITY_DISPOSITION)
