"""Gate 6A Arm B structured conditioning representation (R2 implementation).

This module implements the STRUCTURED_CONDITIONING_REDESIGN machinery only. It
does NOT run GPU inference, does NOT select any production conditioning policy,
and does NOT change model execution. It provides:

- ConditioningSpec / RunConfig: explicit, typed, independently addressable
  material conditioning dimensions (replacing the implicit flatten-to-prompt path).
- render_conditioning(spec, run): a single deterministic boundary that resolves
  the structured spec into the exact model-facing inputs (descriptors).
- canonical_serialize / spec_sha256 / run_sha256: stable, hashable serialization.
- build_provenance: field-level provenance hashes for every derived artifact.
- diff_conditioning_specs: machine-readable semantic field-level diff.
- assert_single_changed_dimension: fail-closed causal-isolation validator.
- from_canonical_fixture: narrow adapter from canonical 72 manifest entries.

The "exact inputs consumed by the model" are produced as deterministic DESCRIPTORS
(the prompt strings, init-image descriptor, mask descriptor, and inpaint kwargs).
Actual pixel compositing / SDXL invocation remains in the (untouched) generator;
this module is the experimental control system, not the experiment.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

FROZEN_GENERATOR_UNCHANGED = True
GPU_INFERENCE_PERFORMED = False

# --------------------------------------------------------------------------- #
# Typed material-conditioning dimensions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlacementSpec:
    """Geometric placement / anchor conditioning.

    anchor_enforced / regions_enforced default to False to PRESERVE legacy
    behavior (the frozen derive_placement ignores anchor/region constraints for
    full-canvas assets). They are explicit, independently switchable capabilities.
    """

    anchor_point: Optional[Tuple[float, float]] = None
    allowed_overlap_regions: Optional[List[List[float]]] = None
    forbidden_regions: Optional[List[List[float]]] = None
    scale_policy: str = "asset_native"  # asset_native | fit_to_allowed_region | explicit_px
    placement_policy: str = "anchor_centered"  # matches frozen derive_placement
    anchor_enforced: bool = False
    regions_enforced: bool = False


@dataclass(frozen=True)
class MaskSpec:
    """Mask / geometry conditioning (descriptor only; pixel math is downstream)."""

    policy: str = "placement_ellipse"  # matches frozen build_mask_from_placement
    blur_px: int = 0
    dilation_px: int = 0


@dataclass(frozen=True)
class EnvironmentSpec:
    """Background / scene conditioning capability.

    neutral_background defaults to False (legacy uses the scene base). It is a
    capability, NOT a selected scientific default.
    """

    base_source: Optional[str] = None
    neutral_background: bool = False


@dataclass(frozen=True)
class ReferenceBindingSpec:
    """Reference object binding.

    For canonical 72 entries the weapon asset path/sha is supplied out-of-band by
    the generator (CLI), not stored in the manifest; we model that honestly as
    None rather than manufacturing a binding.
    """

    asset_path: Optional[str] = None
    asset_sha256: Optional[str] = None
    preserve_reference: bool = True


@dataclass(frozen=True)
class SourceBindingSpec:
    """Source scene binding (the base image the object is composited onto)."""

    source_asset: Optional[str] = None
    source_sha256: Optional[str] = None


@dataclass(frozen=True)
class PreservationConstraints:
    """Mechanical invariants that must hold before CLIP is considered."""

    requested_object_present: bool = True
    correct_object_class_state: bool = True
    no_catastrophic_crop: bool = True
    reference_binding_intact: bool = True


@dataclass(frozen=True)
class RunConfig:
    """Model / run configuration. A material dimension set per the redesign."""

    strength: float = 1.0
    guidance_scale: float = 7.5
    num_inference_steps: int = 20
    scheduler: str = "EulerDiscreteScheduler"
    model: str = "SDXL_BASE"
    lora: str = "sd_xl_offset_example-lora_1.0"
    seed: int = 1_000_003
    resolution: Tuple[int, int] = (1024, 1024)


@dataclass(frozen=True)
class ConditioningSpec:
    """Explicit, structured Arm B conditioning specification.

    Every field is independently addressable. A change to one field must not
    implicitly rewrite unrelated fields (except deterministic, surfaced derived
    artifacts, which are recorded in provenance, not in the semantic spec).
    """

    object_class: str = ""
    object_state: str = ""  # drawn | sheathed | prop
    object_identity: str = ""  # e.g. "carved jade talisman"
    viewpoint: str = ""
    distance: str = ""
    pose: str = ""
    lighting: str = ""
    background_complexity: str = ""
    occlusion: str = ""
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    negative_constraints: Tuple[str, ...] = ()
    placement: PlacementSpec = field(default_factory=PlacementSpec)
    mask_geometry: MaskSpec = field(default_factory=MaskSpec)
    reference_binding: ReferenceBindingSpec = field(default_factory=ReferenceBindingSpec)
    source_binding: SourceBindingSpec = field(default_factory=SourceBindingSpec)
    preservation_constraints: PreservationConstraints = field(
        default_factory=PreservationConstraints
    )

    # Prompt-relevant (semantic) fields, in canonical order, used to render the
    # positive prompt. Changing any of these legitimately changes rendered prompt
    # bytes (a DERIVED artifact), which the causal validator explicitly permits.
    PROMPT_FIELDS = (
        "object_identity",
        "viewpoint",
        "distance",
        "lighting",
        "background_complexity",
        "occlusion",
        "pose",
    )


# --------------------------------------------------------------------------- #
# Rendered (derived) conditioning payload
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RenderedConditioning:
    positive_prompt: str
    negative_prompt: str
    init_image_descriptor: Dict[str, Any]
    mask_descriptor: Dict[str, Any]
    inpaint_kwargs: Dict[str, Any]


# --------------------------------------------------------------------------- #
# Deterministic render boundary
# --------------------------------------------------------------------------- #

_FIXED_PROMPT_SUFFIX = (
    "fully visible no crop, minimal background, no wide shot, "
    "no contact/reference/model sheet, turnaround, multi-angle or split panel"
)


def _render_positive_prompt(spec: ConditioningSpec) -> str:
    """Deterministically render the positive prompt.

    For a migrated canonical fixture this reproduces the frozen build_prompt
    output exactly (behavior-preserving), because all prompt-relevant fields map
    1:1 from the manifest entry.
    """
    return (
        f"single subject, object-centric, exactly one {spec.object_identity}, "
        f"{spec.viewpoint}, {spec.distance}, {spec.lighting}, "
        f"{spec.background_complexity}, {spec.occlusion}, {spec.pose}, "
        f"{_FIXED_PROMPT_SUFFIX}"
    )


def render_conditioning(spec: ConditioningSpec, run: RunConfig) -> RenderedConditioning:
    """Resolve a ConditioningSpec + RunConfig into exact model-facing inputs.

    Deterministic, canonical, inspectable, reproducible, provenance-recorded.
    Returns DESCRIPTORS of the inputs (no GPU, no PIL, no model call).
    """
    positive = _render_positive_prompt(spec)
    negative = ", ".join(spec.negative_constraints) if spec.negative_constraints else ""

    init_image_descriptor = {
        "base_source": spec.source_binding.source_asset,
        "neutral_background": spec.environment.neutral_background,
        "reference_asset": spec.reference_binding.asset_path,
        "preserve_reference": spec.reference_binding.preserve_reference,
        "scale_policy": spec.placement.scale_policy,
        "placement_policy": spec.placement.placement_policy,
        "anchor_point": list(spec.placement.anchor_point)
        if spec.placement.anchor_point is not None
        else None,
        "anchor_enforced": spec.placement.anchor_enforced,
        "regions_enforced": spec.placement.regions_enforced,
        "allowed_overlap_regions": spec.placement.allowed_overlap_regions,
        "forbidden_regions": spec.placement.forbidden_regions,
    }

    mask_descriptor = {
        "policy": spec.mask_geometry.policy,
        "blur_px": spec.mask_geometry.blur_px,
        "dilation_px": spec.mask_geometry.dilation_px,
    }

    inpaint_kwargs = {
        "prompt": positive,
        "negative_prompt": negative,
        "strength": run.strength,
        "guidance_scale": run.guidance_scale,
        "num_inference_steps": run.num_inference_steps,
        "scheduler": run.scheduler,
        "model": run.model,
        "lora": run.lora,
        "seed": run.seed,
        "resolution": list(run.resolution),
    }

    return RenderedConditioning(
        positive_prompt=positive,
        negative_prompt=negative,
        init_image_descriptor=init_image_descriptor,
        mask_descriptor=mask_descriptor,
        inpaint_kwargs=inpaint_kwargs,
    )


# --------------------------------------------------------------------------- #
# Canonical serialization + hashing
# --------------------------------------------------------------------------- #


def _to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def canonical_serialize(spec: ConditioningSpec) -> str:
    """Deterministic canonical serialization of the semantic spec.

    Key ordering is sorted; tuples/lists normalized; identical semantic specs
    serialize identically. Does NOT include RunConfig (see spec_sha256 design).
    """
    return json.dumps(_to_jsonable(spec), sort_keys=True, separators=(",", ":"))


def canonical_serialize_obj(obj: Any) -> str:
    """Deterministic canonical serialization for arbitrary derived artifacts."""
    return json.dumps(_to_jsonable(obj), sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_sha256(spec: ConditioningSpec) -> str:
    """Stable semantic-spec digest. Independent of RunConfig / runtime noise."""
    return _sha256_text(canonical_serialize(spec))


def run_sha256(run: RunConfig) -> str:
    """Stable run-config digest."""
    return _sha256_text(canonical_serialize_obj(_to_jsonable(run)))


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #


def build_provenance(
    spec: ConditioningSpec, run: RunConfig, rendered: RenderedConditioning
) -> Dict[str, Any]:
    """Field-level provenance: hashes for unresolved spec, run config, and every
    derived artifact. Records derived changes explicitly (does not hash only the
    final prompt)."""
    spec_hash = spec_sha256(spec)
    run_hash = run_sha256(run)
    pos_hash = _sha256_text(rendered.positive_prompt)
    neg_hash = _sha256_text(rendered.negative_prompt)
    init_hash = _sha256_text(canonical_serialize_obj(rendered.init_image_descriptor))
    mask_hash = _sha256_text(canonical_serialize_obj(rendered.mask_descriptor))
    kw_hash = _sha256_text(canonical_serialize_obj(rendered.inpaint_kwargs))
    resolved = _sha256_text(
        spec_hash + run_hash + pos_hash + neg_hash + init_hash + mask_hash + kw_hash
    )
    return {
        "unresolved_spec_sha256": spec_hash,
        "run_config_sha256": run_hash,
        "rendered_positive_prompt_sha256": pos_hash,
        "rendered_negative_prompt_sha256": neg_hash,
        "init_image_descriptor_sha256": init_hash,
        "mask_descriptor_sha256": mask_hash,
        "inpaint_kwargs_sha256": kw_hash,
        "resolved_conditioning_signature_sha256": resolved,
        "object_class": spec.object_class,
        "object_state": spec.object_state,
        "source_sha256": spec.source_binding.source_sha256,
        "reference_sha256": spec.reference_binding.asset_sha256,
    }


# --------------------------------------------------------------------------- #
# Semantic diff + causal-isolation validator
# --------------------------------------------------------------------------- #


class CausalIsolationError(Exception):
    """Raised (fail-closed) when a causal test is not single-dimension isolated."""


_MISSING = object()


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


def diff_conditioning_specs(
    control: ConditioningSpec,
    test: ConditioningSpec,
    control_run: Optional[RunConfig] = None,
    test_run: Optional[RunConfig] = None,
) -> Dict[str, Any]:
    """Machine-readable field-level semantic diff.

    Compares SEMANTIC spec fields (and optional run-config fields) only. It does
    NOT diff rendered prompt/config bytes; those are derived artifacts recorded
    in provenance. Returns dotted paths of every changed dimension.
    """
    changed: List[str] = []
    details: Dict[str, Any] = {}
    _collect_diff(_to_jsonable(control), _to_jsonable(test), "", changed, details)
    if control_run is not None and test_run is not None:
        _collect_diff(_to_jsonable(control_run), _to_jsonable(test_run), "run", changed, details)
    return {"changed": changed, "details": details}


def assert_single_changed_dimension(
    control: ConditioningSpec,
    test: ConditioningSpec,
    allowed_dimension: str,
    control_run: Optional[RunConfig] = None,
    test_run: Optional[RunConfig] = None,
) -> bool:
    """Fail-closed causal-isolation assertion.

    Exactly one material dimension must differ, and it must be the authorized
    one. Raises CausalIsolationError otherwise (never merely warns).
    """
    diff = diff_conditioning_specs(control, test, control_run, test_run)
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
# Migration adapter (canonical 72 manifest -> ConditioningSpec)
# --------------------------------------------------------------------------- #

_STATE_BY_CLASS = {
    "sheathed_sword": "sheathed",
    "drawn_sword": "drawn",
    "non_weapon_prop": "prop",
}


def from_canonical_fixture(entry: Dict[str, Any]) -> Tuple[ConditioningSpec, RunConfig]:
    """Narrow adapter: map a canonical 72 manifest entry to (spec, run).

    Preserves all conditioning metadata present in the manifest; does not
    manufacture semantics that are absent (e.g. reference asset binding is left
    None because the manifest does not carry it).
    """
    oc = entry.get("object_class", "")
    anchor = entry.get("anchor")
    placement_kwargs: Dict[str, Any] = {}
    if isinstance(anchor, dict):
        ap = anchor.get("anchor_point")
        placement_kwargs["anchor_point"] = tuple(ap) if isinstance(ap, (list, tuple)) else None
        placement_kwargs["allowed_overlap_regions"] = anchor.get("allowed_overlap_regions")
        placement_kwargs["forbidden_regions"] = anchor.get("forbidden_regions")
    placement = PlacementSpec(**placement_kwargs)

    run = RunConfig(seed=int(entry.get("seed", RunConfig.seed)))

    spec = ConditioningSpec(
        object_class=oc,
        object_state=_STATE_BY_CLASS.get(oc, ""),
        object_identity=entry.get("target_identity", ""),
        viewpoint=entry.get("viewpoint", ""),
        distance=entry.get("distance", ""),
        pose=entry.get("pose", ""),
        lighting=entry.get("lighting", ""),
        background_complexity=entry.get("background_complexity", ""),
        occlusion=entry.get("occlusion", ""),
        environment=EnvironmentSpec(base_source=entry.get("source_asset")),
        placement=placement,
        source_binding=SourceBindingSpec(
            source_asset=entry.get("source_asset"),
            source_sha256=entry.get("source_sha256"),
        ),
    )
    return spec, run
