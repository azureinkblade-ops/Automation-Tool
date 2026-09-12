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
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.comfyui_adapter import (
    extract_provenance,
    load_template,
    WorkflowTemplate,
    apply_structural_runtime_control,
    is_explicit_openpose_structural_permitted,
)
from tools.spatial_guide import StructuralGuideBundle, bind_structural_guides_to_workflow
from tools.generation_spec import (
    ConditioningSpec,
    ContentSpec,
    GenerationSpec,
    GenerationSpecValidationError,
    IdentitySpec,
    LoRABinding,
    ModelExecutionSpec,
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

# --------------------------------------------------------------------------- #
# Bounded composition-constraint factor (canonical realistic conditioning owner)
# --------------------------------------------------------------------------- #
#
# COMPOSITION_CONSTRAINT is a SINGLE, narrow, optional composition/framing
# conditioning factor expressed through the production realistic conditioning
# layer (this module). It addresses the diagnosed seed-dependent
# PROMPT_COMPOSITION_UNDERCONSTRAINT: the intended Kael + Soulblade +
# gripping-hand interaction escapes into a portrait / composition mode.
#
# Contract:
#   - default OFF (composition_constraint=False) => byte-identical CONTROL.
#   - TREATMENT adds ONLY composition/framing CLIP text (positive + bounded
#     negative). It does NOT touch hand geometry, OpenPose asset, checkpoint,
#     LoRA, seed, sampler, scheduler, steps, CFG, resolution, regional masks,
#     Studio Bible canon, or the GenerationSpec schema/hashing.
#   - It is NOT a second anatomy-repair factor: no fused/missing/extra-finger
#     language (that belongs to the sanctioned OpenPose hand factor). The
#     negative side is confined to composition escape only.
#   - It is NOT the prior causal-null HAND_HILT_ISOLATION regional mask factor.

REALISTIC_COMPOSITION_CONSTRAINT_POSITIVE = (
    "medium shot, upper-body interaction framing, Kael's gripping hand visible, "
    "Soulblade hilt visible, hand and hilt both inside the frame, visible "
    "hand-to-hilt contact, interaction centered in the composition"
)

REALISTIC_COMPOSITION_CONSTRAINT_NEGATIVE = (
    "tight portrait crop, face-only framing, hands outside frame, "
    "weapon outside frame"
)

# Capability disposition (M6 section 7 / 9 / 10). Each optional capability is
# classified exactly once.
REALISTIC_CAPABILITY_DISPOSITION: Dict[str, str] = {
    "LORA": "REQUIRED",
    "CONTROLNET": "DISABLED_FOR_BASE_PROFILE",
    "IP_ADAPTER": "DISABLED_FOR_BASE_PROFILE",
    "MASK_INPAINT": "DISABLED_FOR_REALISTIC_V2",
}
REALISTIC_CONTROLNET_POLICY = "DISABLED_FOR_BASE_PROFILE"
REALISTIC_IP_ADAPTER_POLICY = "OPTIONAL_NOT_PROVISIONED"

# Additive explicit-structural-OpenPose exception. This does NOT change
# REALISTIC_CONTROLNET_POLICY (which remains "DISABLED_FOR_BASE_PROFILE"); it is a
# SEPARATE bounded capability permitting ONLY the already-qualified EN explicit
# hand-interaction OpenPose path, discriminated provider-neutrally from the pose
# artifact provenance by tools.comfyui_adapter.is_explicit_openpose_structural_permitted.
REALISTIC_CAPABILITY_DISPOSITION["OPENPOSE_EXPLICIT_HAND_INTERACTION"] = (
    "EXPLICIT_STRUCTURAL_OPENPOSE_EXCEPTION"
)

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

# --------------------------------------------------------------------------- #
# Approved-asset registry — single canonical owner
# --------------------------------------------------------------------------- #
#
# Realistic V2 consumes the ONE canonical V2 approved-asset registry defined in
# tools/image_pipeline_v2_assets.py. The duplicated registry that previously
# lived here has been removed; the symbols below are re-exported for
# backward-compatible imports and MUST NOT own independent registry data.

from tools.image_pipeline_v2_assets import (
    ApprovedAsset,
    _APPROVED_REGISTRY,
    AssetResolutionError,
    derive_comfyui_reference,
    normalize_comfyui_reference,
    resolve_asset,
    resolve_asset_by_basename,
)


# derive_comfyui_reference / normalize_comfyui_reference / resolve_asset /
# resolve_asset_by_basename / AssetResolutionError are re-exported from
# tools/image_pipeline_v2_assets (single canonical owner).


# --------------------------------------------------------------------------- #
# Realistic Posts V2 GenerationSpec builder
# --------------------------------------------------------------------------- #


def build_realistic_generation_spec(
    *,
    character_id: str = "",
    content_subjects: Tuple[str, ...] = (),
    environment: str = "",
    props: Tuple[str, ...] = (),
    object_identity: str = "",
    negative_constraints: Tuple[str, ...] = (),
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
    char_visual = ""
    enrich = bool(novel) and studio_bible_enrich
    if enrich:
        scene = scene_text if scene_text is not None else prompt
        projection = _sba.build_projection(novel, chapter, scene)
        proj_sha = _sba.projection_sha256(projection)
        sb = _sba.derive_spec_inputs(projection, scene)
        binding_ref = studio_bible_snapshot_ref or f"aivsb-{novel}-{chapter or 'general'}"
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
        style_lighting = sb["lighting_design"]
        cond_object_class = sb["object_class"]
        cond_lighting = sb["lighting"]
        # Surface concrete character visual identity (canon-supplied, never
        # synthesized) so the primary subject is grounded, not merely named.
        # Uses the existing content.narrative_intent field (no schema change).
        char_visual = _character_visual_phrase(
            projection, scene,
            object_identity=object_identity,
            object_state=object_state,
        )
        negative_constraints = tuple(
            dict.fromkeys(list(negative_constraints) + list(sb["negative_constraints"]))
        )
        if studio_bible_meta is not None:
            studio_bible_meta.update(
                {
                    "novel": novel,
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

    checkpoint = resolve_asset(REALISTIC_CHECKPOINT_ASSET_ID, read_bytes=read_bytes)
    lora = resolve_asset(REALISTIC_LORA_ASSET_ID, read_bytes=read_bytes)
    return GenerationSpec(
        caller_prompt=prompt,
        identity=IdentitySpec(
            character_id=character_id,
            studio_bible_binding=StudioBibleBinding(
                snapshot_ref=binding_ref,
                snapshot_sha256=binding_sha,
            ),
        ),
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
            narrative_intent=char_visual,
        ),
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
        validation=ValidationSpec(
            pass_rules=REALISTIC_PROFILE_DEF["validation_requirements"],
        ),
        run=RunConfig(seed=seed),
    )


# --------------------------------------------------------------------------- #
# Deterministic workflow resolution + provenance (CPU-only, no GPU submit)
# --------------------------------------------------------------------------- #


def _character_visual_phrase(
    projection: Any,
    scene_text: str = "",
    *,
    object_identity: str = "",
    object_state: str = "",
) -> str:
    """Build a canon-grounded character visual description for the SCENE-SELECTED
    subject.

    Delegates subject selection AND the conditioning-facing clothing projection
    to the authoritative adapter contract so (a) a multi-character projection
    never resolves Kael's visual identity for a Kai request, and (b) legacy
    "(NOTE: ...)" authoring annotations plus a resting/carry layout descriptor
    that contradicts an active grip/wield scene never reach positive CLIP text.
    Consumes ONLY canon-supplied appearance fields (gender, age, build, hair,
    eyes, clothing). Returns "" when no canon character resolves (so OFF builds
    stay byte-identical).
    """
    record = _sba.select_character_record(projection, scene_text)
    if record is None:
        return ""
    return _sba.character_visual_phrase(
        record, object_identity=object_identity, object_state=object_state
    )


def _realistic_positive_prompt(spec: GenerationSpec) -> str:
    """Deterministic positive CLIP text with subject/object conditioning priority.

    Priority order (per bounded Studio Bible conditioning-priority diagnostic):
      1. explicit primary subject (name + canon visual identity)
      2. required object/weapon explicitly attached to the subject
      3. environment / location
      4. lighting (previously computed but dropped from CLIP; restored)
      5. palette / style
      6. generic promotional / profile descriptors LAST so they cannot crowd
         out the required subject/object semantics.
    """
    bits: List[str] = []
    subject_str = ", ".join(spec.content.subjects) if spec.content.subjects else ""
    # 1. Explicit primary subject, with concrete visual identity when canon
    #    supplies it (carried in content.narrative_intent).
    if subject_str:
        if spec.content.narrative_intent:
            bits.append(f"{subject_str}, {spec.content.narrative_intent}")
        else:
            bits.append(subject_str)
    # 2. Required object/weapon attached to the subject (no longer a bare,
    #    duplicated trailing fragment). Attach a truthful ordinary-language class
    #    grounding (e.g. "blade") derived from the canon name so an otherwise
    #    opaque canon object identity carries interpretable grounding for the
    #    model. The class is never fabricated visual detail; it is omitted when
    #    it is already an explicit token of the identity (e.g. "Soulblade").
    obj = spec.conditioning.object_identity
    obj_class = spec.conditioning.object_class
    if obj:
        # Physical object (EN): the canon name is a wielded weapon/object.
        if subject_str:
            if obj_class and obj_class != "object" \
                    and obj_class not in set(re.split(r"[\s_]+", obj.lower())):
                bits.append(f"{subject_str} wielding the {obj}, a {obj_class}")
            else:
                bits.append(f"{subject_str} wielding the {obj}")
        else:
            bits.append(obj)
    else:
        # No physical object (HA): non-physical qi manifestations are visible
        # EFFECTS, never "wielded". Render them as visible effects tied to the
        # subject, not as an absence to be gripped.
        effects = [p for p in spec.content.props if p]
        if effects:
            bits.append(_sba.render_nonphysical_effects_fragment(subject_str, tuple(effects)))
    # 3. Environment / location.
    if spec.content.environment:
        bits.append(spec.content.environment)
    # 4. Lighting (was computed in style.lighting_design but omitted before).
    if spec.style.lighting_design:
        bits.append(spec.style.lighting_design)
    # 5. Palette / style.
    if spec.style.palette:
        bits.append(spec.style.palette)
    # 6. Generic promotional / profile descriptors LAST.
    if spec.caller_prompt:
        bits.append(spec.caller_prompt)
    if spec.style.style_profile:
        bits.append(spec.style.style_profile)
    # Remaining props that were neither the wielded object nor already-rendered
    # visible effects (de-duplicates the previously doubled Soulblade token).
    rendered = set()
    if obj:
        rendered.add(obj)
    else:
        rendered.update(p for p in spec.content.props if p)
    if spec.content.props:
        extra = [p for p in spec.content.props if p and p not in rendered]
        if extra:
            bits.append(", ".join(extra))
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
            "Realistic LoRA not load-bearing: KSampler.model not connected to LoraLoader output"
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
    composition_constraint: bool = False,
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
            "steps": spec.model_execution.steps,
            "cfg": spec.model_execution.cfg,
            "dimensions": list(spec.model_execution.resolution),
            "lora_strengths": {
                b.name: b.weight for b in spec.model_execution.loras
            },
            "gpu_execution": False,
            "gpu_authority": M6_GPU_AUTHORIZED,
            "composition_constraint_applied": bool(composition_constraint),
            "composition_constraint_positive": (
                REALISTIC_COMPOSITION_CONSTRAINT_POSITIVE if composition_constraint else ""
            ),
            "composition_constraint_negative": (
                REALISTIC_COMPOSITION_CONSTRAINT_NEGATIVE if composition_constraint else ""
            ),
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
    structural_guide_bundle: Optional["StructuralGuideBundle"] = None,
    composition_constraint: bool = False,
) -> RealisticResolution:
    """Resolve a GenerationSpec into a runnable Realistic V2 workflow + provenance.

    CPU-only. Deterministic and fail-closed. Never submits to ComfyUI (no GPU).

    ``structural_guide_bundle`` is the canonical, provider-neutral structural-
    control hook. When None (the default, including Studio Bible enrichment OFF),
    the workflow is byte-identical to the pre-guide contract: no metadata block,
    no added guide nodes.

    ``composition_constraint`` is the bounded COMPOSITION_CONSTRAINT factor, owned
    by this realistic conditioning layer. When False (default) the resolved
    positive/negative CLIP text is byte-identical to the current production
    contract. When True it appends ONLY the composition/framing CLIP text
    (positive + bounded negative) and records the factor in provenance. It never
    alters hand geometry, the OpenPose asset, regional masks, checkpoint, LoRA,
    seed, sampler settings, or the GenerationSpec.
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

    pos_text = _realistic_positive_prompt(spec)
    neg_text = ", ".join(spec.conditioning.negative_constraints)
    # Bounded COMPOSITION_CONSTRAINT factor (default OFF = byte-identical CONTROL).
    # TREATMENT appends ONLY composition/framing CLIP text; no geometry, asset,
    # regional-mask, model, or GenerationSpec change.
    if composition_constraint:
        pos_text = f"{pos_text}, {REALISTIC_COMPOSITION_CONSTRAINT_POSITIVE}"
        neg_text = f"{neg_text}, {REALISTIC_COMPOSITION_CONSTRAINT_NEGATIVE}".strip(", ")
    nodes["6"]["inputs"]["text"] = pos_text
    nodes["7"]["inputs"]["text"] = neg_text
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

    # Canonical structural-control wiring (provider-neutral real node binding).
    # No-op when no bundle. The mask/regional + OpenPose ControlNet runtime binding
    # is owned by comfyui_adapter.apply_structural_runtime_control, which attaches
    # the provider-neutral metadata block and the real CORE control nodes.
    if structural_guide_bundle is not None:
        import tempfile

        from tools import spatial_guide as _sg

        # Bounded capability gate: permit OpenPose ONLY for the already-qualified
        # explicit EN hand-interaction path. The global REALISTIC_CONTROLNET_POLICY
        # remains "DISABLED_FOR_BASE_PROFILE"; this is a separate bounded exception.
        allow_openpose = is_explicit_openpose_structural_permitted(
            structural_guide_bundle,
            structural_guide_bundle.request,
        )
        nodes = apply_structural_runtime_control(
            nodes,
            structural_guide_bundle.request,
            structural_guide_bundle,
            output_dir=tempfile.mkdtemp(prefix="v2_rp_struct_"),
            allow_openpose=allow_openpose,
        )

    # Fail-closed invariants before "submission".
    _assert_no_placeholder(nodes)
    _assert_lora_load_bearing(nodes)

    provenance = _build_provenance(
        spec, nodes, template, checkpoint, lora, replica=replica,
        studio_bible_meta=studio_bible_meta,
        composition_constraint=composition_constraint,
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
        structural_guide_bundle: Optional["StructuralGuideBundle"] = None,
        composition_constraint: bool = False,
    ) -> RealisticResolution:
        return run_realistic_resolution(
            spec, replica=replica, read_bytes=read_bytes,
            studio_bible_meta=studio_bible_meta,
            structural_guide_bundle=structural_guide_bundle,
            composition_constraint=composition_constraint,
        )

    def capability_disposition(self) -> Dict[str, str]:
        return dict(REALISTIC_CAPABILITY_DISPOSITION)
