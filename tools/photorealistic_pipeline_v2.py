"""Photorealistic V2 asset binding. CPU selection only. No ComfyUI submit.

Binds RealVisXL V5.0 fp16 to the photorealistic profile after the file exists
and the SHA-256 matches. Does not load azink_real. Does not queue a KSampler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from tools.generation_spec import (
    BodyPoseSpec,
    CompositionSpec,
    ConditioningSpec,
    ContentSpec,
    GenerationSpec,
    IdentitySpec,
    ModelExecutionSpec,
    RunConfig,
    StyleSpec,
    StudioBibleBinding,
    ValidationSpec,
)
from tools.image_pipeline_v2_profiles import (
    PHOTOREALISTIC_CHECKPOINT_FILENAME,
    PHOTOREALISTIC_PROFILE,
    photorealistic_asset_status,
    project_shared_studio_bible_canon,
)
from tools import studio_bible_adapter as _sba

PHOTOREALISTIC_TEMPLATE_ID = "photorealistic_base"
PHOTOREALISTIC_STYLE_SLICE = "photographic live-action style slice"
PHOTOREALISTIC_GPU_QUALIFICATION_AUTHORIZED = False


class PhotorealisticGpuQualificationRequired(RuntimeError):
    """Asset is selected. Generation stays blocked until GPU qualification."""

    def __init__(self, asset: str):
        super().__init__(
            "photorealistic profile selected "
            f"{asset}; GPU qualification not authorized. Refusing generation. "
            "Will not fall through to cinematic-promo, realistic-posts, "
            "main-posts, local SD, cloud, or stock."
        )
        self.asset = asset
        self.gpu_qualification_authorized = False


@dataclass
class PhotorealisticResolution:
    spec: GenerationSpec
    workflow: Dict[str, Any]
    template: Any
    provenance: Dict[str, Any]


def _object_state(value: str) -> str:
    token = str(value or "").strip().lower()
    if token in {"drawn", "sheathed", "prop"}:
        return token
    return "drawn"



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



def build_photorealistic_generation_spec(
    *,
    prompt: str = "",
    novel: str = "",
    chapter: str = "",
    scene_text: Optional[str] = None,
    seed: int = 1_000_103,
    studio_bible_enrich: bool = True,
) -> GenerationSpec:
    status = photorealistic_asset_status()
    if not status["ready"]:
        from tools.image_pipeline_v2_profiles import PhotorealisticProfileUnavailableError

        raise PhotorealisticProfileUnavailableError(status["message"])

    scene = scene_text if scene_text is not None else prompt
    canon: Dict[str, Any] = {
        "character_id": "",
        "subjects": (),
        "location": "",
        "object_identity": "",
        "object_state": "",
        "object_class": "",
        "props": (),
        "wardrobe": (),
        "negative_constraints": (),
        "palette": "",
        "lighting": "",
        "supernatural_effects": (),
        "projection_sha256": "",
    }
    if novel and studio_bible_enrich:
        canon = project_shared_studio_bible_canon(novel, chapter, scene)

    wardrobe = tuple(canon.get("wardrobe") or ())
    effects = tuple(canon.get("supernatural_effects") or ())
    subjects = tuple(canon.get("subjects") or ())
    props = tuple(canon.get("props") or ())
    negatives = tuple(canon.get("negative_constraints") or ())
    identity_lock = str(canon.get("identity_lock") or "")
    lighting_phrase = str(canon.get("lighting_phrase") or canon.get("lighting") or "")
    person = ""
    if identity_lock:
        person = identity_lock
    if wardrobe:
        worn = "wearing " + ", ".join(wardrobe)
        person = (person + "; " if person else "") + worn
    if effects:
        effect_text = ", ".join(effects)
        person = (person + "; " if person else "") + "supernatural effects: " + effect_text


    # Auto-attach wardrobe contract when ENABLE_WARDROBE_PRESERVATION=ON
    _wardrobe_novel_id = ""
    if novel:
        try:
            from tools.studio_bible_adapter import normalize_novel_id as _norm_novel
            _wardrobe_novel_id = _norm_novel(novel, empty_ok=True)
        except Exception:
            _wardrobe_novel_id = str(novel)
    _wardrobe_character_id = str(canon.get("character_id") or "")

    return _apply_identity_auto_attach(_apply_wardrobe_auto_attach(
        GenerationSpec(
        caller_prompt=prompt,
        identity=IdentitySpec(
            character_id=str(canon.get("character_id") or ""),
            studio_bible_binding=StudioBibleBinding(
                snapshot_ref=f"photorealistic-{novel}-{chapter or 'general'}" if novel else "",
                snapshot_sha256=str(canon.get("projection_sha256") or ""),
            ),
        ),
        style=StyleSpec(
            pipeline=PHOTOREALISTIC_PROFILE,
            style_profile=PHOTOREALISTIC_STYLE_SLICE,
            palette=str(canon.get("palette") or ""),
            lighting_design=lighting_phrase,
        ),
        content=ContentSpec(
            subjects=subjects,
            environment=str(canon.get("location") or ""),
            props=props,
            narrative_intent=str(canon.get("magic_effects") or ""),
        ),
        composition=CompositionSpec(
            camera=str(canon.get("camera_phrase") or ""),
            shot_distance=str(canon.get("shot_language") or ""),
            framing=str(canon.get("shot_language") or ""),
            focal_point=identity_lock,
        ),
        conditioning=ConditioningSpec(
            object_state=_object_state(str(canon.get("object_state") or "")),
            object_identity=str(canon.get("object_identity") or ""),
            object_class=str(canon.get("object_class") or ""),
            lighting=lighting_phrase,
            negative_constraints=negatives,
        ),
        model_execution=ModelExecutionSpec(
            backend="comfyui",
            workflow_id=PHOTOREALISTIC_TEMPLATE_ID,
            workflow_version="1.0",
            checkpoint=PHOTOREALISTIC_CHECKPOINT_FILENAME,
            checkpoint_hash=status["sha256"],
            vae="embedded_sdxl",
            loras=(),
            sampler="dpmpp_2m",
            scheduler="karras",
            steps=30,
            cfg=5.0,
            resolution=(1024, 1024),
            seed=seed,
            precision="fp16",
        ),
        body_pose=BodyPoseSpec(person_geometry=person),
        validation=ValidationSpec(pass_rules="photorealistic_cpu_bind"),
        run=RunConfig(seed=seed),
    ),
        character_id=_wardrobe_character_id,
        novel_id=_wardrobe_novel_id,
    ),
        character_id=_wardrobe_character_id,
        novel_id=_wardrobe_novel_id,
    )


def resolve_photorealistic_workflow(spec: GenerationSpec) -> Dict[str, Any]:
    """Build a CheckpointLoaderSimple graph. Does not POST /prompt."""
    status = photorealistic_asset_status()
    if not status["ready"]:
        from tools.image_pipeline_v2_profiles import PhotorealisticProfileUnavailableError

        raise PhotorealisticProfileUnavailableError(status["message"])
    if spec.model_execution.checkpoint != PHOTOREALISTIC_CHECKPOINT_FILENAME:
        from tools.image_pipeline_v2_profiles import PhotorealisticProfileUnavailableError

        raise PhotorealisticProfileUnavailableError(
            "photorealistic profile is unavailable/unqualified: "
            "checkpoint binding does not match the installed photographic asset. "
            "Refusing generation. Will not fall through to cinematic-promo, "
            "realistic-posts, main-posts, local SD, cloud, or stock."
        )
    if spec.model_execution.loras:
        from tools.image_pipeline_v2_profiles import PhotorealisticProfileUnavailableError

        raise PhotorealisticProfileUnavailableError(
            "photorealistic profile is unavailable/unqualified: "
            "a LoRA was bound onto the photographic checkpoint path. "
            "Refusing generation. Will not fall through to azink_real."
        )

    positive_parts = [PHOTOREALISTIC_STYLE_SLICE]
    if spec.identity.character_id:
        positive_parts.append(spec.identity.character_id)
    if spec.content.subjects:
        positive_parts.append(", ".join(spec.content.subjects))
    if spec.body_pose.person_geometry:
        positive_parts.append(spec.body_pose.person_geometry)
    if spec.content.environment:
        positive_parts.append(spec.content.environment)
    if spec.conditioning.object_identity:
        positive_parts.append(spec.conditioning.object_identity)
    if spec.caller_prompt:
        positive_parts.append(spec.caller_prompt)
    for clause in _sba.clip_cinematography_clauses(spec):
        if clause and clause.casefold() not in ", ".join(positive_parts).casefold():
            positive_parts.append(clause)
    negative = ", ".join(spec.conditioning.negative_constraints)
    ckpt = PHOTOREALISTIC_CHECKPOINT_FILENAME
    return {
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ", ".join(positive_parts), "clip": ["10", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["10", 1]},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": spec.model_execution.seed,
                "steps": spec.model_execution.steps,
                "cfg": spec.model_execution.cfg,
                "sampler_name": spec.model_execution.sampler,
                "scheduler": spec.model_execution.scheduler,
                "denoise": 1.0,
                "model": ["10", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["10", 2]}},
        "8": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": "photorealistic-cpu-bind"},
        },
    }


class PhotorealisticPipelineV2:
    """CPU facade. Selects RealVisXL only. Never loads azink_real."""

    PROFILE = PHOTOREALISTIC_PROFILE
    TEMPLATE_ID = PHOTOREALISTIC_TEMPLATE_ID
    GPU_AUTHORIZED = False

    def build_spec(self, **kwargs: Any) -> GenerationSpec:
        return build_photorealistic_generation_spec(**kwargs)

    def resolve(
        self,
        spec: GenerationSpec,
        *,
        replica: int = 0,
        read_bytes: Any = None,
        studio_bible_meta: Optional[Dict[str, Any]] = None,
    ) -> PhotorealisticResolution:
        del replica, read_bytes
        workflow = resolve_photorealistic_workflow(spec)
        provenance = {
            "profile": PHOTOREALISTIC_PROFILE,
            "checkpoint": PHOTOREALISTIC_CHECKPOINT_FILENAME,
            "lora_asset_id": None,
            "trigger": None,
            "loads_azink_real": False,
            "loads_lora_realistic_posts": False,
            "gpu_submitted": False,
            "ksampler_queued": False,
            "studio_bible": studio_bible_meta or {},
        }
        template = type("PhotorealisticTemplate", (), {
            "id": PHOTOREALISTIC_TEMPLATE_ID,
            "version": "1.0",
        })()
        return PhotorealisticResolution(
            spec=spec,
            workflow=workflow,
            template=template,
            provenance=provenance,
        )
