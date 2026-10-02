"""Image Pipeline V2 GenerationSpec (M1 foundation).

M1 builds the canonical GenerationSpec contract: schema, canonical
serialization, hashing, fail-closed validation, and semantic diffing.

Reuse note (binding provenance for M1):
    M1_REUSE_SOURCE=tools/gate6a_conditioning.py
    M1_REUSE_SOURCE_GIT_STATE=UNTRACKED
    M1_REUSE_SOURCE_SHA256=41e49e778a1002cacb06345aff3c7260178f9360689ad646921d91da3dc3c2a4
    M1_REUSE_SOURCE_FUNCTIONS_VERIFIED=ConditioningSpec, RunConfig, canonical_serialize,
        spec_sha256, run_sha256, diff_conditioning_specs, assert_single_changed_dimension

The structured-conditioning machinery proven in `gate6a_conditioning.py` is the
prototype backbone. This module reuses it directly:
  - ConditioningSpec / RunConfig: embedded as the structured conditioning + run
    dimensions of a GenerationSpec.
  - canonical_serialize / spec_sha256 / run_sha256: reused for the embedded
    conditioning/run hashes and as the basis for the whole-spec hash.
  - diff_conditioning_specs / assert_single_changed_dimension: reused as the
    primary causal-isolation gate on the embedded ConditioningSpec.

This module does NOT run GPU inference, does NOT select a production generation
policy, and does NOT modify the frozen generator. It is the contract, not the
experiment.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from tools.gate6a_conditioning import (
    CausalIsolationError,
    ConditioningSpec,
    RenderedConditioning,
    RunConfig,
    assert_single_changed_dimension,
    build_provenance,
    canonical_serialize,
    canonical_serialize_obj,
    diff_conditioning_specs,
    render_conditioning,
    run_sha256,
    spec_sha256,
)

# --- M1 reuse provenance (see module docstring; source is UNTRACKED, pinned) ---
M1_REUSE_SOURCE = "tools/gate6a_conditioning.py"
M1_REUSE_SOURCE_GIT_STATE = "UNTRACKED"
M1_REUSE_SOURCE_SHA256 = "41e49e778a1002cacb06345aff3c7260178f9360689ad646921d91da3dc3c2a4"

GENERATION_SPEC_SCHEMA_VERSION = "1.0"
ALLOWED_PIPELINES = ("comic", "realistic")
ALLOWED_STATES = ("drawn", "sheathed", "prop")


# --------------------------------------------------------------------------- #
# V2 domain specs (typed, independently addressable)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StudioBibleBinding:
    snapshot_ref: str = ""
    snapshot_sha256: str = ""


@dataclass(frozen=True)
class ReferenceBinding:
    asset_path: str = ""
    asset_sha256: str = ""


@dataclass(frozen=True)
class IdentitySpec:
    character_id: str = ""
    character_version: str = ""
    object_id: str = ""
    object_version: str = ""
    studio_bible_binding: StudioBibleBinding = field(default_factory=StudioBibleBinding)
    reference_bindings: Tuple[ReferenceBinding, ...] = ()


@dataclass(frozen=True)
class ContentSpec:
    subjects: Tuple[str, ...] = ()
    action: str = ""
    environment: str = ""
    props: Tuple[str, ...] = ()
    narrative_intent: str = ""


@dataclass(frozen=True)
class StyleSpec:
    pipeline: str = ""  # comic | realistic
    style_profile: str = ""
    palette: str = ""
    line_shading_behavior: str = ""
    material_treatment: str = ""
    lighting_design: str = ""


@dataclass(frozen=True)
class CompositionSpec:
    framing: str = ""
    shot_distance: str = ""
    camera: str = ""
    viewpoint: str = ""
    focal_point: str = ""
    negative_space: str = ""
    aspect_ratio: str = ""


@dataclass(frozen=True)
class BodyPoseSpec:
    pose: str = ""
    person_geometry: str = ""
    landmark_bindings: Tuple[str, ...] = ()
    silhouette_regions: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectGeometrySpec:
    object_orientation: str = ""
    size: str = ""
    location: str = ""
    anchor: str = ""
    placement: str = ""
    attachment_point: str = ""


@dataclass(frozen=True)
class AttachmentSpec:
    attachment_type: str = ""  # sheathed | belt | strap | harness | hand_grip | mount
    mechanism: str = ""
    required_visible_evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OcclusionDepthSpec:
    front_behind: Tuple[str, ...] = ()
    body_region_relationships: Tuple[str, ...] = ()
    depth_ordering: Tuple[str, ...] = ()
    masks: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceSpec:
    character_refs: Tuple[ReferenceBinding, ...] = ()
    object_refs: Tuple[ReferenceBinding, ...] = ()
    environment_refs: Tuple[ReferenceBinding, ...] = ()
    style_refs: Tuple[ReferenceBinding, ...] = ()


@dataclass(frozen=True)
class LoRABinding:
    name: str = ""
    hash: str = ""
    weight: float = 1.0


@dataclass(frozen=True)
class ModelExecutionSpec:
    backend: str = "comfyui"
    workflow_id: str = ""
    workflow_version: str = ""
    checkpoint: str = ""
    checkpoint_hash: str = ""
    vae: str = ""
    loras: Tuple[LoRABinding, ...] = ()
    sampler: str = ""
    scheduler: str = ""
    steps: int = 20
    cfg: float = 7.5
    denoise: float = 1.0
    resolution: Tuple[int, int] = (1024, 1024)
    seed: int = 1_000_003
    precision: str = "fp16"


@dataclass(frozen=True)
class RepairSpec:
    repair_allowed: bool = False
    repair_regions: Tuple[str, ...] = ()
    repair_reason: str = ""
    max_passes: int = 0
    immutable_acceptance_criteria: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationSpec:
    mechanical_fields: Tuple[str, ...] = ()
    visual_fields: Tuple[str, ...] = ()
    pass_rules: str = ""
    reviewer_requirements: str = ""
    reproducibility_requirements: str = ""


# --------------------------------------------------------------------------- #
# GenerationSpec (canonical V2 contract)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GenerationSpec:
    """Canonical V2 generation contract.

    Every field is an independently addressable domain. The embedded
    `conditioning` (ConditioningSpec) and `run` (RunConfig) are reused from
    gate6a_conditioning.py so the proven causal-isolation primitive applies
    directly.
    """

    spec_version: str = GENERATION_SPEC_SCHEMA_VERSION
    caller_prompt: str = ""
    identity: IdentitySpec = field(default_factory=IdentitySpec)
    content: ContentSpec = field(default_factory=ContentSpec)
    style: StyleSpec = field(default_factory=StyleSpec)
    composition: CompositionSpec = field(default_factory=CompositionSpec)
    body_pose: BodyPoseSpec = field(default_factory=BodyPoseSpec)
    object_geometry: ObjectGeometrySpec = field(default_factory=ObjectGeometrySpec)
    attachment: AttachmentSpec = field(default_factory=AttachmentSpec)
    occlusion_depth: OcclusionDepthSpec = field(default_factory=OcclusionDepthSpec)
    references: ReferenceSpec = field(default_factory=ReferenceSpec)
    conditioning: ConditioningSpec = field(default_factory=ConditioningSpec)
    model_execution: ModelExecutionSpec = field(default_factory=ModelExecutionSpec)
    repair: RepairSpec = field(default_factory=RepairSpec)
    validation: ValidationSpec = field(default_factory=ValidationSpec)
    run: RunConfig = field(default_factory=RunConfig)


# --------------------------------------------------------------------------- #
# Serialization + hashing
# --------------------------------------------------------------------------- #


def generation_spec_sha256(spec: GenerationSpec) -> str:
    """Authoritative whole-spec digest: sha256 of canonical serialization."""
    return hashlib.sha256(
        canonical_serialize_obj(_to_jsonable(spec)).encode("utf-8")
    ).hexdigest()


def conditioning_sha256(spec: GenerationSpec) -> str:
    """Reuse gate6a spec_sha256 on the embedded conditioning dimension."""
    return spec_sha256(spec.conditioning)


def model_run_sha256(spec: GenerationSpec) -> str:
    """Reuse gate6a run_sha256 on the embedded run dimension."""
    return run_sha256(spec.run)


# --------------------------------------------------------------------------- #
# Fail-closed validation
# --------------------------------------------------------------------------- #


class GenerationSpecValidationError(Exception):
    """Raised (fail-closed) when a GenerationSpec violates an invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenerationSpecValidationError(message)


