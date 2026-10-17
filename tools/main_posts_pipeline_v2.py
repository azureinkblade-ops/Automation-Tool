"""Image Pipeline V2 — Main Posts pipeline migration (CPU-only, first-class).

M-authority boundary (per Main Posts V2 bounded pipeline implementation
authority record 2026-08-20):
- No GPU execution. submit_workflow / ComfyUI inference is never invoked.
- No production routing. app.py / app_config.py / release_state.py untouched.
- Open Design remains optional (never imported; no runtime requirement).
- Realistic Posts (M6) and Comic (M5) profiles are NOT modified here.
- M1 GenerationSpec contract is NOT mutated (M1_CONTRACT_MUTATION_AUTHORIZED=NO).

Profile identity reconciliation (critical):
    The frozen M1 contract enumerates ALLOWED_PIPELINES = ("comic", "realistic")
    and its validate_generation_spec fails closed on any other pipeline value
    (tools/generation_spec.py:56, :280-283). This authority explicitly forbids
    mutating that whitelist. Therefore Main Posts carries its distinct
    first-class profile identity on GenerationSpec.style.pipeline = "main_posts"
    and validates through THIS module's dedicated, fail-closed contract
    (validate_main_posts_spec) rather than the frozen M1 pipeline validator.
    Main Posts is thereby a genuine first-class profile, not an alias of
    Realistic, while M1 stays byte-for-byte unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.comfyui_adapter import extract_provenance, load_template, WorkflowTemplate
from tools.generation_spec import (
    ALLOWED_STATES,
    CompositionSpec,
    ConditioningSpec,
    ContentSpec,
    GenerationSpec,
    IdentitySpec,
    LoRABinding,
    ModelExecutionSpec,
    RunConfig,
    StyleSpec,
    StudioBibleBinding,
    ValidationSpec,
    generation_spec_sha256,
)
from tools import studio_bible_adapter as _sba

# --- Main Posts authority constants ---------------------------------------
MAIN_POSTS_PROFILE = "main_posts"
MAIN_POSTS_TEMPLATE_ID = "main_posts_base"
MAIN_POSTS_LORA_ASSET_ID = "lora_main_posts"
MAIN_POSTS_CHECKPOINT_ASSET_ID = "sdxl_base_1.0"
MAIN_POSTS_TRIGGER_TOKEN = "azink_main"
MAIN_POSTS_OPEN_DESIGN_RUNTIME_REQUIREMENT = "OPTIONAL"
MAIN_POSTS_GPU_AUTHORIZED = False

# Capability disposition (section 9 / 18). Each optional capability classified
# exactly once; ControlNet / IP-Adapter are not required for the base profile.
MAIN_POSTS_CAPABILITY_DISPOSITION: Dict[str, str] = {
    "LORA": "REQUIRED",
    "CONTROLNET": "DISABLED_FOR_BASE_PROFILE",
    "IP_ADAPTER": "OPTIONAL_NOT_REQUIRED",
    "MASK_INPAINT": "DISABLED_FOR_MAIN_POSTS_V2",
}
MAIN_POSTS_CONTROLNET_POLICY = "DISABLED_FOR_BASE_PROFILE"
MAIN_POSTS_IP_ADAPTER_POLICY = "OPTIONAL_NOT_REQUIRED"

# Main Posts profile definition (section 9). Distinct from Realistic: different
# style conditioning, LoRA asset, and fixed default LoRA strength. Values that
# Main Posts governance leaves silent (LoRA strength, sampler, steps, cfg,
# resolution, negatives) are fixed here as documented base-profile defaults and
# recorded in the evidence record; they are not borrowed from Realistic.
MAIN_POSTS_PROFILE_DEF: Dict[str, Any] = {
    "checkpoint_asset_id": MAIN_POSTS_CHECKPOINT_ASSET_ID,
    "lora_asset_id": MAIN_POSTS_LORA_ASSET_ID,
    "lora_weight": 0.80,
    "conditioning": (
        "Azure Inkblade chapter promo art, strong web novel cover composition, "
        "high-impact social media framing"
    ),
    "sampler": "dpmpp_2m",
    "scheduler": "karras",
    "steps": 28,
    "cfg": 4.5,
    "resolution": (1024, 1024),
    "precision": "fp16",
    "validation_requirements": "phase3_v2_main_posts_default",
    "workflow_topology": "CheckpointLoader -> LoraLoader(load-bearing) -> KSampler -> VAEDecode -> SaveImage",
}

# Fixed default negative constraint set for the base Main Posts profile
# (section 13 fixture + section 9 negative constraints). Governance is silent
# on negatives for Main Posts; this fixed set is a documented base-profile
# default, not an invented per-request behavior.
MAIN_POSTS_DEFAULT_NEGATIVE: Tuple[str, ...] = (
    "low quality",
    "blurry",
    "watermark",
    "text overlay",
    "extra limbs",
    "deformed hands",
)

_ASSET_ROOT = Path(r"C:\Users\David\Documents\Automation tool")


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
        pipeline_role=("comic", "realistic", "main_posts"),
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
        asset_id="lora_realistic_posts",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "realistic_posts" / "pytorch_lora_weights.safetensors"),
        comfyui_reference="realistic_posts/pytorch_lora_weights.safetensors",
        sha256="FF795D7028D3473083901EBCE2CC7B284D12FF6C904E7834428A0213CD92C564",
        pipeline_role=("realistic",),
        provisioned=True,
    ),
)


def derive_comfyui_reference(canonical_path: str) -> str:
    """Deterministic ComfyUI-visible model reference (last two path components)."""
    p = Path(canonical_path)
    return f"{p.parent.name}/{p.name}"


def normalize_comfyui_reference(reference: str) -> str:
    """Normalize a ComfyUI model reference to the backend's path-separator form.

    Mirrors the M6 Defect 3 remediation: the live ComfyUI 0.33.2 backend builds
    its accepted model-name list with the host OS separator (``os.sep``), so on
    Windows a forward-slash LoRA reference is rejected with ``value_not_in_list``.
    Normalizing the execution-visible reference to ``os.sep`` reconciles the
    approved M4 semantic reference with the backend's canonical form without
    altering asset identity, canonical path, SHA, or the load-bearing topology.
    Empty references (unprovisioned assets) are returned unchanged.
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

    Fail-closed if zero/multiple assets match, the asset is unprovisioned, the
    on-disk SHA-256 does not match the approved manifest, or reads fail.

    `read_bytes` lets tests inject deterministic content; when None the real file
    is read and cached so the multi-GB checkpoint is not re-read per call.
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
            f"cannot resolve for Main Posts"
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

    if used_default_reader:
        _FULL_RESOLVE_CACHE[asset_id] = asset
    return asset


