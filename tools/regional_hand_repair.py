"""Bounded post-generation REGIONAL HAND REPAIR stage (CPU-first, opt-in, fail-closed).

Architecture (previously qualified by the EN Regional Hand-Repair Architecture Audit):

    primary SDXL generation (UNCHANGED)
        -> VAEDecode / decoded image retrieval
        -> [THIS MODULE] bounded regional hand/hilt repair
        -> final persistence / provenance / publication

Boundary selection (audit result B): the repair operates on the DECODED IMAGE
BEFORE persistence. It therefore never touches the primary KSampler graph, the
GenerationSpec, GenerationSpec hashing, the primary execution identity, the
Studio Bible adapter, the primary prompt builder, checkpoint/LoRA selection, the
primary seed, or the primary sampler settings.

What this module deliberately does NOT introduce:
  - no detector (no bbox/YOLO/SAM/Florence/hand detector)
  - no segmentation model
  - no Impact Pack / Detailer / FaceDetailer
  - no DWPose / MeshGraphormer
  - no FLUX / base-model swap
  - no face repair (architecturally independent; deferred)
  - no upscaling
  - no COMPOSITION_CONSTRAINT, no HAND_HILT_ISOLATION
  - no new ComfyUI custom node and no model download

Localization authority is the ALREADY SANCTIONED prescriptive OpenPose-21 hand
geometry produced by ``tools.spatial_guide`` (``en_sanctioned_hand_interaction_params``
-> ``derive_hand_keypoints``) plus the existing ``soulblade_contact`` /
``object_regions`` structural geometry. Nothing here retunes that geometry: this
module is a strict READ-ONLY CONSUMER of it.

OpenPose ControlNet is intentionally NOT added to the repair sampler, so the one
new causal factor of the first bounded GPU experiment is exactly:

    "one bounded regional SDXL inpaint repair pass"

Governance:
  - Every CPU artifact (request, region, mask, workflow, execution id,
    provenance) is constructible with NO GPU authority.
  - GPU authority is checked BEFORE any reservation, client construction, or
    submission, so an unauthorized call cannot poison the duplicate-submission
    lifecycle.
  - Absolutely nothing in this module constructs a ComfyUI client or submits a
    prompt; submission is performed only by an injected collaborator, and only
    when explicit GPU authority is present.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from tools.spatial_guide import (
    OPENPOSE_HAND_KEYPOINT_COUNT,
    HandKeypoints,
    Region,
    en_sanctioned_hand_interaction_params,
    is_en_sanctioned_hand_interaction,
)

# --------------------------------------------------------------------------- #
# Stage identity / governance constants
# --------------------------------------------------------------------------- #

REGIONAL_HAND_REPAIR_OWNER = "tools/regional_hand_repair.py"
REGIONAL_HAND_REPAIR_STAGE = "regional_hand_repair"
REGIONAL_HAND_REPAIR_VERSION = "regional_hand_repair_v1"

#: The repair stage is OPTIONAL and OFF by default. Nothing in the primary V2
#: path invokes it implicitly; a caller must construct a request explicitly.
REGIONAL_HAND_REPAIR_DEFAULT_ENABLED = False

#: The production three-state render gate is NOT activated by this module. The
#: classifier below is pure decision mechanics available to harnesses/tests.
PRODUCTION_RENDER_GATE_ACTIVATED = False

#: Face repair is architecturally independent and is NOT part of this stage.
FACE_REPAIR_INVOKED = False

#: OpenPose ControlNet is NOT used in the repair sampler (single-factor policy).
OPENPOSE_CONTROLNET_USED_IN_REPAIR = False
#: The sanctioned OpenPose hand guide IS used, for localization + provenance only.
OPENPOSE_GUIDE_ROLE = "localization"

#: Repair execution identities live in their own namespace so they can never
#: collide with primary ``v2exec-<profile>-<digest>`` identities.
REPAIR_EXECUTION_NAMESPACE = "v2repair-hand"

# Encode-architecture discriminator (G2). This is the ONLY causal factor that may
# differ between the CONTROL and TREATMENT encode paths. It is a stable, semantic,
# content-addressed field (no host paths, timestamps, or UUIDs) so the repair
# execution identity changes exactly and only when the encode architecture changes.
REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT = "vae_encode_for_inpaint"
REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK = (
    "vae_encode_set_latent_noise_mask"
)
REPAIR_ENCODE_ARCHITECTURE_VALUES = frozenset(
    {
        REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT,
        REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK,
    }
)


class RegionalHandRepairError(RuntimeError):
    """Base class for every fail-closed regional-hand-repair refusal."""


class RepairFindingsError(RegionalHandRepairError):
    """An unknown / contradictory visual-contract finding was supplied."""


class RepairRegionError(RegionalHandRepairError):
    """The derived repair region violates a hard geometric gate."""


class RepairIdentityError(RegionalHandRepairError):
    """A content-address (source / mask / hand guide) failed verification."""


class RepairEligibilityError(RegionalHandRepairError):
    """The render is not REPAIR_ELIGIBLE, so repair must not run."""


class RepairAssetError(RegionalHandRepairError):
    """An unknown checkpoint / LoRA reference was supplied."""


class RepairGpuAuthorityAbsent(RegionalHandRepairError):
    """GPU authority is absent, so no repair submission may occur."""


class RepairDuplicateSubmission(RegionalHandRepairError):
    """This repair execution identity is already reserved or submitted."""


class RepairImmutabilityViolation(RegionalHandRepairError):
    """Pixels changed outside the permitted composite region."""


class RepairSoulbladeViolation(RegionalHandRepairError):
    """Soulblade geometry changed outside the permitted contact subregion."""


class RepairCandidateContentError(RegionalHandRepairError):
    """A repair candidate carries no valid RGB image content (fail closed).

    Raised when the GPU-decoded candidate is structurally invalid: a uniform
    gray placeholder, a near-zero-variance canvas, a mask misrouted as the
    repair image, or dimension/mode/availability defects. Such a candidate must
    NEVER be promoted to the final composite or marked a successful repair.
    """


# --------------------------------------------------------------------------- #
# PHASE 3 - three-state render classifier (decision mechanics only)
# --------------------------------------------------------------------------- #
# Input is EXPLICIT visual-contract / mechanical findings supplied by a reviewer
# or a mechanical evaluator. There is deliberately no hidden model judgment and
# no image inspection here: the classifier is a pure, deterministic function of
# declared finding tokens.

RENDER_STATE_PASS = "PASS"
RENDER_STATE_REPAIR_ELIGIBLE = "REPAIR_ELIGIBLE"
RENDER_STATE_FAIL = "FAIL"

RENDER_STATES: Tuple[str, ...] = (
    RENDER_STATE_PASS,
    RENDER_STATE_REPAIR_ELIGIBLE,
    RENDER_STATE_FAIL,
)

#: BASE_GENERATION_FATAL: a render carrying ANY of these can never be promoted
#: to repair eligibility, because a bounded local inpaint cannot reconstruct
#: global composition, identity, scene, or object presence.
BASE_GENERATION_FATAL_FINDINGS: frozenset = frozenset(
    {
        "composition_escape",
        "missing_kael",
        "wrong_kael",
        "missing_soulblade",
        "wrong_soulblade",
        "missing_gripping_hand",
        "grossly_wrong_pose",
        "wrong_scene",
        "canon_contamination",
    }
)

#: REPAIR_ELIGIBLE: bounded LOCAL defects only, confined to the hand/hilt
#: neighbourhood that the derived repair region encloses.
REPAIR_ELIGIBLE_FINDINGS: frozenset = frozenset(
    {
        "fused_fingers",
        "extra_fingers",
        "missing_fingers",
        "local_finger_deformation",
        "local_palm_deformation",
        "local_wrist_deformation",
        "local_hand_object_fusion",
        "bounded_hand_hilt_contact_defect",
    }
)

_KNOWN_FINDINGS: frozenset = BASE_GENERATION_FATAL_FINDINGS | REPAIR_ELIGIBLE_FINDINGS


@dataclass(frozen=True)
class VisualContractFindings:
    """Explicit, declared visual-contract findings for ONE rendered image.

    ``fatal`` and ``local`` are separate only for authoring clarity; the
    classifier unions them and re-derives severity from the canonical finding
    sets, so mislabelling a fatal defect as "local" cannot promote a render.
    """

    fatal: Tuple[str, ...] = ()
    local: Tuple[str, ...] = ()

    def tokens(self) -> Tuple[str, ...]:
        return tuple(self.fatal) + tuple(self.local)


def classify_render_findings(findings: Any) -> str:
    """Return PASS / REPAIR_ELIGIBLE / FAIL from explicit findings (fail closed).

    Rules (in order):
      1. an unknown finding token raises ``RepairFindingsError`` - it is NEVER
         silently downgraded to PASS and never silently treated as repairable;
      2. any token in ``BASE_GENERATION_FATAL_FINDINGS`` -> FAIL, regardless of
         how many repairable defects accompany it (fatal takes precedence);
      3. any token in ``REPAIR_ELIGIBLE_FINDINGS`` -> REPAIR_ELIGIBLE;
      4. no findings at all -> PASS.
    """
    if isinstance(findings, VisualContractFindings):
        tokens = findings.tokens()
    elif isinstance(findings, (list, tuple, set, frozenset)):
        tokens = tuple(findings)
    else:
        raise RepairFindingsError(
            f"findings must be VisualContractFindings or a token sequence, got "
            f"{type(findings).__name__}"
        )

    normalized: List[str] = []
    for raw in tokens:
        if not isinstance(raw, str):
            raise RepairFindingsError(
                f"visual-contract finding must be a string token, got "
                f"{type(raw).__name__}: {raw!r}"
            )
        token = raw.strip().lower()
        if token == "":
            raise RepairFindingsError(
                "empty visual-contract finding token is not permitted (fail closed)"
            )
        if token not in _KNOWN_FINDINGS:
            raise RepairFindingsError(
                f"unknown visual-contract finding {raw!r}: it is neither a declared "
                f"BASE_GENERATION_FATAL finding {sorted(BASE_GENERATION_FATAL_FINDINGS)} "
                f"nor a declared REPAIR_ELIGIBLE finding "
                f"{sorted(REPAIR_ELIGIBLE_FINDINGS)}; refusing to classify (an "
                f"unrecognized defect must never be downgraded to PASS or promoted "
                f"to repair eligibility)"
            )
        normalized.append(token)

    if any(t in BASE_GENERATION_FATAL_FINDINGS for t in normalized):
        return RENDER_STATE_FAIL
    if any(t in REPAIR_ELIGIBLE_FINDINGS for t in normalized):
        return RENDER_STATE_REPAIR_ELIGIBLE
    return RENDER_STATE_PASS


# --------------------------------------------------------------------------- #
# PHASE 4 - bounded repair-region derivation (no detector)
# --------------------------------------------------------------------------- #
# The region is derived ONLY from geometry that already exists and is already
# qualified:
#   - the sanctioned OpenPose-21 grip hand keypoints (HandKeypoints),
#   - the existing ``soulblade_contact`` contact/hilt Region,
#   - the existing Soulblade ``object_regions`` blade Region (used as a clamp
#     authority so most of the blade is excluded),
#   - the existing subject Region (used as a clamp authority so background is
#     excluded).
# No image is inspected, so no detector or segmentation model is required.

REPAIR_REGION_LABEL = "regional_hand_repair"

#: Fixed deterministic padding (normalized units) added around the union of the
#: hand keypoint bbox and the contact/hilt rect. Not tunable per-call: a caller
#: cannot silently widen the repair blast radius.
REPAIR_REGION_PADDING = 0.02

#: Hard numeric gates. Exceeding any of these FAILS CLOSED.
REPAIR_REGION_MAX_AREA_FRACTION = 0.070      # of the whole image
REPAIR_REGION_MAX_WIDTH_FRACTION = 0.30      # of the whole image width
REPAIR_REGION_MAX_HEIGHT_FRACTION = 0.34     # of the whole image height
REPAIR_REGION_MAX_TORSO_COVERAGE = 0.50      # of the subject region's area
REPAIR_REGION_MAX_SOULBLADE_COVERAGE = 0.50  # of the blade region's area
REPAIR_REGION_MIN_HAND_OVERLAP = 0.50        # of the hand keypoint bbox area
REPAIR_REGION_MIN_CONTACT_OVERLAP = 0.90     # of the contact/hilt rect area

#: Protected face zone (LAYOUT CONVENTION, deterministic). The neutral/wielding
#: OpenPose presets place nose y=0.12, ears y=0.11, neck y=0.18, so a face band
#: ending at y=0.26 conservatively covers head + jaw + neck transition. The
#: repair region must lie entirely BELOW it.
FACE_PROTECTED_REGION = Region("face_protected", "rect", 0.30, 0.00, 0.40, 0.26, zone="face")
FACE_PROTECTED_BOTTOM = FACE_PROTECTED_REGION.y + FACE_PROTECTED_REGION.h


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _rect_of(region: Region) -> Tuple[float, float, float, float]:
    return (float(region.x), float(region.y), float(region.w), float(region.h))


def _intersect_area(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ox = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    oy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return ox * oy


def _area(r: Tuple[float, float, float, float]) -> float:
    return float(r[2]) * float(r[3])


@dataclass(frozen=True)
class HandRepairRegion:
    """Deterministic, content-addressed bounded repair region (normalized).

    Identity is derived ONLY from geometry + the localization authority hashes.
    No host path, no output directory, and no absolute filename participates, so
    the same geometry produces the same identity on every host.
    """

    label: str
    x: float
    y: float
    w: float
    h: float
    padding: float
    image_width: int
    image_height: int
    hand_bbox: Tuple[float, float, float, float]
    contact_rect: Tuple[float, float, float, float]
    blade_rect: Tuple[float, float, float, float]
    subject_rect: Tuple[float, float, float, float]
    hand_keypoints_sha256: str = ""
    hand_guide_sha256: str = ""

    # -- measurable metrics (all mechanical, no prose) --------------------- #

    def rect(self) -> Tuple[float, float, float, float]:
        return (float(self.x), float(self.y), float(self.w), float(self.h))

    def area_fraction(self) -> float:
        return _area(self.rect())

    def hand_overlap_fraction(self) -> float:
        a = _area(self.hand_bbox)
        return 0.0 if a <= 0.0 else _intersect_area(self.rect(), self.hand_bbox) / a

    def contact_overlap_fraction(self) -> float:
        a = _area(self.contact_rect)
        return 0.0 if a <= 0.0 else _intersect_area(self.rect(), self.contact_rect) / a

    def soulblade_overlap_fraction(self) -> float:
        a = _area(self.blade_rect)
        return 0.0 if a <= 0.0 else _intersect_area(self.rect(), self.blade_rect) / a

    def torso_coverage_fraction(self) -> float:
        a = _area(self.subject_rect)
        return 0.0 if a <= 0.0 else _intersect_area(self.rect(), self.subject_rect) / a

    def face_overlap_fraction(self) -> float:
        face = _rect_of(FACE_PROTECTED_REGION)
        a = _area(face)
        return 0.0 if a <= 0.0 else _intersect_area(self.rect(), face) / a

    def pixel_box(self) -> Tuple[int, int, int, int]:
        """Deterministic integer pixel box (x0, y0, x1, y1), half-open on x1/y1."""
        w, h = int(self.image_width), int(self.image_height)
        x0 = int(round(self.x * w))
        y0 = int(round(self.y * h))
        x1 = int(round((self.x + self.w) * w))
        y1 = int(round((self.y + self.h) * h))
        x0 = max(0, min(w, x0))
        y0 = max(0, min(h, y0))
        x1 = max(x0, min(w, x1))
        y1 = max(y0, min(h, y1))
        return (x0, y0, x1, y1)

    # -- identity ---------------------------------------------------------- #

    def identity_payload(self) -> Dict[str, Any]:
        """Host-independent identity payload (NO paths, NO output dirs)."""
        return {
            "stage": REGIONAL_HAND_REPAIR_STAGE,
            "version": REGIONAL_HAND_REPAIR_VERSION,
            "label": self.label,
            "rect": [round(v, 8) for v in self.rect()],
            "padding": round(float(self.padding), 8),
            "image_width": int(self.image_width),
            "image_height": int(self.image_height),
            "hand_bbox": [round(v, 8) for v in self.hand_bbox],
            "contact_rect": [round(v, 8) for v in self.contact_rect],
            "blade_rect": [round(v, 8) for v in self.blade_rect],
            "subject_rect": [round(v, 8) for v in self.subject_rect],
            "hand_keypoints_sha256": self.hand_keypoints_sha256,
            "hand_guide_sha256": self.hand_guide_sha256,
        }

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.identity_payload(), sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()

    def to_json(self) -> Dict[str, Any]:
        payload = self.identity_payload()
        payload.update(
            {
                "repair_region_sha256": self.sha256(),
                "pixel_box": list(self.pixel_box()),
                "area_fraction": round(self.area_fraction(), 8),
                "hand_overlap_fraction": round(self.hand_overlap_fraction(), 8),
                "contact_overlap_fraction": round(self.contact_overlap_fraction(), 8),
                "soulblade_overlap_fraction": round(self.soulblade_overlap_fraction(), 8),
                "torso_coverage_fraction": round(self.torso_coverage_fraction(), 8),
                "face_overlap_fraction": round(self.face_overlap_fraction(), 8),
            }
        )
        return payload


def hand_keypoints_sha256(hand: HandKeypoints) -> str:
    """Content address of the sanctioned OpenPose-21 hand geometry (read-only)."""
    payload = {
        "side": hand.side,
        "anchor_label": hand.anchor_label,
        "anchor_geometry": [round(v, 8) for v in hand.anchor_geometry],
        "hand_span": round(float(hand.hand_span), 8),
        "finger_wrap": round(float(hand.finger_wrap), 8),
        "keypoints": [[round(x, 8), round(y, 8)] for (x, y) in hand.keypoints],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _hand_bbox(hand: HandKeypoints) -> Tuple[float, float, float, float]:
    xs = [float(x) for (x, _y) in hand.keypoints]
    ys = [float(y) for (_x, y) in hand.keypoints]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return (x0, y0, x1 - x0, y1 - y0)


def derive_hand_repair_region(
    hand: HandKeypoints,
    contact: Region,
    *,
    subject: Region,
    blade: Region,
    image_width: int,
    image_height: int,
    padding: float = REPAIR_REGION_PADDING,
    hand_guide_sha256: str = "",
) -> HandRepairRegion:
    """Derive the bounded hand/hilt repair region deterministically (FAIL CLOSED).

    Construction (no detector, no image inspection):
      1. bbox of the 21 sanctioned OpenPose hand keypoints,
      2. union with the existing ``soulblade_contact`` rect (guarantees the hilt
         / contact junction is inside the region),
      3. fixed deterministic padding,
      4. clamp to the subject rect (excludes background),
      5. clamp to image bounds,
      6. hard gates: below the protected face band, bounded area/width/height,
         bounded torso coverage, bounded Soulblade coverage, minimum hand and
         contact overlap.

    Any violated gate raises ``RepairRegionError`` rather than silently shrinking
    or widening the blast radius.
    """
    if len(hand.keypoints) != OPENPOSE_HAND_KEYPOINT_COUNT:
        raise RepairRegionError(
            f"repair region requires the sanctioned {OPENPOSE_HAND_KEYPOINT_COUNT}-keypoint "
            f"OpenPose hand geometry, got {len(hand.keypoints)} keypoints"
        )
    if int(image_width) <= 0 or int(image_height) <= 0:
        raise RepairRegionError(
            f"repair region requires positive image dimensions, got "
            f"{image_width}x{image_height}"
        )
    if float(padding) < 0.0:
        raise RepairRegionError(f"repair region padding must be >= 0, got {padding!r}")

    hb = _hand_bbox(hand)
    cr = _rect_of(contact)
    sr = _rect_of(subject)
    br = _rect_of(blade)

    if _area(cr) <= 0.0:
        raise RepairRegionError(
            "repair region requires a non-degenerate Soulblade contact/hilt region; "
            "the required contact geometry is missing"
        )
    if _area(sr) <= 0.0:
        raise RepairRegionError(
            "repair region requires a non-degenerate subject region as the "
            "background-exclusion clamp authority"
        )

    # 1+2. union(hand bbox, contact rect)
    x0 = min(hb[0], cr[0])
    y0 = min(hb[1], cr[1])
    x1 = max(hb[0] + hb[2], cr[0] + cr[2])
    y1 = max(hb[1] + hb[3], cr[1] + cr[3])

    # 3. fixed deterministic padding
    pad = float(padding)
    x0 -= pad
    y0 -= pad
    x1 += pad
    y1 += pad

    # 4. clamp to the subject rect -> background is excluded by construction
    x0 = max(x0, sr[0])
    y0 = max(y0, sr[1])
    x1 = min(x1, sr[0] + sr[2])
    y1 = min(y1, sr[1] + sr[3])

    # 5. clamp to image bounds
    x0, y0 = _clamp01(x0), _clamp01(y0)
    x1, y1 = _clamp01(x1), _clamp01(y1)
    if not (x1 > x0 and y1 > y0):
        raise RepairRegionError(
            f"derived repair region is degenerate after clamping: "
            f"x=[{x0},{x1}] y=[{y0},{y1}]"
        )

    region = HandRepairRegion(
        label=REPAIR_REGION_LABEL,
        x=x0,
        y=y0,
        w=x1 - x0,
        h=y1 - y0,
        padding=pad,
        image_width=int(image_width),
        image_height=int(image_height),
        hand_bbox=hb,
        contact_rect=cr,
        blade_rect=br,
        subject_rect=sr,
        hand_keypoints_sha256=hand_keypoints_sha256(hand),
        hand_guide_sha256=str(hand_guide_sha256 or ""),
    )
    assert_repair_region_within_gates(region)
    return region


def assert_repair_region_within_gates(region: HandRepairRegion) -> None:
    """Enforce every hard numeric repair-region gate (FAIL CLOSED)."""
    rx, ry, rw, rh = region.rect()

    if rx < 0.0 or ry < 0.0 or rx + rw > 1.0 + 1e-9 or ry + rh > 1.0 + 1e-9:
        raise RepairRegionError(
            f"repair region out of image bounds: x={rx} y={ry} w={rw} h={rh}"
        )
    if ry < FACE_PROTECTED_BOTTOM:
        raise RepairRegionError(
            f"repair region top y={ry} intrudes into the protected face band "
            f"(must be >= {FACE_PROTECTED_BOTTOM}); face repair is not part of "
            f"this stage"
        )
    if region.face_overlap_fraction() > 0.0:
        raise RepairRegionError(
            f"repair region overlaps the protected face region "
            f"(fraction={region.face_overlap_fraction()})"
        )
    if region.area_fraction() > REPAIR_REGION_MAX_AREA_FRACTION:
        raise RepairRegionError(
            f"repair region area fraction {region.area_fraction():.6f} exceeds "
            f"maximum {REPAIR_REGION_MAX_AREA_FRACTION}"
        )
    if rw > REPAIR_REGION_MAX_WIDTH_FRACTION:
        raise RepairRegionError(
            f"repair region width {rw:.6f} exceeds maximum "
            f"{REPAIR_REGION_MAX_WIDTH_FRACTION}"
        )
    if rh > REPAIR_REGION_MAX_HEIGHT_FRACTION:
        raise RepairRegionError(
            f"repair region height {rh:.6f} exceeds maximum "
            f"{REPAIR_REGION_MAX_HEIGHT_FRACTION}"
        )
    if region.torso_coverage_fraction() > REPAIR_REGION_MAX_TORSO_COVERAGE:
        raise RepairRegionError(
            f"repair region covers {region.torso_coverage_fraction():.6f} of the "
            f"torso/subject region, exceeding {REPAIR_REGION_MAX_TORSO_COVERAGE}"
        )
    if region.soulblade_overlap_fraction() > REPAIR_REGION_MAX_SOULBLADE_COVERAGE:
        raise RepairRegionError(
            f"repair region covers {region.soulblade_overlap_fraction():.6f} of the "
            f"Soulblade region, exceeding {REPAIR_REGION_MAX_SOULBLADE_COVERAGE}"
        )
    if region.hand_overlap_fraction() < REPAIR_REGION_MIN_HAND_OVERLAP:
        raise RepairRegionError(
            f"repair region encloses only {region.hand_overlap_fraction():.6f} of the "
            f"gripping-hand bbox, below the required "
            f"{REPAIR_REGION_MIN_HAND_OVERLAP}"
        )
    if region.contact_overlap_fraction() < REPAIR_REGION_MIN_CONTACT_OVERLAP:
        raise RepairRegionError(
            f"repair region encloses only {region.contact_overlap_fraction():.6f} of the "
            f"hilt/contact region, below the required "
            f"{REPAIR_REGION_MIN_CONTACT_OVERLAP}"
        )


# --------------------------------------------------------------------------- #
# PHASE 5 - deterministic CPU repair-mask generation
# --------------------------------------------------------------------------- #
# The mask is an 8-bit grayscale PNG: 255 inside the permitted composite region,
# 0 everywhere else. Feathering, when enabled, ramps INWARD from the region
# boundary. That choice is deliberate and is what makes the outside-region
# immutability policy strict rather than approximate:
#
#     alpha == 0 on and outside the mask boundary
#     alpha ramps 0 -> 255 over REPAIR_MASK_FEATHER_PX pixels going inward
#     alpha == 255 in the interior
#
# Because the ramp is inward, the set of pixels that may legally change is
# EXACTLY the mask rect. There is no outward feather band bleeding into
# protected territory, so the policy is "byte-identical outside the explicit
# composite mask" with no tolerance and no perceptual metric.

#: Feather width in pixels at the qualified 1024x1024 production resolution.
REPAIR_MASK_FEATHER_PX = 12
#: Deterministic, integer-only inward ramp. No blur kernel, no float filter, no
#: library-version-dependent resampling -> byte-stable across hosts.
REPAIR_MASK_FEATHER_ALGORITHM = "deterministic_inward_linear_chebyshev_ramp"
REPAIR_MASK_MODE = "L"
REPAIR_MASK_FULL = 255
REPAIR_MASK_EMPTY = 0


def render_hand_repair_mask(
    region: HandRepairRegion,
    *,
    feather_px: int = REPAIR_MASK_FEATHER_PX,
) -> bytes:
    """Render the deterministic bounded repair mask as PNG bytes (side-effect free).

    Deterministic by construction: fixed mode, fixed size, integer-only geometry,
    integer-only inward ramp, and a PIL PNG save with no pnginfo/timestamp. The
    same region + feather therefore always yields byte-identical output, and any
    geometry change necessarily changes the bytes (and the SHA-256).
    """
    if int(feather_px) < 0:
        raise RepairRegionError(f"feather_px must be >= 0, got {feather_px!r}")

    w, h = int(region.image_width), int(region.image_height)
    x0, y0, x1, y1 = region.pixel_box()
    img = Image.new(REPAIR_MASK_MODE, (w, h), REPAIR_MASK_EMPTY)

    box_w, box_h = x1 - x0, y1 - y0
    if box_w <= 0 or box_h <= 0:
        raise RepairRegionError(
            f"repair mask region is degenerate in pixel space: {box_w}x{box_h}"
        )

    # Cap the inward ramp so it can never consume the whole region (a fully
    # ramped mask would have no fully-editable interior).
    max_ramp = max(0, (min(box_w, box_h) - 1) // 2)
    ramp = min(int(feather_px), max_ramp)

    draw = ImageDraw.Draw(img)
    if ramp <= 0:
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=REPAIR_MASK_FULL)
        return _png_bytes(img)

    # Deterministic inward linear ramp using the Chebyshev distance to the region
    # boundary: concentric integer rectangles, outermost first.
    for step in range(ramp + 1):
        # step 0 == outermost ring (alpha lowest), step == ramp -> full interior.
        alpha = int(round(REPAIR_MASK_FULL * (step + 1) / float(ramp + 1)))
        if step == ramp:
            alpha = REPAIR_MASK_FULL
        rx0, ry0 = x0 + step, y0 + step
        rx1, ry1 = x1 - 1 - step, y1 - 1 - step
        if rx1 < rx0 or ry1 < ry0:
            break
        draw.rectangle([rx0, ry0, rx1, ry1], fill=alpha)
    return _png_bytes(img)


def _png_bytes(img: "Image.Image") -> bytes:
    """Deterministic PNG serialization (no pnginfo, no timestamp, no RNG)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def repair_mask_sha256(mask_png: bytes) -> str:
    return hashlib.sha256(mask_png).hexdigest()