def validate_generation_spec(spec: GenerationSpec) -> None:
    """Fail-closed validation. Raises GenerationSpecValidationError on the first
    violated invariant. Invariants map directly to design section K.2."""
    # Schema version parses as major.minor.
    _require(
        _is_semantic_version(spec.spec_version),
        f"spec_version must be 'major.minor': got {spec.spec_version!r}",
    )

    # STYLE: pipeline must be one of the allowed values.
    _require(
        spec.style.pipeline in ALLOWED_PIPELINES,
        f"style.pipeline must be in {ALLOWED_PIPELINES}: got {spec.style.pipeline!r}",
    )

    # CONDITIONING state must be a known state.
    _require(
        spec.conditioning.object_state in ALLOWED_STATES,
        f"conditioning.object_state must be in {ALLOWED_STATES}: "
        f"got {spec.conditioning.object_state!r}",
    )

    # ATTACHMENT SEMANTICS: when object state is sheathed, attachment evidence
    # MUST be present (fail-closed; see design K.1 / P.1).
    if spec.conditioning.object_state == "sheathed":
        _require(
            spec.attachment.attachment_type != "",
            "attachment.attachment_type required when object_state='sheathed'",
        )
        _require(
            len(spec.attachment.required_visible_evidence) > 0,
            "attachment.required_visible_evidence required when object_state='sheathed'",
        )

    # REFERENCES / PROVENANCE: any declared reference or model asset must carry
    # a SHA-256 (fail-closed; no asset participates without a verifiable hash).
    for rb in spec.identity.reference_bindings:
        if rb.asset_path != "":
            _require(
                rb.asset_sha256 != "",
                f"identity reference binding for {rb.asset_path!r} missing asset_sha256",
            )
    all_refs = (
        list(spec.references.character_refs)
        + list(spec.references.object_refs)
        + list(spec.references.environment_refs)
        + list(spec.references.style_refs)
    )
    for rb in all_refs:
        if rb.asset_path != "":
            _require(
                rb.asset_sha256 != "",
                f"reference binding for {rb.asset_path!r} missing asset_sha256",
            )
    _require(
        spec.model_execution.checkpoint_hash != "",
        "model_execution.checkpoint_hash required (must carry SHA)",
    )
    for lora in spec.model_execution.loras:
        _require(
            lora.hash != "",
            f"lora {lora.name!r} missing hash",
        )