def resolve_asset_by_basename(basename: str) -> List[ApprovedAsset]:
    """Simulates the dangerous basename-only resolution pattern.

    Returns every approved asset whose on-disk file basename equals `basename`.
    When this returns more than one asset, basename-only resolution is ambiguous
    and MUST be rejected. The Main Posts pipeline never uses this path; it is
    provided so tests can prove the ambiguity fail-closed guarantee.
    """
    return [a for a in _APPROVED_REGISTRY if Path(a.canonical_path).name == basename]


# --------------------------------------------------------------------------- #
# Main Posts GenerationSpec contract (dedicated, M1-frozen-aware)
# --------------------------------------------------------------------------- #


class MainPostsSpecValidationError(Exception):
    """Fail-closed error for the Main Posts dedicated GenerationSpec contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MainPostsSpecValidationError(message)


def validate_main_posts_spec(spec: GenerationSpec) -> None:
    """Dedicated fail-closed contract for the Main Posts V2 profile.

    Mirrors the spirit of M1 validate_generation_spec (schema version,
    conditioning state, reference/asset SHA presence, sheathed-attachment
    semantics) but DELIBERATELY omits the M1 ALLOWED_PIPELINES whitelist check:
    under this authority main_posts cannot be added to that frozen whitelist, so
    the profile is validated here instead. Additionally enforces the Main Posts
    profile-specific invariants (style.pipeline == "main_posts", exactly the
    Main Posts LoRA bound, no Realistic/Comic LoRA substitution).
    """
    _require(
        _is_semantic_version(spec.spec_version),
        f"spec_version must be 'major.minor': got {spec.spec_version!r}",
    )
    _require(
        spec.style.pipeline == MAIN_POSTS_PROFILE,
        f"Main Posts profile requires style.pipeline='{MAIN_POSTS_PROFILE}', "
        f"got {spec.style.pipeline!r}",
    )
    _require(
        spec.conditioning.object_state in ALLOWED_STATES,
        f"conditioning.object_state must be in {ALLOWED_STATES}: "
        f"got {spec.conditioning.object_state!r}",
    )
    if spec.conditioning.object_state == "sheathed":
        _require(
            spec.attachment.attachment_type != "",
            "attachment.attachment_type required when object_state='sheathed'",
        )
        _require(
            len(spec.attachment.required_visible_evidence) > 0,
            "attachment.required_visible_evidence required when object_state='sheathed'",
        )
    _require(
        spec.model_execution.checkpoint_hash != "",
        "model_execution.checkpoint_hash required (must carry SHA)",
    )
    for lora in spec.model_execution.loras:
        _require(lora.hash != "", f"lora {lora.name!r} missing hash")

    bound = [b.name for b in spec.model_execution.loras]
    _require(
        MAIN_POSTS_LORA_ASSET_ID in bound,
        f"Main Posts profile must bind {MAIN_POSTS_LORA_ASSET_ID}; bound={bound}",
    )
    _require(
        "lora_realistic_posts" not in bound and "lora_comic_style" not in bound,
        f"Realistic / Comic LoRA must not be substituted into Main Posts: {bound}",
    )


def _is_semantic_version(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 2:
        return False
    return all(p.isdigit() for p in parts)


# --------------------------------------------------------------------------- #
# Deterministic Main Posts test fixture (section 13, CPU-only, no GPU)
# --------------------------------------------------------------------------- #

# Canonical, previously-undefined Main Posts qualification fixture. Fixed values
# for every required binding dimension so the future bounded GPU qualification
# reproduces deterministically. NO GPU generation occurs here.
MAIN_POSTS_FIXTURE_SEED = 1_000_003
MAIN_POSTS_FIXTURE_SUBJECTS = ("Azure Inkblade protagonist",)
MAIN_POSTS_FIXTURE_ENVIRONMENT = "stormlit cliff citadel at dawn, banner unfurling"
MAIN_POSTS_FIXTURE_PROPS = ("glowing sigil blade",)
MAIN_POSTS_FIXTURE_OBJECT_IDENTITY = "azure inkblade emblem"
MAIN_POSTS_FIXTURE_NEGATIVES = (
    "low quality",
    "blurry",
    "watermark",
    "text overlay",
    "extra limbs",
    "deformed hands",
)
MAIN_POSTS_FIXTURE_CHARACTER_ID = "azure_inkblade"



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



def build_main_posts_qualification_fixture(
    *,
    read_bytes: Optional[Callable[[str], bytes]] = None,
) -> GenerationSpec:
    """Build the single fixed Main Posts qualification fixture GenerationSpec.

    Deterministic and CPU-only. Binds one fixed seed, subject, environment,
    negative set, approved SDXL checkpoint, and approved Main Posts LoRA.
    """
    return build_main_posts_generation_spec(
        character_id=MAIN_POSTS_FIXTURE_CHARACTER_ID,
        content_subjects=MAIN_POSTS_FIXTURE_SUBJECTS,
        environment=MAIN_POSTS_FIXTURE_ENVIRONMENT,
        props=MAIN_POSTS_FIXTURE_PROPS,
        object_identity=MAIN_POSTS_FIXTURE_OBJECT_IDENTITY,
        negative_constraints=MAIN_POSTS_FIXTURE_NEGATIVES,
        object_state="drawn",
        seed=MAIN_POSTS_FIXTURE_SEED,
        read_bytes=read_bytes,
    )


# --------------------------------------------------------------------------- #
# Main Posts V2 GenerationSpec builder
# --------------------------------------------------------------------------- #


def build_main_posts_generation_spec(
    *,
    character_id: str = "",
    content_subjects: Tuple[str, ...] = (),
    environment: str = "",
    props: Tuple[str, ...] = (),
    object_identity: str = "",
    negative_constraints: Tuple[str, ...] = MAIN_POSTS_DEFAULT_NEGATIVE,
    object_state: str = "drawn",
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
    """Construct a GenerationSpec bound to the Main Posts V2 profile.

    GenerationSpec-driven: the SDXL checkpoint and the Main Posts LoRA are
    resolved from the authoritative registry (with SHA verification) and bound
    into model_execution. style.pipeline is set to the distinct first-class
    'main_posts' identity. No Open Design runtime is required.

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
    style_profile = MAIN_POSTS_PROFILE_DEF["conditioning"]
    style_palette = ""
    style_lighting = ""
    cond_object_class = ""
    cond_lighting = ""
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
        object_state = sb["object_state"] or object_state
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

    checkpoint = resolve_asset(MAIN_POSTS_CHECKPOINT_ASSET_ID, read_bytes=read_bytes)
    lora = resolve_asset(MAIN_POSTS_LORA_ASSET_ID, read_bytes=read_bytes)
    return _apply_identity_auto_attach(_apply_wardrobe_auto_attach(
        GenerationSpec(
        caller_prompt=prompt,
        identity=IdentitySpec(
            character_id=character_id,
            studio_bible_binding=StudioBibleBinding(
                snapshot_ref=binding_ref,
                snapshot_sha256=binding_sha,
            ),
        ),
        style=StyleSpec(
            pipeline=MAIN_POSTS_PROFILE,
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
            workflow_id=MAIN_POSTS_TEMPLATE_ID,
            workflow_version="1.1",
            checkpoint=checkpoint.comfyui_reference,
            checkpoint_hash=checkpoint.sha256,
            vae="embedded_sdxl",
            loras=(
                LoRABinding(
                    name=lora.asset_id,
                    hash=lora.sha256,
                    weight=float(MAIN_POSTS_PROFILE_DEF["lora_weight"]),
                ),
            ),
            sampler=MAIN_POSTS_PROFILE_DEF["sampler"],
            scheduler=MAIN_POSTS_PROFILE_DEF["scheduler"],
            steps=int(MAIN_POSTS_PROFILE_DEF["steps"]),
            cfg=float(MAIN_POSTS_PROFILE_DEF["cfg"]),
            resolution=(int(MAIN_POSTS_PROFILE_DEF["resolution"][0]), int(MAIN_POSTS_PROFILE_DEF["resolution"][1])),
            seed=seed,
            precision=MAIN_POSTS_PROFILE_DEF["precision"],
        ),
        validation=ValidationSpec(
            pass_rules=MAIN_POSTS_PROFILE_DEF["validation_requirements"],
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


def _main_posts_positive_prompt(spec: GenerationSpec) -> str:
    bits: List[str] = []
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
    if spec.style.palette:
        bits.append(spec.style.palette)
    if spec.conditioning.object_identity:
        bits.append(spec.conditioning.object_identity)
    if spec.content.props:
        bits.append(", ".join(spec.content.props))
    for clause in _sba.clip_cinematography_clauses(spec):
        if clause and clause.casefold() not in ", ".join(bits).casefold():
            bits.append(clause)
    return ", ".join(b for b in bits if b)


def _build_output_prefix(spec: GenerationSpec) -> str:
    """Deterministic Main Posts V2 SaveImage naming (replica-invariant).

    No replica index (section 15), no prompt ID, no timestamp, no random
    suffix, no nondeterministic process state. The prefix depends only on the
    deterministic GenerationSpec digest and the fixed seed, so it is identical
    across reproducibility replicas.
    """
    spec_sha8 = generation_spec_sha256(spec)[:8]
    return f"v2_main_posts_rp{spec_sha8}_s{spec.model_execution.seed}"


def _assert_no_placeholder(nodes: Dict[str, Any]) -> None:
    for nid, node in nodes.items():
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, str) and value.startswith("REPLACE_"):
                raise AssetResolutionError(
                    f"unresolved placeholder {value!r} at node {nid} input {key!r}; "
                    f"no REPLACE_* placeholder may reach ComfyUI submission"
                )


def _assert_lora_load_bearing(nodes: Dict[str, Any]) -> None:
    if nodes["3"]["inputs"].get("model") != ["11", 0]:
        raise AssetResolutionError(
            "Main Posts LoRA not load-bearing: KSampler.model not connected to LoraLoader output"
        )
    if nodes["6"]["inputs"].get("clip") != ["11", 1]:
        raise AssetResolutionError(
            "Main Posts LoRA not load-bearing: positive CLIPTextEncode.clip not connected to LoraLoader"
        )
    if nodes["7"]["inputs"].get("clip") != ["11", 1]:
        raise AssetResolutionError(
            "Main Posts LoRA not load-bearing: negative CLIPTextEncode.clip not connected to LoraLoader"
        )
    if not nodes["11"]["inputs"].get("lora_name"):
        raise AssetResolutionError("Main Posts LoRA node has no lora_name reference bound")


def _build_provenance(
    spec: GenerationSpec,
    workflow: Dict[str, Any],
    template: WorkflowTemplate,
    checkpoint: ApprovedAsset,
    lora: ApprovedAsset,
    studio_bible_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = extract_provenance(template, workflow, spec)
    base["generation_spec_sha256"] = generation_spec_sha256(spec)
    base["resolved_workflow_sha256"] = hashlib.sha256(
        json.dumps(workflow, sort_keys=True).encode("utf-8")
    ).hexdigest()
    binding = spec.identity.studio_bible_binding
    base.update(
        {
            "profile": MAIN_POSTS_PROFILE,
            "caller_prompt": spec.caller_prompt,
            "controlnet_policy": MAIN_POSTS_CONTROLNET_POLICY,
            "ip_adapter_policy": MAIN_POSTS_IP_ADAPTER_POLICY,
            "capability_disposition": dict(MAIN_POSTS_CAPABILITY_DISPOSITION),
            "open_design_runtime_requirement": MAIN_POSTS_OPEN_DESIGN_RUNTIME_REQUIREMENT,
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
            "lora_strengths": {
                b.name: b.weight for b in spec.model_execution.loras
            },
            "checkpoint_identity": {
                "asset_id": checkpoint.asset_id,
                "path": checkpoint.canonical_path,
                "sha256": checkpoint.sha256,
                "comfyui_reference": normalize_comfyui_reference(checkpoint.comfyui_reference),
            },
            "main_posts_lora": {
                "asset_id": lora.asset_id,
                "path": lora.canonical_path,
                "sha256": lora.sha256,
                "comfyui_reference": normalize_comfyui_reference(lora.comfyui_reference),
                "trigger_token": MAIN_POSTS_TRIGGER_TOKEN,
            },
            "output_naming_identity": workflow["8"]["inputs"].get("filename_prefix"),
            "sampler": spec.model_execution.sampler,
            "scheduler": spec.model_execution.scheduler,
            "steps": spec.model_execution.steps,
            "cfg": spec.model_execution.cfg,
            "dimensions": list(spec.model_execution.resolution),
            "gpu_execution": False,
            "gpu_authority": MAIN_POSTS_GPU_AUTHORIZED,
        }
    )
    return base


@dataclass
class MainPostsResolution:
    spec: GenerationSpec
    workflow: Dict[str, Any]
    template: WorkflowTemplate
    provenance: Dict[str, Any]


def run_main_posts_resolution(
    spec: GenerationSpec,
    *,
    replica: int = 0,
    read_bytes: Optional[Callable[[str], bytes]] = None,
    studio_bible_meta: Optional[Dict[str, Any]] = None,
) -> MainPostsResolution:
    """Resolve a GenerationSpec into a runnable Main Posts V2 workflow + provenance.

    CPU-only. Deterministic and fail-closed. Never submits to ComfyUI (no GPU).

    NOTE: validation uses the dedicated validate_main_posts_spec contract, NOT
    M1's validate_generation_spec, because M1's frozen ALLOWED_PIPELINES
    whitelist cannot enumerate 'main_posts' under this authority.
    """
    if spec.style.pipeline != MAIN_POSTS_PROFILE:
        raise AssetResolutionError(
            f"Main Posts pipeline requires style.pipeline='{MAIN_POSTS_PROFILE}', "
            f"got {spec.style.pipeline!r}"
        )
    validate_main_posts_spec(spec)

    checkpoint = resolve_asset(MAIN_POSTS_CHECKPOINT_ASSET_ID, read_bytes=read_bytes)
    lora = resolve_asset(MAIN_POSTS_LORA_ASSET_ID, read_bytes=read_bytes)

    bound = [b.name for b in spec.model_execution.loras]
    if MAIN_POSTS_LORA_ASSET_ID not in bound:
        raise AssetResolutionError(
            f"Main Posts profile must bind {MAIN_POSTS_LORA_ASSET_ID}; bound={bound}"
        )
    if "lora_realistic_posts" in bound or "lora_comic_style" in bound:
        raise AssetResolutionError(
            f"Realistic / Comic LoRA must not be substituted into Main Posts: {bound}"
        )

    template = load_template(MAIN_POSTS_TEMPLATE_ID)
    nodes = json.loads(json.dumps(template.nodes, sort_keys=True))  # deep copy

    nodes["6"]["inputs"]["text"] = _main_posts_positive_prompt(spec)
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
    weight = spec.model_execution.loras[0].weight
    nodes["11"]["inputs"]["lora_name"] = normalize_comfyui_reference(lora.comfyui_reference)
    nodes["11"]["inputs"]["strength_model"] = weight
    nodes["11"]["inputs"]["strength_clip"] = weight

    # Deterministic, replica-invariant SaveImage output naming (no replica index).
    nodes["8"]["inputs"]["filename_prefix"] = _build_output_prefix(spec)

    # Fail-closed invariants before "submission".
    _assert_no_placeholder(nodes)
    _assert_lora_load_bearing(nodes)

    provenance = _build_provenance(
        spec, nodes, template, checkpoint, lora,
        studio_bible_meta=studio_bible_meta,
    )
    return MainPostsResolution(
        spec=spec, workflow=nodes, template=template, provenance=provenance
    )


# --------------------------------------------------------------------------- #
# Evidence overwrite-protection contract (section 16, designed now; no GPU here)
# --------------------------------------------------------------------------- #


class EvidenceOverwriteError(Exception):
    """Fail-closed error when a Main Posts evidence write would destroy preserved output."""


# Replica 1 is the canonical preserved baseline from the future GPU
# qualification; it must never be silently overwritten by a re-run or a later
# replica.
PRESERVED_BASELINE_REPLICA = 1


def assert_evidence_overwrite_safe(
    replica: int,
    *,
    preserved_replicas: Tuple[int, ...] = (PRESERVED_BASELINE_REPLICA,),
    explicit_archival_selector: Optional[str] = None,
) -> None:
    """Fail-closed guard for Main Posts qualification evidence writers.

    Contract:
      - An explicit replica selector is always required (no implicit overwrite).
      - A preserved baseline replica (default: Replica 1) may NOT be overwritten
        unless an explicit archival selector (e.g. "archive-<id>") is supplied,
        which routes the write to a distinct archival evidence location.
      - Non-preserved replicas are always permitted (distinct identity).

    This is a design-time contract only; no GPU generation or file I/O occurs.
    """
    if replica in preserved_replicas and explicit_archival_selector is None:
        raise EvidenceOverwriteError(
            f"replica {replica} is a preserved baseline; overwrite forbidden "
            f"without an explicit archival selector"
        )


# --------------------------------------------------------------------------- #
# Public pipeline facade
# --------------------------------------------------------------------------- #


class MainPostsPipelineV2:
    """First-class Main Posts V2 pipeline (CPU-only resolution facade)."""

    PROFILE = MAIN_POSTS_PROFILE
    TEMPLATE_ID = MAIN_POSTS_TEMPLATE_ID
    CAPABILITY_DISPOSITION = MAIN_POSTS_CAPABILITY_DISPOSITION
    CONTROLNET_POLICY = MAIN_POSTS_CONTROLNET_POLICY
    IP_ADAPTER_POLICY = MAIN_POSTS_IP_ADAPTER_POLICY
    OPEN_DESIGN_RUNTIME_REQUIREMENT = MAIN_POSTS_OPEN_DESIGN_RUNTIME_REQUIREMENT
    GPU_AUTHORIZED = MAIN_POSTS_GPU_AUTHORIZED
    LORA_ASSET_ID = MAIN_POSTS_LORA_ASSET_ID
    CHECKPOINT_ASSET_ID = MAIN_POSTS_CHECKPOINT_ASSET_ID

    def build_spec(self, **kwargs: Any) -> GenerationSpec:
        return build_main_posts_generation_spec(**kwargs)

    def resolve(
        self,
        spec: GenerationSpec,
        *,
        replica: int = 0,
        read_bytes: Optional[Callable[[str], bytes]] = None,
        studio_bible_meta: Optional[Dict[str, Any]] = None,
    ) -> MainPostsResolution:
        return run_main_posts_resolution(
            spec, replica=replica, read_bytes=read_bytes,
            studio_bible_meta=studio_bible_meta,
        )

    def capability_disposition(self) -> Dict[str, str]:
        return dict(MAIN_POSTS_CAPABILITY_DISPOSITION)