def load_mask_alpha(mask_png: bytes) -> Tuple["Image.Image", int, int]:
    """Load a repair mask PNG into an 8-bit alpha image (fail closed on mode)."""
    img = Image.open(io.BytesIO(mask_png))
    img.load()
    if img.mode != REPAIR_MASK_MODE:
        img = img.convert(REPAIR_MASK_MODE)
    return img, img.width, img.height


# --------------------------------------------------------------------------- #
# PHASE 4 - Soulblade-safe repair mask (fail-closed region/clip isolation)
# --------------------------------------------------------------------------- #
# The qualified hand-repair region legitimately overlaps the Soulblade blade
# region (soulblade_overlap_fraction up to REPAIR_REGION_MAX_SOULBLADE_COVERAGE).
# The blade MUST remain immutable outside the explicitly permitted contact/hilt
# subregion. The CPU evidence from the previous real-source GPU qualification
# proved the bare hand-repair mask permitted inpaint mutation of bare-blade
# pixels above the contact band, breaching the Soulblade firewall.
#
# Remediation (narrowest, strategy D = B + C):
#
#     effective_repair_mask =
#         hand_repair_mask
#         MINUS ( soulblade_region MINUS permitted_contact_subregion )
#
# i.e. for every pixel:
#     - not in Soulblade                          -> keep hand-repair semantics
#     - in Soulblade AND in permitted contact     -> repair may be permitted
#     - in Soulblade AND outside permitted contact -> alpha MUST be zero
#
# The exclusion is applied AFTER the feather ramp, and is keyed on blade/contact
# MEMBERSHIP, so the inward feather ramp can never bleed back into forbidden
# Soulblade pixels. Fail closed when the required blade/contact geometry is
# missing or degenerate: the Soulblade firewall cannot then be guaranteed, and
# we must NOT silently permit the entire Soulblade region.