def _is_semantic_version(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 2:
        return False
    return all(p.isdigit() for p in parts)


# --------------------------------------------------------------------------- #
# Whole-spec semantic diff (generic; complements gate6a's conditioning diff)
# --------------------------------------------------------------------------- #


_MISSING = object()


def _to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _join(prefix: str, key: str) -> str:
    return key if not prefix else f"{prefix}.{key}"


def _collect_diff(control: Any, test: Any, prefix: str, changed: List[str], details: Dict[str, Any]) -> None:
    if isinstance(control, dict) and isinstance(test, dict):
        for k in set(control.keys()) | set(test.keys()):
            _collect_diff(control.get(k, _MISSING), test.get(k, _MISSING), _join(prefix, str(k)), changed, details)
    elif isinstance(control, list) and isinstance(test, list):
        if len(control) != len(test):
            changed.append(prefix)
            details[prefix] = {"control": control, "test": test}
        else:
            for i, (c, t) in enumerate(zip(control, test)):
                _collect_diff(c, t, _join(prefix, str(i)), changed, details)
    elif control != test:
        changed.append(prefix)
        details[prefix] = {"control": control, "test": test}


def diff_generation_spec(control: GenerationSpec, test: GenerationSpec) -> Dict[str, Any]:
    """Field-level semantic diff of the whole GenerationSpec (dotted paths)."""
    changed: List[str] = []
    details: Dict[str, Any] = {}
    _collect_diff(_to_jsonable(control), _to_jsonable(test), "", changed, details)
    return {"changed": changed, "details": details}


def assert_single_changed_generation_dimension(
    control: GenerationSpec,
    test: GenerationSpec,
    allowed_dimension: str,
) -> bool:
    """Fail-closed whole-spec causal-isolation assertion."""
    diff = diff_generation_spec(control, test)
    changed = set(diff["changed"])
    if allowed_dimension not in changed:
        raise CausalIsolationError(
            f"authorized dimension {allowed_dimension!r} did not change; "
            f"changed={sorted(changed)}"
        )
    if changed != {allowed_dimension}:
        raise CausalIsolationError(
            f"causal isolation violated: expected exactly {allowed_dimension!r}, "
            f"but changed={sorted(changed)}"
        )
    return True


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #


def build_generation_spec_provenance(spec: GenerationSpec) -> Dict[str, Any]:
    """Compose provenance hashes across the GenerationSpec contract."""
    full_hash = generation_spec_sha256(spec)
    cond_hash = conditioning_sha256(spec)
    run_hash = model_run_sha256(spec)
    return {
        "spec_version": spec.spec_version,
        "generation_spec_sha256": full_hash,
        "conditioning_sha256": cond_hash,
        "run_sha256": run_hash,
        "pipeline": spec.style.pipeline,
        "object_state": spec.conditioning.object_state,
        "checkpoint_hash": spec.model_execution.checkpoint_hash,
        "seed": spec.model_execution.seed,
        "m1_reuse_source": M1_REUSE_SOURCE,
        "m1_reuse_source_sha256": M1_REUSE_SOURCE_SHA256,
    }


def render_generation_spec(spec: GenerationSpec) -> RenderedConditioning:
    """Reuse gate6a's deterministic render boundary on the embedded spec/run."""
    return render_conditioning(spec.conditioning, spec.run)
