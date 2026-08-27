"""Image Pipeline V2 M4 — ComfyUI adapter (out-of-process, non-GPU qualification).

M4 boundary (per authority record + M3 role freeze):
- Consumes ONLY the M1 GenerationSpec. It does NOT import ComfyUI, does NOT
  depend on Open Design, and ignores Open Design internals.
- This module is the V2 execution adapter: it turns a resolved GenerationSpec
  into a ComfyUI workflow via versioned, hashed templates, submits through the
  ComfyUI REST/WS API, and extracts structured provenance.
- GPU generation is NOT performed here. Actual inference requires a separate
  bounded GPU authority; the adapter only builds + submits + extracts.

Security note: the custom-node security scan is read-only and enumerates the
ComfyUI `custom_nodes/` directory without executing anything.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.generation_spec import GenerationSpec, validate_generation_spec

# --- M4 firewall (binding for M4) ------------------------------------------
# M4 must not pull in Open Design or any rendering-ownership concern.
OPEN_DESIGN_DEPENDENCY = False
CONSUMES_GENERATION_SPEC = True
M4_GPU_AUTHORIZED = False

_TEMPLATE_DIR = Path(__file__).resolve().parent / "workflow_templates"
_DEFAULT_BASE_URL = "http://127.0.0.1:8188"


# --------------------------------------------------------------------------- #
# Workflow template + registry (versioned, hashed)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    version: str
    description: str
    nodes: Dict[str, Any]
    semantic_inputs: Dict[str, Dict[str, str]]
    sha256: str


# --------------------------------------------------------------------------- #
# Structural-guide binding (provider-neutral CPU contract)
# --------------------------------------------------------------------------- #
# This is the canonical structural-control boundary for the V2 ComfyUI workflow
# construction path. It consumes ONLY the SpatialGuideArtifact contract (produced
# by tools/spatial_guide.py or ANY provider-neutral provider) and never depends
# on LocalCpuReferenceProvider, OpenDesign, ControlNet packages, or custom-node
# names. The base workflows intentionally lack executable ControlNet / mask /
# pose / depth nodes; this boundary attaches provider-neutral reference slots
# and an inspectable metadata block so a later ControlNet / mask / pose / depth
# adapter can consume the guides without re-deriving the transport.

GUIDE_NODE_CLASS = "StructuralGuideReference"
GUIDE_METADATA_KEY = "structural_conditioning"
COORDINATE_SPACE_NORMALIZED = "normalized_0_1"


@dataclass(frozen=True)
class StructuralGuideBinding:
    """One structural guide binding fed to (or deriving from) a workflow.

    Required minimum contract (per the spatial-guide CPU wiring gate):
      guide_type            layout | mask | pose | depth
      artifact_path         content-addressed (deterministic) reference, NOT a
                            host-specific filesystem path, so the workflow hash
                            stays deterministic regardless of where bytes land.
      sha256                content hash of the guide artifact bytes
      width, height        artifact pixel dimensions
      coordinate_space      e.g. "normalized_0_1" (pixel/normalized convention)
      source_provider       provider name that produced the artifact
      source_request_hash   sha256 of the SpatialGuideRequest that produced it
    Optional (carried from the request, not duplicated from the artifact):
      semantic_role         subject | object | effect | environment
      target_subject        canon subject the guide is anchored to
      target_object         canon object (e.g. Soulblade)
      body_region           e.g. chest | torso_and_arms
      depth_role            near | far (for depth guides)
      attachment_target     subject an object guide is attached to
    """

    guide_type: str
    artifact_path: str
    sha256: str
    width: int
    height: int
    coordinate_space: str
    source_provider: str
    source_request_hash: str
    semantic_role: str = ""
    target_subject: str = ""
    target_object: str = ""
    body_region: str = ""
    depth_role: str = ""
    attachment_target: str = ""


def attach_structural_guides(
    workflow: Dict[str, Any],
    bindings: Tuple[StructuralGuideBinding, ...],
    *,
    regions: Tuple[Dict[str, Any], ...] = (),
    novel: str = "",
) -> Dict[str, Any]:
    """Return a NEW workflow dict carrying structural guide references.

    Provider-neutral: consumes only the StructuralGuideBinding contract. When
    ``bindings`` is empty it returns a deep copy of the workflow UNCHANGED (the
    OFF path stays byte-identical: no metadata block, no added nodes). When
    bindings are present it:
      - adds a provider-neutral placeholder reference node ``guide_<type>``
        (class_type ``StructuralGuideReference``) wired to the content-addressed
        artifact reference, for the future structural-control consumer;
      - records an inspectable ``structural_conditioning`` metadata block with
        the full binding contract + per-region semantics, which participates in
        the workflow hash so guide changes are causally reflected.

    The artifact's on-disk path is intentionally NOT embedded; only the
    deterministic content-addressed reference is, so the workflow hash is stable
    across machines / output directories.
    """
    wf = copy.deepcopy(dict(workflow))
    if not bindings:
        return wf
    for b in bindings:
        node_id = f"guide_{b.guide_type}"
        if node_id not in wf:
            wf[node_id] = {"class_type": GUIDE_NODE_CLASS, "inputs": {"image": ""}}
        wf[node_id]["inputs"]["image"] = b.artifact_path
    wf[GUIDE_METADATA_KEY] = {
        "contract_version": "1.0",
        "provider_neutral": True,
        "novel": novel,
        "guides": [dataclasses.asdict(b) for b in bindings],
        "regions": list(regions),
    }
    return wf


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _template_sha256(nodes: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(nodes).encode("utf-8")).hexdigest()


def load_template(template_id: str) -> WorkflowTemplate:
    path = _TEMPLATE_DIR / f"{template_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"workflow template not found: {template_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("v2_meta", {})
    nodes = data["nodes"]
    return WorkflowTemplate(
        template_id=meta.get("id", template_id),
        version=meta.get("version", "0.0"),
        description=meta.get("description", ""),
        nodes=nodes,
        semantic_inputs=meta.get("semantic_inputs", {}),
        sha256=_template_sha256(nodes),
    )


def list_templates() -> List[str]:
    if not _TEMPLATE_DIR.exists():
        return []
    return sorted(p.stem for p in _TEMPLATE_DIR.glob("*.json"))


# --------------------------------------------------------------------------- #
# GenerationSpec -> ComfyUI workflow (deterministic)
# --------------------------------------------------------------------------- #


def _build_positive_prompt(spec: GenerationSpec) -> str:
    bits: List[str] = []
    if spec.style.style_profile:
        bits.append(spec.style.style_profile)
    if spec.style.palette:
        bits.append(spec.style.palette)
    if spec.content.environment:
        bits.append(spec.content.environment)
    if spec.conditioning.object_identity:
        bits.append(spec.conditioning.object_identity)
    if spec.content.props:
        bits.append(", ".join(spec.content.props))
    if spec.attachment.required_visible_evidence:
        bits.append("; ".join(spec.attachment.required_visible_evidence))
    return ", ".join(b for b in bits if b)


def _build_negative_prompt(spec: GenerationSpec) -> str:
    return ", ".join(spec.conditioning.negative_constraints)


def build_workflow(
    template: WorkflowTemplate,
    spec: GenerationSpec,
    seed: Optional[int] = None,
    refs: Tuple[Any, ...] = (),
    masks: Tuple[Any, ...] = (),
    structural_guides: Tuple[StructuralGuideBinding, ...] = (),
) -> Dict[str, Any]:
    """Resolve a GenerationSpec into a runnable ComfyUI workflow.

    Deterministic: same (template, spec, seed, refs, masks, structural_guides)
    -> identical nodes. Consumes only GenerationSpec fields; never touches
    Open Design. Provider-neutral structural guides (when supplied) flow through
    ``attach_structural_guides`` (the canonical structural-control boundary).
    """
    validate_generation_spec(spec)  # fail-closed before building
    nodes = json.loads(_canonical_json(template.nodes))  # deep copy

    def set_input(semantic: str, value: Any) -> None:
        mapping = template.semantic_inputs.get(semantic)
        if not mapping:
            return
        node_id = mapping["node"]
        if node_id not in nodes:
            return
        nodes[node_id]["inputs"][mapping["input"]] = value

    set_input("positive_prompt", _build_positive_prompt(spec))
    set_input("negative_prompt", _build_negative_prompt(spec))
    set_input("checkpoint", spec.model_execution.checkpoint)
    set_input("seed", seed if seed is not None else spec.run.seed)
    set_input("steps", spec.model_execution.steps)
    set_input("cfg", spec.model_execution.cfg)
    set_input("sampler", spec.model_execution.sampler)
    set_input("scheduler", spec.model_execution.scheduler)
    set_input("width", spec.model_execution.resolution[0])
    set_input("height", spec.model_execution.resolution[1])

    # LoRAs: list of {name, weight} (modern ComfyUI LoraLoader `lora` input).
    lora_struct = [
        {"name": l.name, "weight": l.weight} for l in spec.model_execution.loras
    ]
    set_input("loras", lora_struct)

    # Optional refs/masks (ControlNet / IP-Adapter / mask) only when supplied.
    if refs:
        set_input("ipadapter", refs[0].asset_path if hasattr(refs[0], "asset_path") else str(refs[0]))
    if masks:
        set_input("mask", masks[0].asset_path if hasattr(masks[0], "asset_path") else str(masks[0]))

    # Canonical structural-control boundary (provider-neutral). When empty, this
    # is a no-op deep copy, so the OFF / non-spatial path is unchanged.
    nodes = attach_structural_guides(nodes, tuple(structural_guides))

    return nodes


# --------------------------------------------------------------------------- #
# Real mask / regional control node wiring (first runtime structural family)
# --------------------------------------------------------------------------- #
# Wires the provider-neutral StructuralGuideBinding + SpatialGuideRequest into
# ComfyUI CORE nodes (ConditioningSetMask + LoadImageMask + CLIPTextEncode),
# no custom-node package and no external ControlNet model required. This is the
# single minimal structural factor for the causal GPU test:
#   text-only (OFF)  -> base workflow, no region nodes
#   structural (ON)  -> base + region-masked conditioning subgraph
# Every other model execution parameter (checkpoint, LoRA, seed, sampler,
# scheduler, steps, CFG, resolution, caller prompt, Studio Bible enrichment)
# is held identical by the caller. Host paths are never embedded; only a
# deterministic content-addressed mask basename + sha256 participate.


def _find_ksampler(nodes: Dict[str, Any]) -> Optional[str]:
    for nid, n in nodes.items():
        if isinstance(n, dict) and n.get("class_type") == "KSampler":
            return nid
    return None


def _find_positive_node(nodes: Dict[str, Any], ksampler_id: str) -> Optional[str]:
    ks = nodes.get(ksampler_id)
    if not ks:
        return None
    pos_ref = ks.get("inputs", {}).get("positive")
    if isinstance(pos_ref, list) and pos_ref:
        return str(pos_ref[0])
    return None


def _find_negative_node(nodes: Dict[str, Any], ksampler_id: str) -> Optional[str]:
    ks = nodes.get(ksampler_id)
    if not ks:
        return None
    neg_ref = ks.get("inputs", {}).get("negative")
    if isinstance(neg_ref, list) and neg_ref:
        return str(neg_ref[0])
    return None


def apply_mask_regional_conditioning(
    base_workflow: Dict[str, Any],
    request: Any,
    bindings: Tuple[Any, ...],
    *,
    output_dir: Any,
    clip_source: Tuple[str, int] = ("11", 1),
) -> Dict[str, Any]:
    """Return a NEW workflow with built-in mask/regional conditioning applied.

    Provider-neutral: consumes the SpatialGuideRequest + StructuralGuideBinding
    contract only. When ``request`` is None or carries no structural regions,
    returns a deep copy of ``base_workflow`` UNCHANGED (OFF path preserved).

    The region masks are materialized (deterministic PNGs) to ``output_dir``
    (the ComfyUI input directory at execution time) and referenced by
    content-addressed basename, never by host path.
    """
    if request is None:
        return copy.deepcopy(dict(base_workflow))

    from tools import spatial_guide as _sg

    region_masks = _sg.render_region_masks(request, output_dir)
    if not region_masks:
        return copy.deepcopy(dict(base_workflow))

    nodes = copy.deepcopy(dict(base_workflow))

    ksampler_id = _find_ksampler(nodes)
    pos_node = _find_positive_node(nodes, ksampler_id) if ksampler_id else None
    if not ksampler_id or not pos_node or pos_node not in nodes:
        # Cannot safely repoint; fall back to unchanged base (fail-closed).
        return copy.deepcopy(dict(base_workflow))

    # Global conditioning carries the full production prompt everywhere.
    # Each structural region is encoded separately, masked to its region, and
    # combined (pairwise ConditioningCombine) with the global conditioning so
    # the base prompt stays intact and the region prompt is emphasized only
    # inside its mask. This is the single minimal structural factor.
    combine_acc: List[Any] = [pos_node, 0]
    meta_regions: List[Dict[str, Any]] = []
    for label, info in region_masks.items():
        load_id = f"sm_load_{label}"
        enc_id = f"sm_enc_{label}"
        set_id = f"sm_set_{label}"
        combine_id = f"sm_combine_{label}"
        nodes[load_id] = {
            "class_type": "LoadImageMask",
            "inputs": {"image": info["basename"], "channel": "red"},
        }
        nodes[enc_id] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": info["prompt"], "clip": list(clip_source)},
        }
        nodes[set_id] = {
            "class_type": "ConditioningSetMask",
            "inputs": {
                "conditioning": [enc_id, 0],
                "mask": [load_id, 0],
                "strength": 1.0,
                "set_cond_area": "default",
            },
        }
        nodes[combine_id] = {
            "class_type": "ConditioningCombine",
            "inputs": {"conditioning_1": list(combine_acc), "conditioning_2": [set_id, 0]},
        }
        combine_acc = [combine_id, 0]
        neg_prompt = info.get("negative_prompt") or ""
        meta_regions.append({
            "region_label": info["region_label"],
            "label": info["region_label"],
            "role": info["role"],
            "target": info["target"],
            "attachment_target": info["target"] if info["role"] == "object" else "",
            "zone": info["zone"],
            "prompt": info["prompt"],
            "negative_prompt": neg_prompt,
            "has_negative": bool(neg_prompt),
            "mask_basename": info["basename"],
            "mask_sha256": info["sha256"],
        })

    nodes[ksampler_id]["inputs"]["positive"] = list(combine_acc)

    # OPTIONAL regional NEGATIVE chain. Only regions that carry a negative prompt
    # (currently the hand-hilt isolation factor) contribute; all other regions
    # stay positive-only, so the prior regional conditioning behaviour is
    # byte-for-byte unchanged and this remains a single-factor addition.
    neg_node = _find_negative_node(nodes, ksampler_id)
    neg_region_labels = [
        lbl for lbl, info in region_masks.items() if info.get("negative_prompt")
    ]
    if neg_node is not None and neg_node in nodes and neg_region_labels:
        neg_acc: List[Any] = [neg_node, 0]
        for label, info in region_masks.items():
            neg_prompt = info.get("negative_prompt")
            if not neg_prompt:
                continue
            load_id = f"sm_load_{label}"  # reuse the same mask loader
            nenc_id = f"sm_enc_neg_{label}"
            nset_id = f"sm_set_neg_{label}"
            ncombine_id = f"sm_combine_neg_{label}"
            nodes[nenc_id] = {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": neg_prompt, "clip": list(clip_source)},
            }
            nodes[nset_id] = {
                "class_type": "ConditioningSetMask",
                "inputs": {
                    "conditioning": [nenc_id, 0],
                    "mask": [load_id, 0],
                    "strength": 1.0,
                    "set_cond_area": "default",
                },
            }
            nodes[ncombine_id] = {
                "class_type": "ConditioningCombine",
                "inputs": {"conditioning_1": list(neg_acc), "conditioning_2": [nset_id, 0]},
            }
            neg_acc = [ncombine_id, 0]
        nodes[ksampler_id]["inputs"]["negative"] = list(neg_acc)

    nodes[GUIDE_METADATA_KEY] = {
        "contract_version": "2.0",
        "provider_neutral": True,
        "control_family": "mask_regional",
        "real_node": "ConditioningSetMask",
        "custom_node_installed": False,
        "external_control_model": False,
        "guides": [dataclasses.asdict(b) for b in bindings],
        "regions": meta_regions,
    }
    return nodes


# --------------------------------------------------------------------------- #
# Provenance extraction (structured, hashable)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# OpenPose SDXL ControlNet runtime binding (second structural family)
# --------------------------------------------------------------------------- #
# This is the SINGLE production owner for OpenPose runtime binding. It wires a
# resolved OpenPose-18 pose guide artifact into ComfyUI CORE nodes:
#
#   ControlNetLoader(control_net_name=asset_reference)
#       -> CONTROL_NET
#   LoadImage(image=content_addressed_basename)
#       -> IMAGE
#   ControlNetApplyAdvanced(positive, negative, control_net, image,
#                           strength, start_percent, end_percent)
#       -> positive CONDITIONING (-> KSampler.positive)
#       -> negative CONDITIONING (-> KSampler.negative)
#
# No custom node and no external model download is required: ControlNetLoader,
# LoadImage, ControlNetApplyAdvanced are all ComfyUI CORE nodes (verified via the
# read-only /object_info contract). The OpenPose ControlNet asset is resolved
# through the canonical approved-asset registry (image_pipeline_v2_assets) by its
# unique asset_id; the backend-visible reference is the bare filename
# ``diffusion_pytorch_model.safetensors`` (never the private absolute host path).
#
# Provider-neutral: it consumes ONLY the SpatialGuideArtifact contract (produced
# by PoseGuideProvider or any provider-neutral provider). It does NOT depend on
# PoseGuideProvider internals, Open Design, or any custom-node package.
#
# Host independence: the LoadImage node references a content-addressed BASENAME
# (derived from the pose artifact SHA-256), not a private host path. The workflow
# hash therefore depends on the guide content SHA, the OpenPose asset reference,
# and the pose-control settings — never on C:\..., temp dirs, or output dirs.

OPENPOSE_CONTROLNET_ASSET_ID = "controlnet_openpose_sdxl_1.0"

# No prior authority established pose-specific ControlNet strength / start / end
# magnitudes (verified: no such value exists in the approved asset registry, the
# M4 asset manifest, the qualification plans, or any CPU test). Per the
# single-factor governance, the binding uses the ControlNetApplyAdvanced NODE'S
# OWN documented default values (read from /object_info). These are explicit and
# deterministic (not RNG, not an invented arbitrary number), but the magnitude is
# flagged as requiring separate authority confirmation in the GPU causal A/B
# stage (NEXT_STAGE_REQUIRES_GPU=YES). The node contract itself is fixed.
OPENPOSE_RUNTIME_PARAMETERS_REQUIRE_AUTHORITY = True

# ControlNetApplyAdvanced /object_info documented node defaults.
OPENPOSE_CONTROLNET_DEFAULT_STRENGTH = 1.0
OPENPOSE_CONTROLNET_DEFAULT_START_PERCENT = 0.0
OPENPOSE_CONTROLNET_DEFAULT_END_PERCENT = 1.0

# Deterministic, stable node ids for the OpenPose subgraph.
OPENPOSE_LOADER_NODE_ID = "pose_controlnet_loader"
OPENPOSE_LOAD_IMAGE_NODE_ID = "pose_load_image"
OPENPOSE_APPLY_NODE_ID = "pose_controlnet_apply"

# --------------------------------------------------------------------------- #
# Bounded explicit-hand-interaction OpenPose capability amendment
# --------------------------------------------------------------------------- #
# This is a SEPARATE bounded capability from the global Realistic ControlNet
# policy. The global policy REALISTIC_CONTROLNET_POLICY remains
# "DISABLED_FOR_BASE_PROFILE"; this gate does NOT change it.
#
# The gate permits ONLY the already-qualified EN explicit hand-interaction
# OpenPose path. The discriminator is derived provider-neutrally from the pose
# artifact provenance ITSELF (body_only == False AND
# hand_parameters_require_authority present), never from novel strings,
# filenames, basename guessing, prompt text, object names, or user prose.
#
# Authorization is fail-closed: any malformed / missing / ambiguous condition
# denies the capability.
EXPLICIT_STRUCTURAL_OPENPOSE_ALLOWED = True

OPENPOSE_APPROVED_BACKEND_REFERENCE = "diffusion_pytorch_model.safetensors"
OPENPOSE_APPROVED_SHA256 = (
    "B8524E557A7DF60D081F5D4A0EB109967D107DF217943BF88C2D99B9EBCC06C5"
)

OPENPOSE_CAPABILITY_DENIAL_REASON = "capability_gate_denied"


def is_explicit_openpose_structural_permitted(
    bundle: Any,
    request: Any,
    *,
    controlnet_asset_id: str = OPENPOSE_CONTROLNET_ASSET_ID,
    read_bytes: Any = None,
) -> bool:
    """Fail-closed capability gate for the explicit hand-interaction OpenPose path.

    Returns True ONLY when ALL of the following hold:
      1. EXPLICIT_STRUCTURAL_OPENPOSE_ALLOWED is True.
      2. request exists (is truthy).
      3. bundle contains exactly/uniquely one usable pose artifact.
      4. the pose artifact provenance indicates explicit hand interaction:
             body_only == False
         AND hand_parameters_require_authority is present.
      5. the approved OpenPose asset resolves by canonical asset_id (fail-closed).
      6. the backend reference equals OPENPOSE_APPROVED_BACKEND_REFERENCE.
      7. the asset SHA equals OPENPOSE_APPROVED_SHA256.
    Any malformed / missing / ambiguous condition fails closed (returns False).
    """
    try:
        if not EXPLICIT_STRUCTURAL_OPENPOSE_ALLOWED:
            return False
        if not request:
            return False
        artifacts = getattr(bundle, "artifacts", ()) or ()
        pose_arts = [
            a for a in artifacts if getattr(a, "guide_type", "") == "pose"
        ]
        # exactly/uniquely one usable pose artifact required
        if len(pose_arts) != 1:
            return False
        pose = pose_arts[0]
        if not isinstance(getattr(pose, "provenance", None), dict):
            return False
        prov = pose.provenance
        if prov.get("body_only") is not False:
            return False
        if "hand_parameters_require_authority" not in prov:
            return False
        # Resolve approved asset by canonical identity (fail-closed).
        from tools.image_pipeline_v2_assets import (
            normalize_comfyui_reference,
            resolve_asset,
        )

        asset = resolve_asset(controlnet_asset_id, read_bytes=read_bytes)
        reference = normalize_comfyui_reference(asset.comfyui_reference)
        if reference.replace("\\", "/").split("/")[-1] != OPENPOSE_APPROVED_BACKEND_REFERENCE:
            return False
        if (asset.sha256 or "").upper() != OPENPOSE_APPROVED_SHA256.upper():
            return False
        return True
    except Exception:
        return False


def _record_openpose_capability_denied(
    wf: Dict[str, Any], pose_art: Any
) -> Dict[str, Any]:
    """Record truthful structural metadata: OpenPose denied by the capability gate.

    No ControlNetLoader / LoadImage / ControlNetApplyAdvanced nodes are added.
    The pose artifact remains represented in the structural metadata guides but
    is marked capability_denied so downstream provenance is honest.
    """
    meta = dict(wf.get(GUIDE_METADATA_KEY, {}))
    guides = list(meta.get("guides", []))
    pose_updated = False
    for g in guides:
        if g.get("guide_type") == "pose":
            g["openpose_capability"] = "DENIED_BY_CAPABILITY_GATE"
            pose_updated = True
    if not pose_updated:
        guides.append({
            "guide_type": "pose",
            "artifact_path": f"spatial_guide://pose/{pose_art.sha256}.png",
            "sha256": pose_art.sha256,
            "openpose_capability": "DENIED_BY_CAPABILITY_GATE",
        })
    meta["guides"] = guides
    meta["openpose_capability"] = {
        "permitted": False,
        "denial_reason": OPENPOSE_CAPABILITY_DENIAL_REASON,
        "control_family": "openpose_controlnet",
    }
    wf[GUIDE_METADATA_KEY] = meta
    return wf


@dataclass(frozen=True)
class PoseControlNetParams:
    """Explicit, required pose-ControlNet runtime parameters.

    There are NO hidden defaults inside the binding: the caller must pass an
    explicit params object. The module-level ``OPENPOSE_CONTROLNET_DEFAULT_*``
    constants are the only sanctioned starting values (the node-documented
    defaults) and are flagged as requiring authority confirmation before GPU use.
    """

    strength: float
    start_percent: float
    end_percent: float


@dataclass(frozen=True)
class PoseControlNetBinding:
    """Typed runtime contract distinguishing a generic structural guide reference
    from a pose guide that MUST be applied through the OpenPose ControlNet.

    Reuses the canonical content-addressed guide identity (guide_type, sha256,
    content-addressed artifact_path) and adds only the information ComfyUI needs
    to apply OpenPose ControlNet at runtime:
      - controlnet_asset_id  (registry identity, NOT a path)
      - controlnet_reference  (backend-visible basename, NOT a host path)
      - strength / start_percent / end_percent
    It does NOT create a second asset registry; it references the existing one by
    asset_id.
    """

    guide_type: str = "pose"
    artifact_path: str = ""          # content-addressed spatial_guide://<sha>.png
    artifact_basename: str = ""      # ComfyUI-loadable basename (sha-derived)
    sha256: str = ""
    width: int = 0
    height: int = 0
    controlnet_asset_id: str = OPENPOSE_CONTROLNET_ASSET_ID
    controlnet_reference: str = ""
    strength: float = OPENPOSE_CONTROLNET_DEFAULT_STRENGTH
    start_percent: float = OPENPOSE_CONTROLNET_DEFAULT_START_PERCENT
    end_percent: float = OPENPOSE_CONTROLNET_DEFAULT_END_PERCENT


def _resolve_openpose_asset(controlnet_asset_id: str) -> Any:
    """Resolve the approved OpenPose ControlNet asset by unique id (fail-closed)."""
    from tools.image_pipeline_v2_assets import (
        AssetResolutionError,
        normalize_comfyui_reference,
        resolve_asset,
    )

    asset = resolve_asset(controlnet_asset_id)
    reference = normalize_comfyui_reference(asset.comfyui_reference)
    # Backend-invalid reference fails closed before any node is emitted.
    if reference != "diffusion_pytorch_model.safetensors":
        raise AssetResolutionError(
            f"OpenPose ControlNet backend reference {reference!r} is not the "
            f"approved bare filename 'diffusion_pytorch_model.safetensors'; "
            f"refusing to emit an invalid ControlNetLoad value"
        )
    return asset, reference


def _find_ksampler_positive_negative(
    nodes: Dict[str, Any], ksampler_id: str
) -> Tuple[Optional[List[Any]], Optional[List[Any]]]:
    ks = nodes.get(ksampler_id)
    if not ks:
        return None, None
    pos = ks.get("inputs", {}).get("positive")
    neg = ks.get("inputs", {}).get("negative")
    if isinstance(pos, list) and pos:
        pos = list(pos)
    else:
        pos = None
    if isinstance(neg, list) and neg:
        neg = list(neg)
    else:
        neg = None
    return pos, neg


def apply_openpose_controlnet_conditioning(
    base_workflow: Dict[str, Any],
    pose_artifact: Any,
    request: Any,
    *,
    output_dir: Any = None,
    params: Optional[PoseControlNetParams] = None,
    controlnet_asset_id: str = OPENPOSE_CONTROLNET_ASSET_ID,
) -> Dict[str, Any]:
    """Return a NEW workflow with the real OpenPose ControlNet subgraph applied.

    Provider-neutral: consumes only the SpatialGuideArtifact contract. When
    ``pose_artifact`` is None (no pose guide), returns a deep copy of
    ``base_workflow`` UNCHANGED (no-pose path preserved byte-for-byte).

    The subgraph is wired AFTER any prior conditioning (e.g. mask/regional),
    consuming the current KSampler positive/negative refs and repointing the
    KSampler to the ControlNetApplyAdvanced outputs, so every other model
    execution parameter is held identical.
    """
    if pose_artifact is None:
        return copy.deepcopy(dict(base_workflow))

    if params is None:
        params = PoseControlNetParams(
            strength=OPENPOSE_CONTROLNET_DEFAULT_STRENGTH,
            start_percent=OPENPOSE_CONTROLNET_DEFAULT_START_PERCENT,
            end_percent=OPENPOSE_CONTROLNET_DEFAULT_END_PERCENT,
        )

    asset, reference = _resolve_openpose_asset(controlnet_asset_id)

    nodes = copy.deepcopy(dict(base_workflow))

    ksampler_id = _find_ksampler(nodes)
    pos_ref, neg_ref = _find_ksampler_positive_negative(nodes, ksampler_id) \
        if ksampler_id else (None, None)
    if not ksampler_id or not pos_ref or not neg_ref:
        # Cannot safely repoint; fall back to unchanged base (fail-closed).
        return copy.deepcopy(dict(base_workflow))

    # Content-addressed, host-independent loadable basename (not a private path).
    pose_basename = f"pose_{pose_artifact.sha256}.png"
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / pose_basename
        if not target.exists():
            target.write_bytes(Path(pose_artifact.path).read_bytes())

    # 1. ControlNetLoader (CORE) -> CONTROL_NET
    nodes[OPENPOSE_LOADER_NODE_ID] = {
        "class_type": "ControlNetLoader",
        "inputs": {"control_net_name": reference},
    }

    # 2. LoadImage (CORE) -> IMAGE (content-addressed basename only)
    nodes[OPENPOSE_LOAD_IMAGE_NODE_ID] = {
        "class_type": "LoadImage",
        "inputs": {"image": pose_basename},
    }

    # 3. ControlNetApplyAdvanced (CORE) consumes current conditioning + control_net
    #    + pose image, emits adjusted positive/negative conditioning.
    nodes[OPENPOSE_APPLY_NODE_ID] = {
        "class_type": "ControlNetApplyAdvanced",
        "inputs": {
            "positive": list(pos_ref),
            "negative": list(neg_ref),
            "control_net": [OPENPOSE_LOADER_NODE_ID, 0],
            "image": [OPENPOSE_LOAD_IMAGE_NODE_ID, 0],
            "strength": params.strength,
            "start_percent": params.start_percent,
            "end_percent": params.end_percent,
        },
    }

    # 4. Repoint the sampler to the ControlNet-adjusted conditioning.
    nodes[ksampler_id]["inputs"]["positive"] = [OPENPOSE_APPLY_NODE_ID, 0]
    nodes[ksampler_id]["inputs"]["negative"] = [OPENPOSE_APPLY_NODE_ID, 1]

    # 5. Inspectable metadata (merged with any existing structural metadata).
    binding = PoseControlNetBinding(
        artifact_path=(
            f"spatial_guide://pose/{pose_artifact.sha256}.png"
        ),
        artifact_basename=pose_basename,
        sha256=pose_artifact.sha256,
        width=pose_artifact.width,
        height=pose_artifact.height,
        controlnet_asset_id=asset.asset_id,
        controlnet_reference=reference,
        strength=params.strength,
        start_percent=params.start_percent,
        end_percent=params.end_percent,
    )
    meta = dict(nodes.get(GUIDE_METADATA_KEY, {}))
    meta.update({
        "provider_neutral": True,
        "control_family": "openpose_controlnet",
        "real_node": "ControlNetApplyAdvanced",
        "custom_node_installed": False,
        "external_control_model": True,
        "controlnet_asset_id": asset.asset_id,
        "controlnet_reference": reference,
        "pose_guide_sha256": pose_artifact.sha256,
        "pose_strength": params.strength,
        "pose_start_percent": params.start_percent,
        "pose_end_percent": params.end_percent,
        "pose_parameters_require_authority": OPENPOSE_RUNTIME_PARAMETERS_REQUIRE_AUTHORITY,
    })
    guides = list(meta.get("guides", []))
    _pose_updated = False
    for g in guides:
        if g.get("guide_type") == "pose":
            g["artifact_path"] = binding.artifact_path
            g["artifact_basename"] = binding.artifact_basename
            g["sha256"] = binding.sha256
            g["controlnet_asset_id"] = asset.asset_id
            g["controlnet_reference"] = reference
            g["strength"] = params.strength
            g["start_percent"] = params.start_percent
            g["end_percent"] = params.end_percent
            _pose_updated = True
    if not _pose_updated:
        guides.append({
            "guide_type": "pose",
            "artifact_path": binding.artifact_path,
            "artifact_basename": binding.artifact_basename,
            "sha256": binding.sha256,
            "controlnet_asset_id": asset.asset_id,
            "controlnet_reference": reference,
            "strength": params.strength,
            "start_percent": params.start_percent,
            "end_percent": params.end_percent,
        })
    meta["guides"] = guides
    nodes[GUIDE_METADATA_KEY] = meta
    return nodes


# --------------------------------------------------------------------------- #
# Production structural-control composition owner
# --------------------------------------------------------------------------- #
# Single production owner that combines the qualified structural families in the
# canonical order (base CLIP -> mask/regional -> OpenPose ControlNet -> sampler):
#   apply_mask_regional_conditioning  (mask/regional owner)
#   apply_openpose_controlnet_conditioning (OpenPose owner)
# Both sub-owners remain the sole owners of their respective families; this is the
# composition boundary only.


def apply_structural_runtime_control(
    base_workflow: Dict[str, Any],
    request: Any,
    bundle: Any,
    output_dir: Any,
    *,
    allow_openpose: bool = True,
    pose_params: Optional[PoseControlNetParams] = None,
    clip_source: Tuple[str, int] = ("11", 1),
) -> Dict[str, Any]:
    """Return a NEW workflow with mask/regional + OpenPose ControlNet applied.

    Provider-neutral. The OFF path (request is None or bundle/pose absent) returns
    a deep copy of the base UNCHANGED, so the no-pose / no-mask workflow stays
    byte-identical to the pre-guide contract.

    Ordering is explicit: mask/regional conditioning is applied first, then the
    OpenPose ControlNet subgraph wraps the resulting conditioning, then the
    sampler consumes the ControlNet-adjusted positive/negative.
    """
    wf = copy.deepcopy(dict(base_workflow))

    # StructuralGuideBundle carries request + artifacts (no precomputed bindings).
    bindings = getattr(bundle, "bindings", None)
    if bindings is None:
        from tools.spatial_guide import build_structural_bindings

        bindings = build_structural_bindings(tuple(bundle.artifacts), bundle.request)
    if request is not None and bindings:
        wf = apply_mask_regional_conditioning(
            wf, request, tuple(bindings), output_dir=output_dir,
            clip_source=clip_source,
        )

    pose_art = None
    if getattr(bundle, "artifacts", ()):
        pose_art = next(
            (a for a in bundle.artifacts if getattr(a, "guide_type", "") == "pose"),
            None,
        )
    if pose_art is not None:
        if allow_openpose:
            wf = apply_openpose_controlnet_conditioning(
                wf, pose_art, request, output_dir=output_dir, params=pose_params,
            )
        else:
            # Capability gate denied OpenPose: no ControlNetLoader / pose
            # LoadImage / ControlNetApplyAdvanced nodes. Record truthful
            # structural metadata so provenance is honest.
            wf = _record_openpose_capability_denied(wf, pose_art)
    return wf


def extract_provenance(
    template: WorkflowTemplate,
    built_workflow: Dict[str, Any],
    spec: GenerationSpec,
) -> Dict[str, Any]:
    """Independent, structured provenance for a built workflow.

    Mirrors the V2 manifest principle: the Automation Tool owns provenance, not
    ComfyUI-native metadata alone.
    """
    return {
        "workflow_id": template.template_id,
        "workflow_version": template.version,
        "workflow_sha256": template.sha256,
        "built_workflow_sha256": hashlib.sha256(
            _canonical_json(built_workflow).encode("utf-8")
        ).hexdigest(),
        "spec_version": spec.spec_version,
        "pipeline": spec.style.pipeline,
        "seed": spec.run.seed,
        "checkpoint": spec.model_execution.checkpoint,
        "checkpoint_hash": spec.model_execution.checkpoint_hash,
        "loras": [
            {"name": l.name, "hash": l.hash, "weight": l.weight}
            for l in spec.model_execution.loras
        ],
        "resolution": list(spec.model_execution.resolution),
        "object_state": spec.conditioning.object_state,
        "open_design_dependency": OPEN_DESIGN_DEPENDENCY,
    }


# --------------------------------------------------------------------------- #
# Out-of-process ComfyUI client (never imports ComfyUI)
# --------------------------------------------------------------------------- #


class ComfyUIAdapter:
    """REST/WS client for a running ComfyUI instance.

    Out-of-process only (urllib). No ComfyUI import. Submitting a workflow is an
    execution action and MUST NOT be called under M4 (GPU prohibited); the method
    exists so the eventual GPU-gated execution path is wired through one place.
    """

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def system_stats(self) -> Dict[str, Any]:
        return self._get("/system_stats")

    def queue_status(self) -> Dict[str, Any]:
        return self._get("/queue")

    def submit_workflow(self, workflow_dict: Dict[str, Any],
                        client_id: Optional[str] = None) -> str:
        """POST /prompt and return the prompt_id. Execution action — GPU-gated."""
        if not M4_GPU_AUTHORIZED:
            raise RuntimeError(
                "ComfyUIAdapter.submit_workflow requires GPU authority (M4_GPU_AUTHORIZED); "
                "blocked under non-GPU M4 qualification."
            )
        body = {"prompt": workflow_dict}
        if client_id:
            body["client_id"] = client_id
        result = self._post("/prompt", body)
        return result["prompt_id"]

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        return self._get(f"/history/{prompt_id}")

    def get_image(self, subfolder: str, filename: str,
                  img_type: str = "output") -> bytes:
        url = f"{self.base_url}/view?subfolder={subfolder}&filename={filename}&type={img_type}"
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return r.read()


# --------------------------------------------------------------------------- #
# Custom-node security scan (read-only)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CustomNodeFinding:
    name: str
    has_license: bool
    has_git: bool
    network_risk: bool
    notes: str = ""


_NETWORK_IMPORTS = ("urllib", "requests", "socket", "httpx", "aiohttp", "subprocess", "os.system")


def custom_node_security_scan(custom_nodes_dir: str) -> Dict[str, Any]:
    """Read-only enumeration + heuristic risk scan of ComfyUI custom nodes.

    Returns a structured report; performs no execution. A node is flagged
    network_risk when its Python sources import network/subprocess primitives.
    """
    root = Path(custom_nodes_dir)
    findings: List[CustomNodeFinding] = []
    if root.exists():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in ("__pycache__",):
                continue
            has_license = any((entry / lic).exists() for lic in
                              ("LICENSE", "LICENSE.md", "LICENSE.txt"))
            has_git = (entry / ".git").exists()
            network_risk = False
            note = ""
            py_files = list(entry.rglob("*.py"))
            for pf in py_files:
                try:
                    text = pf.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(token in text for token in _NETWORK_IMPORTS):
                    network_risk = True
                    note = f"network/subprocess primitive in {pf.name}"
                    break
            findings.append(CustomNodeFinding(
                name=entry.name, has_license=has_license,
                has_git=has_git, network_risk=network_risk, notes=note,
            ))
    passed = all(not f.network_risk for f in findings)
    return {
        "scanned_dir": str(root),
        "node_count": len(findings),
        "findings": [f.__dict__ for f in findings],
        "passed": passed,
    }