def render_soulblade_safe_repair_mask(
    region: "HandRepairRegion",
    *,
    feather_px: int = REPAIR_MASK_FEATHER_PX,
) -> bytes:
    """Effective Soulblade-safe repair mask (fail closed).

    Returns the hand-repair mask with every Soulblade pixel outside the
    permitted contact/hilt subregion forced to alpha 0. The result is
    deterministic and content-addressed on the same geometry that defines the
    region, so any change to hand/contact/blade geometry, padding, resolution,
    or feather necessarily changes the bytes and therefore the SHA-256.
    """
    br = getattr(region, "blade_rect", None)
    cr = getattr(region, "contact_rect", None)
    if br is None or cr is None:
        raise RepairRegionError(
            "soulblade-safe repair mask requires both blade_rect and contact_rect "
            "geometry; missing Soulblade/contact geometry fails closed because the "
            "Soulblade firewall cannot be guaranteed (we must not silently permit "
            "the entire Soulblade region)"
        )
    if _area(br) <= 0.0:
        raise RepairRegionError(
            "soulblade-safe repair mask requires a non-degenerate Soulblade blade "
            "region; degenerate blade geometry fails closed"
        )
    if _area(cr) <= 0.0:
        raise RepairRegionError(
            "soulblade-safe repair mask requires a non-degenerate Soulblade "
            "contact/hilt subregion; degenerate contact geometry fails closed"
        )

    # Base hand-repair mask (deterministic inward feather ramp).
    base = render_hand_repair_mask(region, feather_px=feather_px)
    img = Image.open(io.BytesIO(base)).convert(REPAIR_MASK_MODE)
    px = img.load()
    w, h = img.size

    bx0, by0 = int(br[0] * w), int(br[1] * h)
    bx1, by1 = int((br[0] + br[2]) * w), int((br[1] + br[3]) * h)
    cx0, cy0 = int(cr[0] * w), int(cr[1] * h)
    cx1, cy1 = int((cr[0] + cr[2]) * w), int((cr[1] + cr[3]) * h)
    bx0, by0 = max(0, bx0), max(0, by0)
    bx1, by1 = min(w, bx1), min(h, by1)
    cx0, cy0 = max(0, cx0), max(0, cy0)
    cx1, cy1 = min(w, cx1), min(h, cy1)

    # Zero every forbidden Soulblade pixel (blade AND NOT contact) AFTER feather.
    # Membership-based, so the feather ramp cannot re-enter forbidden pixels.
    for y in range(by0, by1):
        row_in_contact = cy0 <= y < cy1
        for x in range(bx0, bx1):
            if row_in_contact and cx0 <= x < cx1:
                continue  # permitted contact/hilt subregion
            px[x, y] = REPAIR_MASK_EMPTY
    return _png_bytes(img)


# --------------------------------------------------------------------------- #
# PHASE 7/8 - repair-stage conditioning (LOCAL ONLY, firewalled)
# --------------------------------------------------------------------------- #
# These strings are the ONLY conditioning this stage owns. They never touch the
# primary prompt builder (tools/realistic_pipeline_v2._realistic_positive_prompt
# / _realistic_negative_prompt) and are never appended to primary conditioning.
#
# Deliberately EXCLUDED (each was either causally refuted or is out of scope):
#   - global composition / framing instructions (COMPOSITION_CONSTRAINT was
#     FAIL_DEGRADED; it must not be reintroduced here),
#   - HAND_HILT_ISOLATION regional conditioning (FAIL_NEUTRAL),
#   - any face / expression instruction (face repair is a separate stage),
#   - any environment / scene / lighting / camera instruction.

REPAIR_POSITIVE_CONDITIONING = (
    "anatomically coherent gripping hand, five distinct fingers, "
    "thumb opposing fingers, fingers wrapped around the Soulblade hilt, "
    "clear hand-to-hilt contact, intact palm and wrist"
)

REPAIR_NEGATIVE_CONDITIONING = (
    "fused fingers, merged digits, extra fingers, missing fingers, "
    "hand-object fusion, blade through palm, malformed wrist, "
    "melted hand, duplicated hand"
)

#: Tokens that must NEVER appear in repair conditioning. This is a mechanical
#: firewall, not a comment: ``assert_repair_conditioning_local`` enforces it and
#: the targeted test suite asserts it.
REPAIR_CONDITIONING_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "medium shot",
    "upper-body",
    "upper body",
    "portrait",
    "framing",
    "composition",
    "camera",
    "angle",
    "background",
    "environment",
    "scene",
    "alley",
    "rain",
    "lighting",
    "light source",
    "face",
    "facial",
    "expression",
    "eyes",
    "hair",
    "centered",
    "in frame",
    "inside the frame",
    "outside frame",
    "upscale",
)


def conditioning_sha256(text: str) -> str:
    """Content address of one conditioning string (deterministic, encoding-fixed)."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def assert_repair_conditioning_local(
    positive: str = REPAIR_POSITIVE_CONDITIONING,
    negative: str = REPAIR_NEGATIVE_CONDITIONING,
) -> None:
    """Fail closed when repair conditioning leaks non-local intent."""
    from tools.spatial_guide import (
        HAND_HILT_ISOLATION_NEGATIVE,
        HAND_HILT_ISOLATION_POSITIVE,
    )
    from tools.realistic_pipeline_v2 import (
        REALISTIC_COMPOSITION_CONSTRAINT_NEGATIVE,
        REALISTIC_COMPOSITION_CONSTRAINT_POSITIVE,
    )

    for label, text in (("positive", positive), ("negative", negative)):
        low = str(text).lower()
        for token in REPAIR_CONDITIONING_FORBIDDEN_TOKENS:
            if token in low:
                raise RegionalHandRepairError(
                    f"repair {label} conditioning must remain local to hand/grip "
                    f"anatomy but contains the forbidden token {token!r}"
                )
    if REALISTIC_COMPOSITION_CONSTRAINT_POSITIVE in positive:
        raise RegionalHandRepairError(
            "COMPOSITION_CONSTRAINT positive conditioning must not be reintroduced "
            "into the repair stage (prior causal result: FAIL_DEGRADED)"
        )
    if REALISTIC_COMPOSITION_CONSTRAINT_NEGATIVE in negative:
        raise RegionalHandRepairError(
            "COMPOSITION_CONSTRAINT negative conditioning must not be reintroduced "
            "into the repair stage (prior causal result: FAIL_DEGRADED)"
        )
    if HAND_HILT_ISOLATION_POSITIVE in positive or HAND_HILT_ISOLATION_NEGATIVE in negative:
        raise RegionalHandRepairError(
            "HAND_HILT_ISOLATION regional conditioning must not be reintroduced "
            "into the repair stage (prior causal result: FAIL_NEUTRAL)"
        )


# --------------------------------------------------------------------------- #
# PHASE 2 - repair request contract (NOT part of GenerationSpec)
# --------------------------------------------------------------------------- #
# This object carries ONLY repair-stage data. It is not embedded in
# GenerationSpec, it does not participate in generation_spec_sha256, and it does
# not influence the primary execution identity. Host paths are carried for I/O
# convenience only and are EXCLUDED from every hash.

#: Deterministic repair-seed derivation domain. The repair seed is derived from
#: the source image identity, so it is reproducible from provenance alone and is
#: provably NOT the primary seed.
REPAIR_SEED_DOMAIN = "regional_hand_repair_seed_v1"
REPAIR_SEED_MODULUS = 2 ** 31 - 1

#: Conservative provisional repair sampler settings (see the GPU re-entry spec).
REPAIR_DEFAULT_SAMPLER = "dpmpp_2m"
REPAIR_DEFAULT_SCHEDULER = "karras"
REPAIR_DEFAULT_STEPS = 24
REPAIR_DEFAULT_CFG = 4.5
REPAIR_DEFAULT_DENOISE = 0.58
REPAIR_PARAMETERS_PROVISIONAL = True


def derive_repair_seed(source_image_sha256: str) -> int:
    """Deterministic repair seed derived from the source image identity.

    Explicitly NOT the primary seed: it is a separate value in a separate
    domain, so the repair pass cannot be confused with a base regeneration and
    the primary seed is never reused or mutated.
    """
    if not source_image_sha256:
        raise RepairIdentityError("cannot derive a repair seed without source_image_sha256")
    digest = hashlib.sha256(
        f"{REPAIR_SEED_DOMAIN}:{source_image_sha256}".encode("utf-8")
    ).hexdigest()
    return int(digest[:16], 16) % REPAIR_SEED_MODULUS


@dataclass(frozen=True)
class RepairRequest:
    """Immutable repair-stage request. Carries ONLY repair data.

    ``source_image_path`` is host I/O convenience and is deliberately EXCLUDED
    from ``identity_payload`` / ``sha256`` so the request identity is
    content-addressed and host-independent.
    """

    # --- source binding (content-addressed) ---
    source_image_sha256: str
    # --- localization authority (sanctioned OpenPose-21 hand guide) ---
    hand_guide_sha256: str
    structural_request_sha256: str
    repair_region: HandRepairRegion
    repair_mask_sha256: str
    # --- repair conditioning ---
    repair_prompt: str
    repair_negative_prompt: str
    # --- repair sampler ---
    repair_seed: int
    sampler: str
    scheduler: str
    steps: int
    cfg: float
    denoise: float
    # --- model binding (reused, never re-selected) ---
    checkpoint_asset_id: str
    checkpoint_reference: str
    checkpoint_sha256: str
    lora_asset_id: str
    lora_reference: str
    lora_sha256: str
    lora_strength: float
    # --- mask/composite policy ---
    feather_px: int = REPAIR_MASK_FEATHER_PX
    # --- encode architecture discriminator (G2, content-addressed) ---
    # CONTROL = vae_encode_for_inpaint ; TREATMENT = vae_encode_set_latent_noise_mask.
    # This is the single permitted causal factor between control and treatment and
    # is folded into the repair execution identity so the two cannot collide.
    repair_encode_architecture: str = (
        REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT
    )
    # --- provenance linkage (identity only, never mutated) ---
    source_primary_execution_id: str = ""
    # --- host I/O convenience (EXCLUDED from identity) ---
    source_image_path: str = ""
    hand_guide_reference: str = ""

    def __post_init__(self) -> None:
        if self.repair_encode_architecture not in REPAIR_ENCODE_ARCHITECTURE_VALUES:
            raise RepairIdentityError(
                f"repair_encode_architecture must be one of "
                f"{sorted(REPAIR_ENCODE_ARCHITECTURE_VALUES)}; got "
                f"{self.repair_encode_architecture!r}"
            )

    def identity_payload(self) -> Dict[str, Any]:
        """Complete reconstructable request payload.

        Transport paths may appear here because this payload can be used to
        reconstruct the request. It is not the canonical authorization
        identity.
        """
        return {
            "stage": REGIONAL_HAND_REPAIR_STAGE,
            "version": REGIONAL_HAND_REPAIR_VERSION,
            "repair_encode_architecture": self.repair_encode_architecture,
            "source_image_sha256": self.source_image_sha256,
            "hand_guide_sha256": self.hand_guide_sha256,
            "hand_guide_role": OPENPOSE_GUIDE_ROLE,
            "openpose_controlnet_used": OPENPOSE_CONTROLNET_USED_IN_REPAIR,
            "structural_request_sha256": self.structural_request_sha256,
            "repair_region_sha256": self.repair_region.sha256(),
            "repair_mask_sha256": self.repair_mask_sha256,
            "repair_prompt_sha256": conditioning_sha256(self.repair_prompt),
            "repair_negative_prompt_sha256": conditioning_sha256(
                self.repair_negative_prompt
            ),
            "repair_seed": int(self.repair_seed),
            "sampler": self.sampler,
            "scheduler": self.scheduler,
            "steps": int(self.steps),
            "cfg": round(float(self.cfg), 8),
            "denoise": round(float(self.denoise), 8),
            "checkpoint_asset_id": self.checkpoint_asset_id,
            "checkpoint_reference": self.checkpoint_reference,
            "checkpoint_sha256": self.checkpoint_sha256,
            "lora_asset_id": self.lora_asset_id,
            "lora_reference": self.lora_reference,
            "lora_sha256": self.lora_sha256,
            "lora_strength": round(float(self.lora_strength), 8),
            "feather_px": int(self.feather_px),
            "source_image_path": self.source_image_path,
            "hand_guide_reference": self.hand_guide_reference,
        }

    def hash_preimage(self) -> Dict[str, Any]:
        """Host-independent canonical task identity."""
        payload = self.identity_payload()
        return {
            key: value
            for key, value in payload.items()
            if key not in ("source_image_path", "hand_guide_reference")
        }

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.hash_preimage(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def reconstruct(cls, request: "RepairRequest") -> "RepairRequest":
        """Rebuild a byte-identical request from another (host-independent)."""
        return cls(
            source_image_sha256=request.source_image_sha256,
            hand_guide_sha256=request.hand_guide_sha256,
            structural_request_sha256=request.structural_request_sha256,
            repair_region=request.repair_region,
            repair_mask_sha256=request.repair_mask_sha256,
            repair_prompt=request.repair_prompt,
            repair_negative_prompt=request.repair_negative_prompt,
            repair_seed=request.repair_seed,
            sampler=request.sampler,
            scheduler=request.scheduler,
            steps=request.steps,
            cfg=request.cfg,
            denoise=request.denoise,
            checkpoint_asset_id=request.checkpoint_asset_id,
            checkpoint_reference=request.checkpoint_reference,
            checkpoint_sha256=request.checkpoint_sha256,
            lora_asset_id=request.lora_asset_id,
            lora_reference=request.lora_reference,
            lora_sha256=request.lora_sha256,
            lora_strength=request.lora_strength,
            feather_px=request.feather_px,
            repair_encode_architecture=request.repair_encode_architecture,
            source_primary_execution_id=request.source_primary_execution_id,
            source_image_path=request.source_image_path,
            hand_guide_reference=request.hand_guide_reference,
        )


# --------------------------------------------------------------------------- #
# PHASE 6 - CPU-only inpaint workflow (built, NEVER submitted here)
# --------------------------------------------------------------------------- #
# Uses ONLY already-present ComfyUI core nodes. No new node, no custom node, no
# model download. The graph is deterministic JSON (no RNG, no timestamps).
#
# Nodes (core):
#   R0  CheckpointLoaderSimple        (same SDXL checkpoint, reused)
#   R1  LoraLoader                    (same LoRA, reused)
#   R2  CLIPTextEncode                (repair POSITIVE, local anatomy only)
#   R3  CLIPTextEncode                (repair NEGATIVE, local defects only)
#   R4  LoadImage                     (the SOURCE image - load bearing)
#   R5  LoadImageMask / mask input    (the REPAIR MASK - load bearing)
#   R6  VAEEncodeForInpaint           (source + mask -> inpaint latent)
#   R7  KSampler                      (bounded inpaint pass; denoise < 1.0)
#   R8  VAEDecode                     (repair latent -> repair candidate PNG)
#   R9  SaveImage                     (candidate bytes; final composite is CPU-side)
#
# Safety properties enforced mechanically:
#   - there is exactly ONE KSampler and it consumes the VAEEncodeForInpaint
#     latent, so the pass is a bounded inpaint, NOT a whole-image second sampler;
#   - the source image and mask are both referenced (load bearing);
#   - OpenPose ControlNet is NOT present (single-factor policy);
#   - the final authoritative composite (outside-region immutability) is performed
#     CPU-side by ``composite_repaired_against_source`` using the deterministic
#     mask, so the persisted bytes are guaranteed source-derived outside the
#     permitted region.

REPAIR_WORKFLOW_TEMPLATE_ID = "regional_hand_repair_inpaint"
REPAIR_WORKFLOW_VERSION = "1.0"
REPAIR_NODE_CLASS_CHECKPOINT = "CheckpointLoaderSimple"
REPAIR_NODE_CLASS_LORA = "LoraLoader"
REPAIR_NODE_CLASS_CLIPENC = "CLIPTextEncode"
REPAIR_NODE_CLASS_LOADIMAGE = "LoadImage"
REPAIR_NODE_CLASS_LOADMASK = "LoadImageMask"
REPAIR_NODE_CLASS_VAEENCODEINPAINT = "VAEEncodeForInpaint"
REPAIR_NODE_CLASS_KSAMPLER = "KSampler"
REPAIR_NODE_CLASS_VAEDECODE = "VAEDecode"
REPAIR_NODE_CLASS_SAVEIMAGE = "SaveImage"
REPAIR_NODE_CLASS_VAEENCODE = "VAEEncode"
REPAIR_NODE_CLASS_SETLATENTNOISEMASK = "SetLatentNoiseMask"
REPAIR_PNG_INFO_KEY = "regional_hand_repair_inpaint"


def build_regional_hand_repair_workflow(
    request: "RepairRequest",
    *,
    image_filename: str = "repair_source.png",
    mask_filename: str = "repair_mask.png",
    output_prefix: str = "regional_hand_repair",
) -> Dict[str, Any]:
    """Build the deterministic bounded-inpaint repair workflow (CPU-only).

    No GPU, no ComfyUI client, no submission. Returns a plain dict graph. The
    caller is responsible for persisting the source/mask bytes under the
    referenced filenames (handled by ``run_regional_hand_repair``).
    """
    assert_repair_conditioning_local(
        request.repair_prompt, request.repair_negative_prompt
    )
    nodes: Dict[str, Any] = {
        "R0": {
            "class_type": REPAIR_NODE_CLASS_CHECKPOINT,
            "inputs": {"ckpt_name": request.checkpoint_reference},
        },
        "R1": {
            "class_type": REPAIR_NODE_CLASS_LORA,
            "inputs": {
                "lora_name": request.lora_reference,
                "strength_model": round(float(request.lora_strength), 8),
                "strength_clip": round(float(request.lora_strength), 8),
                "model": ["R0", 0],
                "clip": ["R0", 1],
            },
        },
        "R2": {
            "class_type": REPAIR_NODE_CLASS_CLIPENC,
            "inputs": {"text": request.repair_prompt, "clip": ["R1", 1]},
        },
        "R3": {
            "class_type": REPAIR_NODE_CLASS_CLIPENC,
            "inputs": {"text": request.repair_negative_prompt, "clip": ["R1", 1]},
        },
        "R4": {
            "class_type": REPAIR_NODE_CLASS_LOADIMAGE,
            "inputs": {"image": image_filename},
        },
        "R5": {
            "class_type": REPAIR_NODE_CLASS_LOADMASK,
            "inputs": {"image": mask_filename, "channel": "red"},
        },
        "R6": {
            "class_type": REPAIR_NODE_CLASS_VAEENCODEINPAINT,
            "inputs": {
                "pixels": ["R4", 0],
                "vae": ["R0", 2],
                "mask": ["R5", 0],
                "grow_mask_by": 0,
            },
        },
        "R7": {
            "class_type": REPAIR_NODE_CLASS_KSAMPLER,
            "inputs": {
                "seed": int(request.repair_seed),
                "steps": int(request.steps),
                "cfg": round(float(request.cfg), 8),
                "sampler_name": request.sampler,
                "scheduler": request.scheduler,
                "denoise": round(float(request.denoise), 8),
                "model": ["R1", 0],
                "positive": ["R2", 0],
                "negative": ["R3", 0],
                "latent_image": ["R6", 0],
            },
        },
        "R8": {
            "class_type": REPAIR_NODE_CLASS_VAEDECODE,
            "inputs": {"samples": ["R7", 0], "vae": ["R0", 2]},
        },
        "R9": {
            "class_type": REPAIR_NODE_CLASS_SAVEIMAGE,
            "inputs": {"images": ["R8", 0], "filename_prefix": output_prefix},
        },
    }

    # Encode-architecture branch (G2). CONTROL keeps the destructive
    # VAEEncodeForInpaint node R6. TREATMENT splits it into a non-destructive
    # VAEEncode (R6T, original source RGB, NO mask) plus SetLatentNoiseMask
    # (R6M) so stochastic modification is confined to the repair mask while the
    # original masked RGB survives into the latent. This is the single permitted
    # causal factor; every other node is byte-identical across the two paths.
    arch = request.repair_encode_architecture
    if arch == REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK:
        r6 = nodes.pop("R6")
        nodes["R6T"] = {
            "class_type": REPAIR_NODE_CLASS_VAEENCODE,
            "inputs": {
                "pixels": r6["inputs"]["pixels"],  # [R4, 0] original source RGB
                "vae": r6["inputs"]["vae"],        # [R0, 2] same VAE
            },
        }
        nodes["R6M"] = {
            "class_type": REPAIR_NODE_CLASS_SETLATENTNOISEMASK,
            "inputs": {
                "samples": ["R6T", 0],
                "mask": r6["inputs"]["mask"],      # [R5, 0] effective repair mask
            },
        }
        nodes["R7"]["inputs"]["latent_image"] = ["R6M", 0]

    metadata: Dict[str, Any] = {
        "id": REPAIR_WORKFLOW_TEMPLATE_ID,
        "version": REPAIR_WORKFLOW_VERSION,
        "description": (
            "Bounded regional hand-repair inpaint pass. Reuses the primary SDXL "
            "checkpoint and LoRA; local hand/grip anatomy conditioning only; "
            "OpenPose ControlNet intentionally absent (single causal factor)."
        ),
        "openpose_controlnet_used": OPENPOSE_CONTROLNET_USED_IN_REPAIR,
        "whole_image_second_pass": False,
        "load_bearing": {
            "source_image": True,
            "repair_mask": True,
            "inpaint_conditioning": True,
        },
        "final_composite": "cpu_side_against_original_source",
        "encode_architecture": request.repair_encode_architecture,
        "png_info": {REPAIR_PNG_INFO_KEY: request.sha256()},
    }
    return {"v2_meta": metadata, "nodes": nodes}


# --------------------------------------------------------------------------- #
# PHASE 12 - deterministic repair execution identity
# --------------------------------------------------------------------------- #

def derive_repair_execution_id(request: "RepairRequest") -> str:
    """Separate, host-independent repair execution identity (never primary ID).

    Derived from source + request + mask + sampler settings. No absolute path is
    included, so the same repair parameters map to the same identity on every
    host. The namespace ``v2repair-hand`` guarantees zero collision with primary
    ``v2exec-<profile>-<digest>`` identities even when reusing the same registry
    object.
    """
    payload = request.identity_payload()
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"{REPAIR_EXECUTION_NAMESPACE}-{digest}"


# --------------------------------------------------------------------------- #
# PHASE 13 - repair provenance (additive nested block; schema unchanged)
# --------------------------------------------------------------------------- #

def build_repair_provenance(
    request: "RepairRequest",
    *,
    source_primary_execution_id: str,
    repair_execution_id: str,
    repaired_region_sha256: str,
    final_image_sha256: str,
) -> Dict[str, Any]:
    """Compose the additive repair provenance block (no schema version change)."""
    return {
        "stage": REGIONAL_HAND_REPAIR_STAGE,
        "version": REGIONAL_HAND_REPAIR_VERSION,
        "enabled": True,
        "activated_in_production": False,
        "source_image_sha256": request.source_image_sha256,
        "source_primary_execution_id": source_primary_execution_id,
        "repair_execution_id": repair_execution_id,
        "repair_request_sha256": request.sha256(),
        "repair_region": request.repair_region.to_json(),
        "repair_region_sha256": request.repair_region.sha256(),
        "repair_mask_sha256": request.repair_mask_sha256,
        "hand_guide_sha256": request.hand_guide_sha256,
        "hand_guide_role": OPENPOSE_GUIDE_ROLE,
        "openpose_controlnet_used": OPENPOSE_CONTROLNET_USED_IN_REPAIR,
        "structural_request_sha256": request.structural_request_sha256,
        "checkpoint": {
            "asset_id": request.checkpoint_asset_id,
            "reference": request.checkpoint_reference,
            "sha256": request.checkpoint_sha256,
        },
        "lora": {
            "asset_id": request.lora_asset_id,
            "reference": request.lora_reference,
            "sha256": request.lora_sha256,
            "strength": round(float(request.lora_strength), 8),
        },
        "sampler": request.sampler,
        "scheduler": request.scheduler,
        "steps": int(request.steps),
        "cfg": round(float(request.cfg), 8),
        "denoise": round(float(request.denoise), 8),
        "repair_seed": int(request.repair_seed),
        "repair_prompt_sha256": conditioning_sha256(request.repair_prompt),
        "repair_negative_prompt_sha256": conditioning_sha256(
            request.repair_negative_prompt
        ),
        "repaired_region_sha256": repaired_region_sha256,
        "final_image_sha256": final_image_sha256,
    }


# --------------------------------------------------------------------------- #
# PHASE 10/11 - immutability + Soulblade firewalls (CPU verifiers)
# --------------------------------------------------------------------------- #
# Allowed-change policy (strict, no perceptual tolerance): a pixel may differ
# from the source ONLY where mask alpha > 0 (the repair region). There is NO
# outward feather band because ``render_hand_repair_mask`` ramps INWARD, so the
# permitted-change set is exactly the mask interior. Everything outside is
# byte-identical.
#
# The Soulblade firewall permits change within the intersection of the mask and
# the Soulblade contact/hilt subregion only; change anywhere else on the blade
# region fails closed.

def _image_to_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_rgb(src_bytes: bytes) -> "Image.Image":
    img = Image.open(io.BytesIO(src_bytes)).convert("RGB")
    img.load()
    return img


def verify_outside_region_immutability(
    source_png: bytes,
    repaired_png: bytes,
    mask_png: bytes,
    *,
    feather_px: int = REPAIR_MASK_FEATHER_PX,
) -> None:
    """Fail closed unless repaired bytes equal source bytes outside the mask.

    A changed pixel anywhere the mask alpha is 0 raises
    ``RepairImmutabilityViolation``. Image-dimension change also fails closed.
    """
    src = _load_rgb(source_png)
    rep = _load_rgb(repaired_png)
    mask, mw, mh = load_mask_alpha(mask_png)
    if src.size != rep.size:
        raise RepairImmutabilityViolation(
            f"image dimension changed after repair: {src.size} -> {rep.size}"
        )
    if (mw, mh) != src.size:
        raise RepairImmutabilityViolation(
            f"mask dimensions {mw}x{mh} do not match image {src.size}"
        )

    sw, sh = src.size
    src_px = src.load()
    rep_px = rep.load()
    mask_px = mask.load()
    for y in range(sh):
        for x in range(sw):
            if mask_px[x, y] == 0:
                if src_px[x, y] != rep_px[x, y]:
                    raise RepairImmutabilityViolation(
                        f"pixel ({x},{y}) outside the repair mask changed "
                        f"(source {src_px[x, y]} -> repaired {rep_px[x, y]})"
                    )


def verify_soulblade_boundary(
    source_png: bytes,
    repaired_png: bytes,
    mask_png: bytes,
    blade_rect: Tuple[float, float, float, float],
    contact_rect: Tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
) -> None:
    """Fail closed if the Soulblade changes outside the contact/hilt subregion."""
    src = _load_rgb(source_png)
    rep = _load_rgb(repaired_png)
    mask, mw, mh = load_mask_alpha(mask_png)
    sw, sh = src.size
    if src.size != rep.size or (mw, mh) != src.size:
        raise RepairSoulbladeViolation("dimension mismatch in Soulblade boundary check")
    if (image_width, image_height) != src.size:
        raise RepairSoulbladeViolation(
            "declared image dimensions do not match decoded Soulblade images"
        )

    def _bounded_pixel_rect(
        label: str, rect: Tuple[float, float, float, float]
    ) -> Tuple[int, int, int, int]:
        if len(rect) != 4 or not all(math.isfinite(value) for value in rect):
            raise RepairSoulbladeViolation(f"{label} must contain four finite values")
        x, y, width, height = rect
        if (
            x < 0.0 or y < 0.0 or width <= 0.0 or height <= 0.0
            or x + width > 1.0 or y + height > 1.0
        ):
            raise RepairSoulbladeViolation(
                f"{label} must be a positive normalized rectangle within the image"
            )
        return (
            max(0, int(x * image_width)),
            max(0, int(y * image_height)),
            min(image_width, int((x + width) * image_width)),
            min(image_height, int((y + height) * image_height)),
        )

    cx0, cy0, cx1, cy1 = _bounded_pixel_rect("contact_rect", contact_rect)
    bx0, by0, bx1, by1 = _bounded_pixel_rect("blade_rect", blade_rect)

    src_px = src.load()
    rep_px = rep.load()
    mask_px = mask.load()
    for y in range(by0, by1):
        for x in range(bx0, bx1):
            if src_px[x, y] == rep_px[x, y]:
                continue
            on_contact = (cx0 <= x < cx1) and (cy0 <= y < cy1)
            masked = mask_px[x, y] > 0
            if (not on_contact) or (not masked):
                raise RepairSoulbladeViolation(
                    f"Soulblade pixel ({x},{y}) changed outside the permitted "
                    f"contact/hilt subregion (on_contact={on_contact}, masked={masked})"
                )


def composite_repaired_against_source(
    source_png: bytes,
    candidate_png: bytes,
    mask_png: bytes,
    *,
    blade_rect: Optional[Tuple[float, float, float, float]] = None,
    contact_rect: Optional[Tuple[float, float, float, float]] = None,
) -> bytes:
    """CPU final composite: keep source everywhere except inside the mask.

    The GPU KSampler candidate is only ever consulted inside the mask; the
    persisted output is therefore GUARANTEED source-derived outside the repair
    region, which is the strict outside-region immutability contract.

    Defense in depth (strategy D, part C): when the permitted Soulblade
    contact/hilt geometry is supplied, every Soulblade pixel OUTSIDE the
    contact subregion is forced to the original source pixel INDEPENDENTLY of
    the mask and of any upstream sampler candidate. This guarantees Soulblade
    immutability by construction even if a candidate or mask erroneously
    altered a forbidden blade pixel; it relies on NO sampler behaviour.
    """
    src = _load_rgb(source_png)
    cand = _load_rgb(candidate_png)
    mask, mw, mh = load_mask_alpha(mask_png)
    if src.size != cand.size or (mw, mh) != src.size:
        raise RepairImmutabilityViolation("cannot composite: dimension mismatch")
    out = Image.new("RGB", src.size)
    src_px = src.load()
    cand_px = cand.load()
    mask_px = mask.load()
    ow, oh = out.size
    out_px = out.load()
    for y in range(oh):
        for x in range(ow):
            if mask_px[x, y] > 0:
                out_px[x, y] = cand_px[x, y]
            else:
                out_px[x, y] = src_px[x, y]

    # Independent Soulblade restore (defense in depth). Only active when both
    # geometry rects are present and non-degenerate; it never expands the
    # permitted change set.
    if blade_rect is not None and contact_rect is not None:
        if _area(blade_rect) > 0.0 and _area(contact_rect) > 0.0:
            bx0, by0 = int(blade_rect[0] * ow), int(blade_rect[1] * oh)
            bx1, by1 = int((blade_rect[0] + blade_rect[2]) * ow), int(
                (blade_rect[1] + blade_rect[3]) * oh
            )
            cx0, cy0 = int(contact_rect[0] * ow), int(contact_rect[1] * oh)
            cx1, cy1 = int((contact_rect[0] + contact_rect[2]) * ow), int(
                (contact_rect[1] + contact_rect[3]) * oh
            )
            bx0, by0 = max(0, bx0), max(0, by0)
            bx1, by1 = min(ow, bx1), min(oh, by1)
            cx0, cy0 = max(0, cx0), max(0, cy0)
            cx1, cy1 = min(ow, cx1), min(oh, cy1)
            for y in range(by0, by1):
                row_in_contact = cy0 <= y < cy1
                for x in range(bx0, bx1):
                    if row_in_contact and cx0 <= x < cx1:
                        continue  # permitted contact/hilt subregion
                    out_px[x, y] = src_px[x, y]
    return _image_to_bytes(out)


# --------------------------------------------------------------------------- #
# PHASE 9 - repair-candidate content-validity gate (fail closed)
# --------------------------------------------------------------------------- #
# A bounded GPU inpaint can fail to produce meaningful hand content and instead
# decode to a low-contrast, near-achromatic GRAY BLOCK that destroys the
# hand/hilt interaction (observed in the EN regional repair GPU qualification:
# the candidate repair region was 87% achromatic with 86% of its pixels within
# +/-10 of a single gray mode). The spatial firewalls still pass, because the
# gray block is byte-faithfully preserved inside the mask and the Soulblade
# geometry is untouched. Such a candidate must NEVER be promoted to a successful
# repair; this gate fails closed and refuses it before any composite/persistence.
#
# It is deliberately conservative: it targets STRUCTURALLY INVALID placeholders,
# not aesthetic quality. A legitimate dark but chromatically rich repair (skin
# tones, colored clothing) has low achromatic fraction and a diffuse color
# histogram, so it is accepted. Only an effectively uniform GRAY block, a
# near-zero-variance canvas, or a mask misrouted as the image is rejected.

REPAIR_CANDIDATE_CONTENT_GATE_ENABLED = True

#: Modes that may carry meaningful RGB content after conversion.
_CANDIDATE_ALLOWED_MODES = frozenset({"RGB", "RGBA", "L", "P", "LA"})

#: Per-channel std below this on every channel => zero/near-zero-variance canvas.
_CANDIDATE_NEAR_ZERO_VAR_STD = 2.0

#: A pixel is "gray" when it is nearly achromatic...
_CANDIDATE_GRAY_MAX_MIN = 12.0
_CANDIDATE_GRAY_CHANNEL_TOL = 8.0
#: ...and the gray fraction across the repair region exceeding this => gray block.
_CANDIDATE_GRAY_FRACTION = 0.85

#: Fraction of repair-region pixels within +/-MODE_BAND of the modal color...
_CANDIDATE_MODE_BAND = 10
#: ...exceeding this (while also gray) => effectively uniform placeholder.
_CANDIDATE_UNIFORM_GRAY_FRACTION = 0.85

#: A candidate whose RGB equals the mask grayscale over this fraction is the mask
#: misrouted as the repair image (never valid content).
_CANDIDATE_MASK_VISUALIZATION_FRACTION = 0.90

#: Structural-variance discriminator (G-ray fail-closed hardening, Phase 3).
#: The previously failed gray candidate had repair-region max(std_rgb) ~= 29.77
#: while the source region had max(std_rgb) ~= 86.42. A valid (even dark but
#: chromatically rich) repair therefore exceeds this threshold; a near-uniform
#: gray placeholder does not. This is defense in depth ON TOP of the existing
#: neutral/achromatic checks, so the gate fails closed on low-variance content.
_CANDIDATE_STRUCTURAL_VARIANCE_MIN = 45.0


def verify_repair_candidate_content(
    candidate_png: bytes,
    mask_png: bytes,
    source_png: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Fail closed unless the candidate carries valid RGB content in the mask region.

    Returns a metrics dict on success; raises ``RepairCandidateContentError`` when
    the candidate is missing, corrupt, wrong mode/dimensions, an effectively
    uniform gray block, a near-zero-variance canvas, or a mask misrouted as the
    image. Never raises on legitimate (even dark/low-contrast) chromatically rich
    imagery.
    """
    if not candidate_png:
        raise RepairCandidateContentError("repair candidate is missing (empty bytes)")
    try:
        cand = Image.open(io.BytesIO(candidate_png))
        cand.load()
    except Exception as e:  # noqa: BLE001 - any decode failure fails closed
        raise RepairCandidateContentError(f"repair candidate is corrupt/unreadable: {e!r}")
    if cand.mode not in _CANDIDATE_ALLOWED_MODES:
        raise RepairCandidateContentError(
            f"repair candidate has unsupported image mode {cand.mode!r}; "
            f"expected one of {sorted(_CANDIDATE_ALLOWED_MODES)}"
        )

    mask, mw, mh = load_mask_alpha(mask_png)
    cand_rgb = cand.convert("RGB")
    cw, ch = cand_rgb.size
    if (cw, ch) != (mw, mh):
        raise RepairCandidateContentError(
            f"repair candidate dimensions {cw}x{ch} do not match mask "
            f"dimensions {mw}x{mh}"
        )
    if source_png is not None:
        src = _load_rgb(source_png)
        if src.size != (cw, ch):
            raise RepairCandidateContentError(
                f"repair candidate dimensions {cw}x{ch} do not match source "
                f"dimensions {src.size}"
            )

    cp = cand_rgb.load()
    mp = mask.load()
    rs = []  # red
    gs = []  # green
    bs = []  # blue
    gray = 0
    mask_vis = 0
    n = 0
    for y in range(ch):
        for x in range(cw):
            if mp[x, y] == 0:
                continue
            n += 1
            r, g, b = cp[x, y]
            rs.append(r); gs.append(g); bs.append(b)
            if (abs(r - g) < _CANDIDATE_GRAY_CHANNEL_TOL
                    and abs(g - b) < _CANDIDATE_GRAY_CHANNEL_TOL
                    and (max(r, g, b) - min(r, g, b)) < _CANDIDATE_GRAY_MAX_MIN):
                gray += 1
            if abs(r - mp[x, y]) < 3 and abs(g - mp[x, y]) < 3 and abs(b - mp[x, y]) < 3:
                mask_vis += 1

    if n == 0:
        raise RepairCandidateContentError(
            "repair mask encloses no pixels; cannot validate candidate content "
            "(fail closed: a repair must change a non-empty region)"
        )

    gray_frac = gray / n
    mask_vis_frac = mask_vis / n

    std_r = statistics.pstdev(rs) if n > 1 else 0.0
    std_g = statistics.pstdev(gs) if n > 1 else 0.0
    std_b = statistics.pstdev(bs) if n > 1 else 0.0

    # Modal color concentration (robust uniformity signal independent of std).
    modal_color = Counter((rs[i], gs[i], bs[i]) for i in range(n)).most_common(1)[0][0]
    mr, mg, mb = modal_color
    within_mode = 0
    for i in range(n):
        if (abs(rs[i] - mr) <= _CANDIDATE_MODE_BAND
                and abs(gs[i] - mg) <= _CANDIDATE_MODE_BAND
                and abs(bs[i] - mb) <= _CANDIDATE_MODE_BAND):
            within_mode += 1
    within_mode_frac = within_mode / n

    near_zero_var = (
        std_r < _CANDIDATE_NEAR_ZERO_VAR_STD
        and std_g < _CANDIDATE_NEAR_ZERO_VAR_STD
        and std_b < _CANDIDATE_NEAR_ZERO_VAR_STD
    )
    uniform_gray = (
        gray_frac > _CANDIDATE_GRAY_FRACTION
        and within_mode_frac > _CANDIDATE_UNIFORM_GRAY_FRACTION
    )

    if near_zero_var:
        raise RepairCandidateContentError(
            f"repair candidate is a near-zero-variance placeholder "
            f"(std R/G/B = {std_r:.2f}/{std_g:.2f}/{std_b:.2f}; fail closed)"
        )
    if uniform_gray:
        raise RepairCandidateContentError(
            f"repair candidate is an effectively uniform gray block "
            f"(gray_fraction={gray_frac:.3f}, within_mode_fraction={within_mode_frac:.3f}; "
            f"fail closed)"
        )
    if mask_vis_frac > _CANDIDATE_MASK_VISUALIZATION_FRACTION:
        raise RepairCandidateContentError(
            f"repair candidate equals the mask visualization "
            f"(mask_visualization_fraction={mask_vis_frac:.3f}); the mask was "
            f"misrouted as the repair image (fail closed)"
        )

    # Structural-variance discriminator (G3 gray-candidate hardening, Phase 3).
    # Defense in depth ON TOP of the neutral/achromatic checks above: even if a
    # placeholder slips past them, a near-uniform low-variance canvas has a
    # repair-region max(std_rgb) far below legitimate content and is rejected.
    max_std_rgb = max(std_r, std_g, std_b)
    if max_std_rgb < _CANDIDATE_STRUCTURAL_VARIANCE_MIN:
        raise RepairCandidateContentError(
            f"repair candidate fails structural-variance gate "
            f"(max(std_rgb)={max_std_rgb:.2f} < "
            f"{_CANDIDATE_STRUCTURAL_VARIANCE_MIN}; near-uniform low-variance "
            f"placeholder; fail closed)"
        )

    return {
        "stage": REGIONAL_HAND_REPAIR_STAGE,
        "status": "candidate_content_valid",
        "mask_region_pixels": n,
        "gray_fraction": round(gray_frac, 6),
        "within_mode_fraction": round(within_mode_frac, 6),
        "mask_visualization_fraction": round(mask_vis_frac, 6),
        "std_rgb": [round(std_r, 4), round(std_g, 4), round(std_b, 4)],
        "mode_color": list(modal_color),
        "candidate_mode": cand.mode,
        "candidate_dimensions": [cw, ch],
    }


# --------------------------------------------------------------------------- #
# PHASE 6 - deterministic ComfyUI output retrieval (fail closed)
# --------------------------------------------------------------------------- #
# The GPU repair candidate is the VAEDecode -> SaveImage artifact. Retrieval must
# select that EXACT node deterministically and must NEVER substitute a mask,
# preview, neutral image, stale artifact, or an arbitrary first image. The
# selection is centralized here so every harness shares one tested, fail-closed
# path.

REPAIR_SAVEIMAGE_NODE_ID = "R9"


def select_repair_saveimage_output(
    history_outputs: Dict[str, Any],
    save_image_node_id: str = REPAIR_SAVEIMAGE_NODE_ID,
) -> Optional[Dict[str, str]]:
    """Return the VAEDecode/SaveImage output locator, or None (fail closed).

    Returns ``{"subfolder", "filename", "type"}`` for ``images[0]`` of the
    SaveImage node, or ``None`` when the expected node is absent, has no images,
    or the outputs structure is malformed. The caller must treat ``None`` as a
    hard refusal: it must NOT fall back to another node, a mask, a preview, or a
    stale/neutral image.
    """
    if not isinstance(history_outputs, dict):
        return None
    node_out = history_outputs.get(save_image_node_id)
    if not isinstance(node_out, dict):
        return None
    images = node_out.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        return None
    filename = first.get("filename")
    if not filename:
        return None
    return {
        "subfolder": first.get("subfolder", ""),
        "filename": filename,
        "type": first.get("type", "output"),
    }


# --------------------------------------------------------------------------- #
# PHASE 2 / orchestrator - run_regional_hand_repair (GPU authority first)
# --------------------------------------------------------------------------- #

def run_regional_hand_repair(
    request: "RepairRequest",
    *,
    gpu_authority: bool = False,
    submitter: Optional[Callable[["RepairRequest", Dict[str, Any]], bytes]] = None,
    registry: Any = None,
) -> Dict[str, Any]:
    """Optional, post-generation bounded regional hand-repair orchestration.

    CPU construction of region/mask/workflow/execution-id/provenance is always
    allowed. GPU authority is checked FIRST, before any reservation, before any
    client construction, and before any submission. With ``gpu_authority=False``
    (the only state allowed by this task) this returns a structured refusal and
    performs NO GPU-side action.

    ``submitter`` is the ONLY injected point that may touch ComfyUI; it is never
    constructed or called here without explicit GPU authority.
    """
    repair_id = derive_repair_execution_id(request)
    request_sha = request.sha256()
    mask_sha = request.repair_mask_sha256

    # --- GPU authority precedes EVERYTHING GPU-side ----------------------- #
    if not gpu_authority:
        return {
            "stage": REGIONAL_HAND_REPAIR_STAGE,
            "gpu_authority": False,
            "submitted": False,
            "status": "refused_no_gpu_authority",
            "repair_execution_id": repair_id,
            "repair_request_sha256": request_sha,
            "repair_mask_sha256": mask_sha,
            "gpu_submission_attempted": False,
            "note": "CPU construction allowed; GPU submission refused (authority absent)",
        }

    # From here GPU authority is True; still require production activation.
    if not REGIONAL_HAND_REPAIR_DEFAULT_ENABLED:
        raise RepairGpuAuthorityAbsent(
            "repair stage is not production-activated; GPU authority alone is "
            "insufficient (PRODUCTION_REPAIR_ACTIVATED=False)"
        )
    if submitter is None:
        raise RepairGpuAuthorityAbsent(
            "no repair submitter injected; refusing to construct a GPU client"
        )

    # Reservation / submission lifecycle begins ONLY at this boundary.
    reg = registry if _has_reserve(registry) else _NoReserveRegistry()
    if not reg.check_and_reserve(repair_id):
        raise RepairDuplicateSubmission(
            f"duplicate repair submission blocked for {repair_id}"
        )
    try:
        workflow = build_regional_hand_repair_workflow(request)
        candidate = submitter(request, workflow)
        # Fail closed on structurally invalid candidates (e.g. a uniform gray
        # block): never promote an invalid decode to the final composite.
        if REPAIR_CANDIDATE_CONTENT_GATE_ENABLED:
            verify_repair_candidate_content(
                candidate,
                _mask_bytes_from_request(request),
                source_png=_source_bytes_from_request(request),
            )
        repaired = composite_repaired_against_source(
            _source_bytes_from_request(request),
            candidate,
            _mask_bytes_from_request(request),
            blade_rect=request.repair_region.blade_rect,
            contact_rect=request.repair_region.contact_rect,
        )
    finally:
        reg.release(repair_id)
    return {
        "stage": REGIONAL_HAND_REPAIR_STAGE,
        "gpu_authority": True,
        "submitted": True,
        "status": "submitted",
        "repair_execution_id": repair_id,
        "repaired_image_sha256": hashlib.sha256(repaired).hexdigest(),
        "gpu_submission_attempted": True,
    }


class _NoReserveRegistry:
    """Namespace-safe default when no registry is supplied (single attempt)."""

    def check_and_reserve(self, _id: str) -> bool:
        return True

    def release(self, _id: str) -> None:
        return None


def _has_reserve(reg: Any) -> bool:
    return reg is not None and hasattr(reg, "check_and_reserve")


def _source_bytes_from_request(request: "RepairRequest") -> bytes:
    from pathlib import Path

    if not request.source_image_path:
        raise RepairIdentityError(
            "repair request carries no source_image_path for execution"
        )
    data = Path(request.source_image_path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != request.source_image_sha256:
        raise RepairIdentityError(
            f"source image SHA mismatch: expected {request.source_image_sha256}, "
            f"got {digest}"
        )
    return data


def _mask_bytes_from_request(request: "RepairRequest") -> bytes:
    from pathlib import Path

    if not request.hand_guide_reference:
        raise RepairIdentityError("repair request carries no persisted mask reference")
    return Path(request.hand_guide_reference).read_bytes()
