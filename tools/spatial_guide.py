"""Spatial-control guide provider (additive, CPU-first, provider-neutral).

Studio Bible semantic intent
        -> GenerationSpec spatial fields
        -> SpatialGuideRequest
        -> SpatialGuideProvider.build_guides()
        -> content-addressed SpatialGuideArtifact(s)
        -> ComfyUI structural-conditioning adapter (ControlNet / mask / pose / depth)

This module is strictly ADDITIVE. It does not modify generation_spec.py,
comfyui_adapter.py, or studio_bible_adapter.py. It is the missing
SpatialGuideRequest / SpatialGuideProvider / SpatialGuideArtifact layer that
tools/comfyui_adapter.py:build_workflow currently lacks: that function only
consumes text fields plus externally-supplied refs/masks, and never translates the
typed spatial fields (composition, body_pose, object_geometry, attachment geometry,
occlusion_depth, references) into any structural conditioning.

OpenDesign is intentionally NOT a dependency here:
- M3 froze OPEN_DESIGN_V2_ROLE = NON_RENDERING_DESIGN_SPEC_AND_CRITIQUE_LAYER,
  OPEN_DESIGN_IMAGE_MODE_ALLOWED = NO, OPEN_DESIGN_RENDERING_AUTHORITY = NO.
- Its native vocabulary is web/brand design-system (DESIGN.md), not character-art
  spatial guides (masks / vector / layout / depth / pose). It cannot feed ControlNet.
- No OpenDesign spatial-guide integration code exists in this repo (only plan/metadata
  references with open_design_dependency:false).

Therefore the LOCAL_CPU_REFERENCE_PROVIDER is the default and satisfies the first
CPU causal gate. OpenDesign remains an OPTIONAL, design-intent-only companion that
is never on the ControlNet path.

Determinism / governance:
- Same request -> byte-identical artifacts (no RNG; all geometry derived from request).
- Read-only with respect to Studio Bible canon; output is written only to a caller
  supplied output_dir, never to a canon path.
- Content-addressed (sha256) with provenance and source_request_sha256.
- No private Studio Bible paths leak into artifacts or provenance.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from tools.comfyui_adapter import (
    GUIDE_METADATA_KEY,
    COORDINATE_SPACE_NORMALIZED,
    StructuralGuideBinding,
    WorkflowTemplate,
    attach_structural_guides,
    build_workflow,
)

# --------------------------------------------------------------------------- #
# Typed spatial request (reuses GenerationSpec spatial intent, additive)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Region:
    """Normalized (0..1) relative layout primitive.

    This is a DETERMINISTIC LAYOUT CONVENTION, not canon geometry. Canon supplies
    the semantic facts (subject identity, effect presence, object attachment); the
    normalized rect/ellipse is a plumbing convention for structural-control tests.
    """

    label: str
    shape: str  # "rect" | "ellipse"
    x: float
    y: float
    w: float
    h: float
    zone: str = ""  # optional semantic zone, e.g. "chest", "torso", "arms"


@dataclass(frozen=True)
class SpatialGuideRequest:
    request_id: str
    novel: str
    character_id: str
    scene_id: str
    chapter: str
    width: int
    height: int
    camera_framing: str
    subject_regions: Tuple[Region, ...] = ()
    object_regions: Tuple[Region, ...] = ()
    object_attachments: Tuple[Tuple[str, str], ...] = ()  # (object_label, subject_label)
    contact_regions: Tuple[Region, ...] = ()  # hilt/anchor subregions (blade<->hand/hip)
    effect_regions: Tuple[Region, ...] = ()
    effect_origin: str = ""
    effect_target: str = ""
    effect_extent: str = ""
    depth_layers: Tuple[Tuple[str, float], ...] = ()  # (label, depth 0=near..1=far)
    pose: str = ""
    environment_regions: Tuple[Region, ...] = ()
    forbidden_regions: Tuple[str, ...] = ()  # labels that must be ABSENT (e.g. "weapon")
    constraints: str = ""
    seed: int = 1_000_003
    canon_snapshot_hash: str = ""

    def sha256(self) -> str:
        """Content address of the request (deterministic, no path leakage)."""
        return hashlib.sha256(
            json.dumps(_to_jsonable(self), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class SpatialGuideArtifact:
    provider: str
    guide_type: str  # layout | mask | pose | depth
    path: str
    sha256: str
    width: int
    height: int
    mime: str
    deterministic: bool
    source_request_sha256: str
    provenance: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Canonical structural-guide reference (single owner)
# --------------------------------------------------------------------------- #

STRUCTURAL_GUIDE_URI_SCHEME = "spatial_guide"


def structural_guide_reference(artifact: SpatialGuideArtifact) -> str:
    """Canonical, host-independent, content-addressed structural-guide reference.

    This is the SINGLE owner of the reference form embedded in a workflow. The
    artifact's on-disk ``path`` is deliberately NOT used: workflow identity must
    be reproducible across hosts and output directories, so the reference is
    derived only from the guide TYPE and the artifact's content hash. Two
    byte-identical guides therefore produce the same reference (and the same
    workflow hash) regardless of where they were materialized, while any change
    to the guide bytes changes the reference.
    """
    return (
        f"{STRUCTURAL_GUIDE_URI_SCHEME}://{artifact.guide_type}/{artifact.sha256}.png"
    )


# --------------------------------------------------------------------------- #
# Provider abstraction (provider-neutral)
# --------------------------------------------------------------------------- #


class SpatialGuideProvider:
    """Build deterministic spatial guide artifacts from a request.

    A provider MUST be:
      - deterministic (same request -> identical artifact bytes),
      - read-only w.r.t. Studio Bible canon,
      - content-addressed with provenance,
      - leak-free (no private canon paths in artifacts/provenance),
      - swappable (ComfyUI does not care which provider produced the artifact).
    """

    def build_guides(
        self, request: SpatialGuideRequest, output_dir: Path
    ) -> Tuple[SpatialGuideArtifact, ...]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Local deterministic CPU reference provider (always available)
# --------------------------------------------------------------------------- #


def _label_color(label: str) -> Tuple[int, int, int]:
    """Stable color from label hash (deterministic, no external palette)."""
    h = hashlib.sha256(label.encode("utf-8")).digest()
    return (h[0], h[1], h[2])


def _region_px(r: Region, w: int, h: int):
    x0 = int(r.x * w)
    y0 = int(r.y * h)
    x1 = int((r.x + r.w) * w)
    y1 = int((r.y + r.h) * h)
    return x0, y0, x1, y1


class LocalCpuReferenceProvider(SpatialGuideProvider):
    """Deterministic CPU provider producing layout / mask / pose / depth PNGs.

    Uses only PIL. No GPU, no network, no model. Geometry is derived purely from
    the request (normalized regions), so output is byte-identical for equal input.
    """

    name = "local_cpu_reference"

    def build_guides(
        self, request: SpatialGuideRequest, output_dir: Path
    ) -> Tuple[SpatialGuideArtifact, ...]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        req_hash = request.sha256()
        w, h = request.width, request.height

        artifacts: Tuple[SpatialGuideArtifact, ...] = (
            self._build_layout(request, output_dir, req_hash, w, h),
            self._build_mask(request, output_dir, req_hash, w, h),
            self._build_pose(request, output_dir, req_hash, w, h),
            self._build_depth(request, output_dir, req_hash, w, h),
        )
        return artifacts

    # -- artifact builders -------------------------------------------------- #

    def _build_layout(self, req, out, req_hash, w, h) -> SpatialGuideArtifact:
        img = Image.new("RGB", (w, h), (128, 128, 128))
        d = ImageDraw.Draw(img)
        all_regions = (
            list(req.subject_regions)
            + list(req.object_regions)
            + list(req.effect_regions)
            + list(req.environment_regions)
        )
        for r in all_regions:
            color = _label_color(r.label)
            box = _region_px(r, w, h)
            if r.shape == "ellipse":
                d.ellipse(box, fill=color)
            else:
                d.rectangle(box, fill=color)
        return self._save(img, "layout", out, req_hash, w, h, req.sha256())

    def _build_mask(self, req, out, req_hash, w, h) -> SpatialGuideArtifact:
        img = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(img)
        fg = (
            list(req.subject_regions)
            + list(req.object_regions)
            + list(req.effect_regions)
        )
        for r in fg:
            box = _region_px(r, w, h)
            if r.shape == "ellipse":
                d.ellipse(box, fill=255)
            else:
                d.rectangle(box, fill=255)
        return self._save(img, "mask", out, req_hash, w, h, req.sha256())

    def _build_pose(self, req, out, req_hash, w, h) -> SpatialGuideArtifact:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        if req.pose:
            # Deterministic stick figure: head + spine + arms (no RNG).
            cx = int(0.5 * w)
            head_y = int(0.22 * h)
            torso_top = int(0.30 * h)
            torso_bot = int(0.62 * h)
            d.ellipse([cx - 18, head_y - 18, cx + 18, head_y + 18], outline=(255, 255, 255), width=3)
            d.line([(cx, head_y + 18), (cx, torso_bot)], fill=(255, 255, 255), width=3)
            d.line([(cx, torso_top), (int(0.30 * w), torso_top + int(0.10 * h))], fill=(255, 255, 255), width=3)
            d.line([(cx, torso_top), (int(0.70 * w), torso_top + int(0.10 * h))], fill=(255, 255, 255), width=3)
            d.line([(cx, torso_bot), (int(0.40 * w), int(0.92 * h))], fill=(255, 255, 255), width=3)
            d.line([(cx, torso_bot), (int(0.60 * w), int(0.92 * h))], fill=(255, 255, 255), width=3)
        return self._save(img, "pose", out, req_hash, w, h, req.sha256())

    def _build_depth(self, req, out, req_hash, w, h) -> SpatialGuideArtifact:
        # Near (depth 0) -> bright; far (depth 1) -> dark. Draw far layers first as
        # background, then near layers on top, so the subject reads as foreground.
        img = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(img)
        layers = sorted(req.depth_layers, key=lambda t: -t[1])  # far first
        for label, depth in layers:
            shade = int(255 * (1.0 - depth))
            region = next((r for r in list(req.subject_regions) + list(req.object_regions) + list(req.effect_regions) if r.label == label), None)
            if region is None:
                continue
            box = _region_px(region, w, h)
            if region.shape == "ellipse":
                d.ellipse(box, fill=shade)
            else:
                d.rectangle(box, fill=shade)
        return self._save(img, "depth", out, req_hash, w, h, req.sha256())

    def _save(self, img, guide_type, out, req_hash, w, h, src_req_hash) -> SpatialGuideArtifact:
        fname = f"{guide_type}_{req_hash[:16]}.png"
        path = out / fname
        img.save(path, format="PNG")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        return SpatialGuideArtifact(
            provider=self.name,
            guide_type=guide_type,
            path=str(path),
            sha256=sha,
            width=w,
            height=h,
            mime="image/png",
            deterministic=True,
            source_request_sha256=src_req_hash,
            provenance={
                "provider": self.name,
                "guide_type": guide_type,
                "request_sha256": src_req_hash,
                "no_canon_path_leak": True,
            },
        )


# --------------------------------------------------------------------------- #
# Deterministic CPU pose guide provider (OpenPose-18, prescriptive)
# --------------------------------------------------------------------------- #
# This is a PRESCRIPTIVE pose provider. It does NOT estimate pose from an image
# (no DWPose / SDPose / controlnet_aux / CUDA / cloud). It describes the DESIRED
# pose from canonical structured intent (SpatialGuideRequest / BodyPoseSpec
# descriptive tokens) using a deterministic, normalized OpenPose-18 skeleton.
#
# CANON FACTS consumed (read-only):
#   - subject identity (character_id)
#   - weapon presence/absence (forbidden_regions, object_geometry) -> the skeleton
#     is BODY-ONLY and never encodes an object/weapon keypoint; the mask/regional
#     layer owns object geometry. So forbidden object data cannot leak into the
#     pose skeleton, and wrong-novel object data cannot leak either.
#   - the descriptive pose token (request.pose), used only to select a
#     deterministic skeleton PRESET.
#
# LAYOUT CONVENTIONS (explicitly NOT canon): the exact normalized joint
# coordinates, skeleton proportions, joint ordering, line widths, colors, and
# canvas size. These are plumbing for a future OpenPose ControlNet consumer.
#
# The provider is provider-neutral: ComfyUI does not care which provider produced
# the artifact; the artifact is content-addressed and leak-free.

# OpenPose-18 (COCO-18 body) joint schema. Order is canonical OpenPose semantics:
# index 2/3/4/8/9/10/14/16 are the SUBJECT'S RIGHT side (appears on the left of a
# front-facing image); 5/6/7/11/12/13/15/17 are the SUBJECT'S LEFT side.
OPENPOSE18_JOINT_NAMES: Tuple[str, ...] = (
    "nose",          # 0
    "neck",          # 1
    "right_shoulder",# 2
    "right_elbow",   # 3
    "right_wrist",   # 4
    "left_shoulder", # 5
    "left_elbow",    # 6
    "left_wrist",    # 7
    "right_hip",     # 8
    "right_knee",    # 9
    "right_ankle",   # 10
    "left_hip",      # 11
    "left_knee",     # 12
    "left_ankle",    # 13
    "right_eye",     # 14
    "left_eye",      # 15
    "right_ear",     # 16
    "left_ear",      # 17
)
OPENPOSE18_JOINT_COUNT = len(OPENPOSE18_JOINT_NAMES)  # 18

# Deterministic skeleton edges (limb connections) in OpenPose-18 semantics.
OPENPOSE18_LIMB_EDGES: Tuple[Tuple[int, int], ...] = (
    (0, 1),    # nose - neck
    (1, 2),    # neck - right_shoulder
    (1, 5),    # neck - left_shoulder
    (2, 3),    # right_shoulder - right_elbow
    (3, 4),    # right_elbow - right_wrist
    (5, 6),    # left_shoulder - left_elbow
    (6, 7),    # left_elbow - left_wrist
    (1, 8),    # neck - right_hip
    (8, 9),    # right_hip - right_knee
    (9, 10),   # right_knee - right_ankle
    (1, 11),   # neck - left_hip
    (11, 12),  # left_hip - left_knee
    (12, 13),  # left_knee - left_ankle
    (0, 14),   # nose - right_eye
    (14, 16),  # right_eye - right_ear
    (0, 15),   # nose - left_eye
    (15, 17),  # left_eye - left_ear
    (14, 15),  # right_eye - left_eye (bridge)
)

# Fixed deterministic per-limb colors (OpenPose-style). Index aligns with
# OPENPOSE18_LIMB_EDGES order. No RNG; stable across hosts.
_OPENPOSE18_LIMB_COLORS: Tuple[Tuple[int, int, int], ...] = (
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
    (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
    (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255),
    (255, 0, 170), (255, 0, 85),
)

# Fixed canvas/rendering constants (LAYOUT CONVENTION, deterministic).
_POSE_CANVAS_BG = (0, 0, 0)
_POSE_KEYPOINT_COLOR = (255, 255, 255)
_POSE_KEYPOINT_RADIUS = 4
_POSE_LIMB_WIDTH = 3
_POSE_DEFAULT_CANVAS_W = 512
_POSE_DEFAULT_CANVAS_H = 1024

# --------------------------------------------------------------------------- #
# OpenPose HAND keypoint schema (21 per hand) — hand/object interaction channel
# --------------------------------------------------------------------------- #
# WHY THIS EXISTS (causal, not cosmetic): the body-only OpenPose-18 skeleton has
# the wrist as a TERMINAL joint. It therefore cannot express "these finger joints
# occupy this geometry and wrap around this specific hilt/contact region". The
# rendered causal A/B confirmed the consequence: body pose improved, but the
# Soulblade grip did not (EN_SOULBLADE_GRIP_SOLVED=NO). This section adds the
# missing hand/finger channel to the SAME prescriptive pose guide, consumed by
# the SAME already-qualified OpenPose ControlNet binding. It is NOT a hand
# "detailer" and it does NOT repaint anything.
#
# CONVENTION SOURCE (verified read-only, no install, no download): the locally
# installed ComfyUI 0.33.2 core module ``comfy_extras/nodes_sdpose.py`` defines
# the canonical OpenPose/DWPose-style hand representation used by this backend:
#   - 21 keypoints per hand (root/wrist at index 0, then thumb, index, middle,
#     ring, pinky, 4 joints each),
#   - 20 hand edges (``KeypointDraw.hand_edges``),
#   - per-edge HSV rainbow colours ``hsv_to_rgb(edge_index / 20, 1.0, 1.0)``,
#   - hand edge line thickness 2, hand keypoint dot radius 4, dot colour (0,0,255).
# We reproduce that convention here on CPU with PIL so no custom node, no pose
# estimator, and no model weight download is required.
OPENPOSE_HAND_KEYPOINT_NAMES: Tuple[str, ...] = (
    "hand_root",     # 0  (coincides with the body wrist joint)
    "thumb_cmc",     # 1
    "thumb_mcp",     # 2
    "thumb_ip",      # 3
    "thumb_tip",     # 4
    "index_mcp",     # 5
    "index_pip",     # 6
    "index_dip",     # 7
    "index_tip",     # 8
    "middle_mcp",    # 9
    "middle_pip",    # 10
    "middle_dip",    # 11
    "middle_tip",    # 12
    "ring_mcp",      # 13
    "ring_pip",      # 14
    "ring_dip",      # 15
    "ring_tip",      # 16
    "pinky_mcp",     # 17
    "pinky_pip",     # 18
    "pinky_dip",     # 19
    "pinky_tip",     # 20
)
OPENPOSE_HAND_KEYPOINT_COUNT = len(OPENPOSE_HAND_KEYPOINT_NAMES)  # 21

# Exactly ComfyUI core ``KeypointDraw.hand_edges`` (20 edges).
OPENPOSE_HAND_EDGES: Tuple[Tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),        # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # index
    (0, 9), (9, 10), (10, 11), (11, 12),   # middle
    (0, 13), (13, 14), (14, 15), (15, 16), # ring
    (0, 17), (17, 18), (18, 19), (19, 20), # pinky
)


def _openpose_hand_edge_colors() -> Tuple[Tuple[int, int, int], ...]:
    """Per-edge hand colours, exactly the ComfyUI-core HSV rainbow convention.

    Pure arithmetic (``colorsys`` stdlib), no RNG, no host state, so the result
    is byte-stable across hosts and runs.
    """
    import colorsys

    n = len(OPENPOSE_HAND_EDGES)
    out = []
    for i in range(n):
        r, g, b = colorsys.hsv_to_rgb(i / float(n), 1.0, 1.0)
        out.append((int(r * 255), int(g * 255), int(b * 255)))
    return tuple(out)


_OPENPOSE_HAND_EDGE_COLORS: Tuple[Tuple[int, int, int], ...] = _openpose_hand_edge_colors()
_HAND_KEYPOINT_COLOR = (0, 0, 255)
_HAND_KEYPOINT_RADIUS = 4
_HAND_LIMB_WIDTH = 2

# Deterministic GRIP hand template (LAYOUT CONVENTION, NOT canon geometry).
#
# Local frame: origin (0,0) is the CENTRE of the contact/hilt region; +x is
# image-right, +y is image-down; units are multiples of the hilt scale. The
# template is authored for the SUBJECT'S LEFT hand (which appears on the
# image-right side of a front-facing subject) gripping a vertically oriented
# hilt: the metacarpal knuckles (5/9/13/17) sit OUTBOARD of the hilt at +x, the
# four fingers stack vertically along the hilt, each finger curls ACROSS the
# hilt to -x so the fingertips (8/12/16/20) land on the far side, and the thumb
# (1..4) crosses over the front of the fingers. Mirroring x yields the subject's
# right hand.
#
# The encoded relationship is therefore explicit and structural: the finger
# joints straddle the hilt/contact region, rather than merely being adjacent
# to it.
_GRIP_HAND_TEMPLATE: Tuple[Tuple[float, float], ...] = (
    (0.58, 0.90),    # 0  hand_root (wrist; below the hilt, on the forearm axis)
    (0.48, 0.55),    # 1  thumb_cmc
    (0.32, 0.30),    # 2  thumb_mcp
    (0.12, 0.14),    # 3  thumb_ip
    (-0.08, 0.04),   # 4  thumb_tip  (crossed over the front of the hilt)
    (0.42, -0.34),   # 5  index_mcp  (outboard knuckle, highest finger)
    (0.12, -0.44),   # 6  index_pip
    (-0.12, -0.42),  # 7  index_dip
    (-0.30, -0.30),  # 8  index_tip  (wrapped to the far side)
    (0.46, -0.11),   # 9  middle_mcp
    (0.14, -0.20),   # 10 middle_pip
    (-0.12, -0.18),  # 11 middle_dip
    (-0.32, -0.06),  # 12 middle_tip
    (0.46, 0.12),    # 13 ring_mcp
    (0.15, 0.04),    # 14 ring_pip
    (-0.10, 0.06),   # 15 ring_dip
    (-0.28, 0.17),   # 16 ring_tip
    (0.44, 0.34),    # 17 pinky_mcp (lowest finger)
    (0.18, 0.27),    # 18 pinky_pip
    (-0.04, 0.29),   # 19 pinky_dip
    (-0.18, 0.38),   # 20 pinky_tip
)

# Indices whose x is scaled by ``finger_wrap`` relative to their metacarpal
# knuckle, so the wrap amount is an EXPLICIT causal parameter rather than a
# baked constant. (thumb is measured from the hand root.)
_HAND_WRAP_CHAINS: Tuple[Tuple[int, Tuple[int, ...]], ...] = (
    (0, (1, 2, 3, 4)),        # thumb chain, measured from hand_root
    (5, (6, 7, 8)),           # index
    (9, (10, 11, 12)),        # middle
    (13, (14, 15, 16)),       # ring
    (17, (18, 19, 20)),       # pinky
)

# Sanctioned STARTING magnitudes for the hand-interaction control. These mirror
# the existing OpenPose runtime-parameter governance pattern: they are explicit
# and deterministic (not RNG, not invented per-call), but the magnitudes require
# authority confirmation in the bounded GPU causal stage before being treated as
# production values. Nothing consumes them implicitly: a caller must construct
# HandInteractionParams explicitly, otherwise hand control stays OFF.
HAND_INTERACTION_PARAMETERS_REQUIRE_AUTHORITY = True
EN_HAND_INTERACTION_SANCTIONED_GRIP_HAND = "left"
EN_HAND_INTERACTION_SANCTIONED_HAND_SPAN = 1.25
EN_HAND_INTERACTION_SANCTIONED_FINGER_WRAP = 1.0
EN_HAND_INTERACTION_SANCTIONED_REANCHOR_WRIST = True

_GRIP_HAND_SIDES = ("left", "right")
# OpenPose-18 body indices for each side's (shoulder, elbow, wrist).
_BODY_ARM_INDICES: Dict[str, Tuple[int, int, int]] = {
    "right": (2, 3, 4),
    "left": (5, 6, 7),
}

# Deterministic skeleton PRESETS (LAYOUT CONVENTION). The canon fact is only
# which preset NAME is selected (request.pose token); the joint coordinates
# themselves are NOT canon geometry. Additive presets are permitted; inventing
# new canon facts is NOT.
_POSE_PRESETS: Dict[str, Tuple[Tuple[float, float], ...]] = {
    # Neutral standing front-facing humanoid (default).
    "neutral": (
        (0.50, 0.12),  # nose
        (0.50, 0.18),  # neck
        (0.42, 0.22),  # right_shoulder
        (0.37, 0.34),  # right_elbow
        (0.33, 0.46),  # right_wrist
        (0.58, 0.22),  # left_shoulder
        (0.63, 0.34),  # left_elbow
        (0.67, 0.46),  # left_wrist
        (0.44, 0.52),  # right_hip
        (0.43, 0.70),  # right_knee
        (0.42, 0.88),  # right_ankle
        (0.56, 0.52),  # left_hip
        (0.57, 0.70),  # left_knee
        (0.58, 0.88),  # left_ankle
        (0.47, 0.10),  # right_eye
        (0.53, 0.10),  # left_eye
        (0.44, 0.11),  # right_ear
        (0.56, 0.11),  # left_ear
    ),
    # Wielding / hand-grip posture: right wrist lowered toward the hip grip
    # anchor to support a hand-held object attachment. The object geometry
    # itself remains owned by the mask/regional layer; the skeleton only
    # exposes the hand/hip anchor joints. LAYOUT CONVENTION.
    "wielding": (
        (0.50, 0.12),
        (0.50, 0.18),
        (0.42, 0.22),
        (0.40, 0.40),  # right_elbow lowered
        (0.47, 0.56),  # right_wrist near hip grip
        (0.58, 0.22),
        (0.63, 0.34),
        (0.67, 0.46),
        (0.44, 0.52),
        (0.43, 0.70),
        (0.42, 0.88),
        (0.56, 0.52),
        (0.57, 0.70),
        (0.58, 0.88),
        (0.47, 0.10),
        (0.53, 0.10),
        (0.44, 0.11),
        (0.56, 0.11),
    ),
}


@dataclass(frozen=True)
class HandInteractionParams:
    """EXPLICIT, fully-required hand/object interaction control parameters.

    There are deliberately NO field defaults: a caller that wants hand-aware
    structural control must state every value, so no silent default can change
    the causal interpretation of a rendered result. Passing ``None`` for
    hand interaction anywhere in this module means OFF, which is the previously
    qualified body-only behaviour and is byte/hash identical to it.

    grip_hand        "left" | "right" (the SUBJECT'S side, OpenPose semantics)
    hand_span        >0 multiplier applied to the contact/hilt region size
    finger_wrap      0..1 how far the finger joints curl ACROSS the hilt
    reanchor_wrist   when True, the grip-side body wrist is moved onto the hand
                     root and the elbow is re-interpolated, so the hand provably
                     belongs to the posed subject instead of floating
    """

    grip_hand: str
    hand_span: float
    finger_wrap: float
    reanchor_wrist: bool

    def validate(self) -> None:
        if self.grip_hand not in _GRIP_HAND_SIDES:
            raise ValueError(
                f"HandInteractionParams.grip_hand must be one of {list(_GRIP_HAND_SIDES)}: "
                f"got {self.grip_hand!r}"
            )
        if not (self.hand_span > 0.0):
            raise ValueError(
                f"HandInteractionParams.hand_span must be > 0: got {self.hand_span!r}"
            )
        if not (0.0 <= self.finger_wrap <= 1.0):
            raise ValueError(
                f"HandInteractionParams.finger_wrap must be within [0,1]: "
                f"got {self.finger_wrap!r}"
            )
        if not isinstance(self.reanchor_wrist, bool):
            raise ValueError(
                f"HandInteractionParams.reanchor_wrist must be a bool: "
                f"got {self.reanchor_wrist!r}"
            )


def en_sanctioned_hand_interaction_params() -> HandInteractionParams:
    """The SINGLE canonical owner of the qualified EN grip parameter set.

    Callers (experiment harnesses, qualification runs, tests) MUST obtain the
    qualified EN hand-interaction contract from here instead of re-typing
    magnitudes, because hand-written literals are exactly how the first bounded
    GPU causal test silently ran a sub-sanctioned grip (hand_span=1.0,
    finger_wrap=0.6) and produced an unreadable partial wrap.

    The values themselves stay in the existing
    ``EN_HAND_INTERACTION_SANCTIONED_*`` constants above (no new magic numbers);
    this function only binds them into the explicit params object. It remains
    OPT-IN and provider-neutral: nothing consumes it implicitly, so hand control
    is still OFF unless a caller asks for it.
    """
    return HandInteractionParams(
        grip_hand=EN_HAND_INTERACTION_SANCTIONED_GRIP_HAND,
        hand_span=EN_HAND_INTERACTION_SANCTIONED_HAND_SPAN,
        finger_wrap=EN_HAND_INTERACTION_SANCTIONED_FINGER_WRAP,
        reanchor_wrist=EN_HAND_INTERACTION_SANCTIONED_REANCHOR_WRIST,
    )


def is_en_sanctioned_hand_interaction(
    params: Optional[HandInteractionParams],
) -> bool:
    """True only when ``params`` is exactly the qualified EN grip contract.

    Mechanical gate for harnesses/tests: a sub-sanctioned substitution (e.g.
    hand_span=1.0 / finger_wrap=0.6) is detectable rather than silently accepted.
    """
    if params is None:
        return False
    return params == en_sanctioned_hand_interaction_params()


@dataclass(frozen=True)
class HandKeypoints:
    """One deterministic 21-keypoint OpenPose hand, anchored to a contact region.

    ``anchor_label`` names the contact/hilt region the hand was derived from, and
    ``anchor_geometry`` carries that region's normalized rect, so the encoded
    relationship ("these finger joints wrap THIS hilt") is inspectable and
    participates in the content hash.
    """

    side: str
    keypoints: Tuple[Tuple[float, float], ...]  # length 21, each (x, y) in [0,1]
    anchor_label: str
    anchor_geometry: Tuple[float, float, float, float]  # (x, y, w, h) normalized
    grip_hand_belongs_to: str = ""  # subject the hand is attached to
    hand_span: float = 0.0
    finger_wrap: float = 0.0

    def to_json(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "keypoint_names": list(OPENPOSE_HAND_KEYPOINT_NAMES),
            "keypoints": [[x, y] for (x, y) in self.keypoints],
            "anchor_label": self.anchor_label,
            "anchor_geometry": list(self.anchor_geometry),
            "grip_hand_belongs_to": self.grip_hand_belongs_to,
            "hand_span": self.hand_span,
            "finger_wrap": self.finger_wrap,
        }


@dataclass(frozen=True)
class NormalizedPose:
    """Deterministic, serialization-independent OpenPose joint set.

    Coordinates are normalized to x,y in [0,1] so the serialized form is
    independent of output resolution. Joint ordering is the canonical
    OpenPose-18 order (see OPENPOSE18_JOINT_NAMES).

    ``hands`` is the OPTIONAL hand/object-interaction channel (21 OpenPose hand
    keypoints per hand). When it is empty the serialization, the content hash,
    and the rendered PNG are byte-identical to the pre-hand contract, so the
    previously qualified body-only path is provably unchanged.
    """

    joints: Tuple[Tuple[float, float], ...]  # length 18, each (x, y) in [0,1]
    pose_token: str = ""
    coordinate_space: str = "normalized_0_1"
    hands: Tuple[HandKeypoints, ...] = ()

    def sha256(self) -> str:
        payload: Dict[str, Any] = {
            "coordinate_space": self.coordinate_space,
            "pose_token": self.pose_token,
            "joints": [[round(x, 6), round(y, 6)] for (x, y) in self.joints],
        }
        # Only present when hand control is ON, so the body-only hash is stable.
        if self.hands:
            payload["hands"] = [
                {
                    "side": h.side,
                    "anchor_label": h.anchor_label,
                    "anchor_geometry": [round(v, 6) for v in h.anchor_geometry],
                    "hand_span": round(h.hand_span, 6),
                    "finger_wrap": round(h.finger_wrap, 6),
                    "keypoints": [[round(x, 6), round(y, 6)] for (x, y) in h.keypoints],
                }
                for h in self.hands
            ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "coordinate_space": self.coordinate_space,
            "pose_token": self.pose_token,
            "joint_names": list(OPENPOSE18_JOINT_NAMES),
            "joints": [[x, y] for (x, y) in self.joints],
        }
        if self.hands:
            out["hands"] = [h.to_json() for h in self.hands]
        return out


# Canonical pose token contract (single owner: derive_normalized_pose).
#   - unspecified (None / "" / whitespace) -> neutral default (established contract)
#   - explicit aliases -> canonical preset name (preserve prior mapping)
#   - canonical presets -> their own geometry
#   - any other explicit value is genuinely unrecognized and FAILS CLOSED.
_POSE_TOKEN_ALIASES: Dict[str, str] = {
    "standing": "neutral",
    "stable": "neutral",
    "default": "neutral",
}
_POSE_CANONICAL_TOKENS = frozenset(_POSE_PRESETS.keys())  # {"neutral", "wielding"}
_POSE_SUPPORTED_TOKENS = frozenset(_POSE_CANONICAL_TOKENS | set(_POSE_TOKEN_ALIASES.keys()))


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def derive_hand_keypoints(
    request: SpatialGuideRequest,
    params: HandInteractionParams,
) -> HandKeypoints:
    """Deterministically derive one 21-keypoint OpenPose grip hand (FAIL CLOSED).

    The hand is derived FROM the request's contact/hilt region and the object
    attachment, so the produced geometry encodes the required contract:

        "this hand belongs to <subject>, these hand/finger joints occupy this
         geometry, and they interact with this specific <object> hilt/contact
         region."

    FAIL-CLOSED GUARDS (these are what keep HA clean):
      - a contact/hilt region MUST exist,
      - an object attachment MUST exist and MUST resolve to the request subject,
      - the request MUST NOT forbid a weapon/object.
    A request with no physical object (e.g. HA: no Soulblade, forbidden weapon,
    no contact region) therefore CANNOT be given hand/hilt interaction geometry,
    even if a caller asks for it — it raises instead of silently producing a
    plausible-but-wrong grip.
    """
    params.validate()

    if not request.contact_regions:
        raise ValueError(
            "hand-interaction control requires a contact/hilt region: this "
            "request carries none, so a hand-to-hilt relationship cannot be "
            "represented (no EN hand/Soulblade geometry may be synthesized for "
            "a request without a physical contact anchor)"
        )
    if not request.object_attachments:
        raise ValueError(
            "hand-interaction control requires an object attachment so the hand "
            "provably belongs to the posed subject: this request carries none"
        )
    if request.forbidden_regions:
        raise ValueError(
            f"hand-interaction control refused: request forbids "
            f"{list(request.forbidden_regions)!r}, so it must not receive "
            f"held-object grip geometry"
        )

    contact = request.contact_regions[0]
    obj_label, subject_label = request.object_attachments[0]
    if subject_label != request.character_id:
        raise ValueError(
            f"hand-interaction attachment target {subject_label!r} does not match "
            f"the request subject {request.character_id!r}; refusing to attach a "
            f"grip hand to a different subject"
        )

    cx = contact.x + contact.w / 2.0
    cy = contact.y + contact.h / 2.0
    # Isotropic scale (no aspect distortion) driven by the hilt region size.
    scale = float(params.hand_span) * max(float(contact.w), float(contact.h))
    mirror = -1.0 if params.grip_hand == "right" else 1.0
    wrap = float(params.finger_wrap)

    local = [list(pt) for pt in _GRIP_HAND_TEMPLATE]
    # Apply the explicit wrap factor: distal joints interpolate between their
    # own knuckle's x and the template's fully-wrapped x.
    for base_idx, chain in _HAND_WRAP_CHAINS:
        base_x = _GRIP_HAND_TEMPLATE[base_idx][0]
        for idx in chain:
            tx = _GRIP_HAND_TEMPLATE[idx][0]
            local[idx][0] = base_x + wrap * (tx - base_x)

    keypoints = tuple(
        (
            _clamp01(cx + mirror * lx * scale),
            _clamp01(cy + ly * scale),
        )
        for (lx, ly) in local
    )

    return HandKeypoints(
        side=params.grip_hand,
        keypoints=keypoints,
        anchor_label=contact.label,
        anchor_geometry=(
            float(contact.x), float(contact.y), float(contact.w), float(contact.h)
        ),
        grip_hand_belongs_to=subject_label,
        hand_span=float(params.hand_span),
        finger_wrap=wrap,
    )


def _reanchor_arm_to_hand(
    joints: Tuple[Tuple[float, float], ...],
    hand: HandKeypoints,
) -> Tuple[Tuple[float, float], ...]:
    """Move the grip-side body wrist onto the hand root; re-interpolate the elbow.

    This is the linkage that makes the hand belong to the POSED SUBJECT rather
    than being an unattached hand drawing: the OpenPose-18 wrist joint and the
    OpenPose hand root become the same point, and the elbow is placed on the
    shoulder->wrist midpoint so the limb chain stays connected.
    """
    sh_i, el_i, wr_i = _BODY_ARM_INDICES[hand.side]
    out = [list(p) for p in joints]
    root_x, root_y = hand.keypoints[0]
    out[wr_i] = [root_x, root_y]
    sx, sy = joints[sh_i]
    out[el_i] = [
        _clamp01((sx + root_x) / 2.0),
        _clamp01((sy + root_y) / 2.0),
    ]
    return tuple((float(x), float(y)) for x, y in out)


def derive_normalized_pose(
    request: SpatialGuideRequest,
    *,
    hand_interaction: Optional[HandInteractionParams] = None,
) -> NormalizedPose:
    """Deterministically derive an OpenPose skeleton from a request.

    CANON INPUT: request.pose token (selects a preset) and the semantic facts
    (character_id, forbidden_regions, object geometry) which GUARANTEE the output
    is body-only and never encodes an object/weapon or wrong-novel data.

    LAYOUT CONVENTION: the joint coordinates come from the selected preset and
    are NOT canon geometry.

    TOKEN CONTRACT (fail closed): an explicitly provided, genuinely unrecognized
    pose token raises ValueError rather than silently resolving to neutral. Only
    the unspecified default ("", None) and the documented aliases/presets are
    accepted, so a typo produces a deterministic, actionable error instead of a
    plausible-but-incorrect guide.

    HAND INTERACTION (opt-in, explicit): when ``hand_interaction`` is None (the
    default) the result is byte-identical to the previously qualified body-only
    contract — same joints, same content hash, same rendered PNG. When it is
    supplied, a 21-keypoint OpenPose hand is derived from the request's
    contact/hilt region (see ``derive_hand_keypoints``) and, if requested, the
    grip-side wrist/elbow are re-anchored onto it. The object/weapon itself is
    still NEVER encoded as a keypoint; the mask/regional layer keeps owning
    object geometry.
    """
    raw = request.pose
    token = (raw or "").strip().lower()
    if token == "":
        token = "neutral"  # unspecified default (established contract)
    elif token in _POSE_TOKEN_ALIASES:
        token = _POSE_TOKEN_ALIASES[token]
    if token not in _POSE_PRESETS:
        raise ValueError(
            f"Unsupported pose token {raw!r}: supported canonical presets are "
            f"{sorted(_POSE_CANONICAL_TOKENS)} and supported aliases are "
            f"{sorted(_POSE_TOKEN_ALIASES)}; an empty/None pose resolves to the "
            f"neutral default"
        )
    preset = _POSE_PRESETS[token]
    if len(preset) != OPENPOSE18_JOINT_COUNT:
        preset = _POSE_PRESETS["neutral"]

    if hand_interaction is None:
        # OFF path: unchanged, byte/hash equivalent to the pre-hand contract.
        return NormalizedPose(joints=preset, pose_token=token)

    hand = derive_hand_keypoints(request, hand_interaction)
    joints = preset
    if hand_interaction.reanchor_wrist:
        joints = _reanchor_arm_to_hand(preset, hand)
    return NormalizedPose(joints=joints, pose_token=token, hands=(hand,))


def _render_openpose_pose_png(
    pose: NormalizedPose,
    width: int,
    height: int,
) -> "Image.Image":
    """Render a deterministic OpenPose skeleton PNG (black bg, colored limbs).

    Deterministic: fixed canvas, fixed background, fixed joint order, fixed line
    widths, fixed colors, deterministic rounding. No timestamps, no RNG, no
    host paths.

    When ``pose.hands`` is empty NOTHING extra is drawn, so the body-only output
    is byte-identical to the pre-hand contract. When hands are present they are
    drawn AFTER the body using the locally installed ComfyUI-core OpenPose hand
    convention (21 keypoints, 20 edges, HSV rainbow edge colours).
    """
    img = Image.new("RGB", (width, height), _POSE_CANVAS_BG)
    draw = ImageDraw.Draw(img)
    pts = [(
        int(round(x * (width - 1))),
        int(round(y * (height - 1))),
    ) for (x, y) in pose.joints]

    for i, (a, b) in enumerate(OPENPOSE18_LIMB_EDGES):
        color = _OPENPOSE18_LIMB_COLORS[i % len(_OPENPOSE18_LIMB_COLORS)]
        draw.line([pts[a], pts[b]], fill=color, width=_POSE_LIMB_WIDTH)

    for (px, py) in pts:
        draw.ellipse(
            [
                px - _POSE_KEYPOINT_RADIUS,
                py - _POSE_KEYPOINT_RADIUS,
                px + _POSE_KEYPOINT_RADIUS,
                py + _POSE_KEYPOINT_RADIUS,
            ],
            fill=_POSE_KEYPOINT_COLOR,
        )

    for hand in pose.hands:
        hpts = [(
            int(round(x * (width - 1))),
            int(round(y * (height - 1))),
        ) for (x, y) in hand.keypoints]
        for i, (a, b) in enumerate(OPENPOSE_HAND_EDGES):
            draw.line(
                [hpts[a], hpts[b]],
                fill=_OPENPOSE_HAND_EDGE_COLORS[i % len(_OPENPOSE_HAND_EDGE_COLORS)],
                width=_HAND_LIMB_WIDTH,
            )
        for (px, py) in hpts:
            draw.ellipse(
                [
                    px - _HAND_KEYPOINT_RADIUS,
                    py - _HAND_KEYPOINT_RADIUS,
                    px + _HAND_KEYPOINT_RADIUS,
                    py + _HAND_KEYPOINT_RADIUS,
                ],
                fill=_HAND_KEYPOINT_COLOR,
            )
    return img


class PoseGuideProvider(SpatialGuideProvider):
    """Deterministic CPU-only provider of a prescriptive OpenPose pose guide.

    Output: a single SpatialGuideArtifact with guide_type="pose". Provider-neutral
    (ComfyUI-agnostic), content-addressed, leak-free, off-safe. Never estimates
    pose from an image; never depends on GPU / network / model weights.

    ``hand_interaction`` is the OPT-IN hand/object interaction structural control.
    It defaults to None, which reproduces the previously qualified body-only
    guide byte-for-byte (same PNG bytes, same sha256, same provenance keys). When
    supplied it MUST be a fully explicit ``HandInteractionParams``.
    """

    name = "pose_guide"
    guide_type = "pose"

    def __init__(self, hand_interaction: Optional[HandInteractionParams] = None):
        self.hand_interaction = hand_interaction

    def build_guides(
        self, request: SpatialGuideRequest, output_dir: Path
    ) -> Tuple[SpatialGuideArtifact, ...]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        req_hash = request.sha256()
        w = int(request.width) if request.width else _POSE_DEFAULT_CANVAS_W
        h = int(request.height) if request.height else _POSE_DEFAULT_CANVAS_H

        pose = derive_normalized_pose(request, hand_interaction=self.hand_interaction)
        img = _render_openpose_pose_png(pose, w, h)

        fname = f"{self.guide_type}_{req_hash[:16]}.png"
        if pose.hands:
            # Distinct on-disk name so a hand-aware guide can never silently
            # overwrite / be mistaken for the body-only guide of the same request.
            fname = f"{self.guide_type}_hand_{req_hash[:16]}.png"
        path = output_dir / fname
        # Deterministic PNG: no pnginfo / timestamps embedded.
        img.save(path, format="PNG")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        provenance: Dict[str, Any] = {
            "provider": self.name,
            "guide_type": self.guide_type,
            "coordinate_space": pose.coordinate_space,
            "pose_token": pose.pose_token,
            "joint_count": OPENPOSE18_JOINT_COUNT,
            "normalized_pose_sha256": pose.sha256(),
            "request_sha256": req_hash,
            "no_canon_path_leak": True,
            "body_only": not bool(pose.hands),
            "object_keypoints": False,
        }
        if pose.hands:
            hand = pose.hands[0]
            provenance.update({
                "hand_keypoints": True,
                "hand_keypoint_count": OPENPOSE_HAND_KEYPOINT_COUNT,
                "hand_edge_count": len(OPENPOSE_HAND_EDGES),
                "grip_hand": hand.side,
                "hand_anchor_label": hand.anchor_label,
                "hand_anchor_geometry": list(hand.anchor_geometry),
                "hand_attached_to_subject": hand.grip_hand_belongs_to,
                "hand_span": hand.hand_span,
                "finger_wrap": hand.finger_wrap,
                "wrist_reanchored": bool(
                    self.hand_interaction is not None
                    and self.hand_interaction.reanchor_wrist
                ),
                "hand_parameters_require_authority": (
                    HAND_INTERACTION_PARAMETERS_REQUIRE_AUTHORITY
                ),
            })
        artifact = SpatialGuideArtifact(
            provider=self.name,
            guide_type=self.guide_type,
            path=str(path),
            sha256=sha,
            width=w,
            height=h,
            mime="image/png",
            deterministic=True,
            source_request_sha256=req_hash,
            provenance=provenance,
        )
        return (artifact,)


def build_pose_guide_from_spec(
    spec: Any,
    *,
    novel: str = "",
    request_id: str = "",
    seed: int = 1_000_003,
    output_dir: Any = None,
    hand_interaction: Optional[HandInteractionParams] = None,
) -> Optional[SpatialGuideArtifact]:
    """Provider-neutral binding: derive a PoseGuideProvider artifact from a spec.

    Returns None when the spec resolves to no subject (Studio Bible OFF), so the
    OFF path produces NO pose node/binding and stays byte-identical to the
    pre-pose contract. ``hand_interaction`` defaults to None (body-only,
    previously qualified behaviour).
    """
    request = build_spatial_guide_request_from_spec(
        spec, novel=novel, request_id=request_id, seed=seed
    )
    if request is None:
        return None
    out = Path(output_dir) if output_dir is not None else Path.cwd() / "pose_guide_out"
    artifacts = PoseGuideProvider(hand_interaction=hand_interaction).build_guides(
        request, out
    )
    return artifacts[0] if artifacts else None


def build_combined_structural_bundle(
    spec: Any,
    output_dir: Any,
    *,
    novel: str = "",
    request_id: str = "",
    seed: int = 1_000_003,
    hand_interaction: Optional[HandInteractionParams] = None,
    hand_hilt_isolation: bool = False,
) -> Optional[StructuralGuideBundle]:
    """Provider-neutral bundle: mask/regional guides + pose guide coexist.

    Uses LocalCpuReferenceProvider for layout/mask/depth (its crude pose is
    excluded to avoid a duplicate pose) and PoseGuideProvider for the OpenPose-18
    pose artifact. Returns None on the OFF path (no subject), preserving OFF
    behavior. Proves pose and mask/regional artifacts can share one bundle and
    one set of structural bindings.

    ``hand_interaction`` defaults to None, i.e. the previously qualified
    body-only pose channel; the mask/regional guides are untouched either way.
    """
    request = build_spatial_guide_request_from_spec(
        spec, novel=novel, request_id=request_id, seed=seed,
        hand_hilt_isolation=hand_hilt_isolation,
    )
    if request is None:
        return None
    out = Path(output_dir)
    out_local = out / "local"
    out_pose = out / "pose"
    local_arts = [
        a for a in LocalCpuReferenceProvider().build_guides(request, out_local)
        if a.guide_type != "pose"
    ]
    pose_arts = PoseGuideProvider(hand_interaction=hand_interaction).build_guides(
        request, out_pose
    )
    artifacts = tuple(local_arts) + tuple(pose_arts)
    return StructuralGuideBundle(request=request, artifacts=artifacts)


# --------------------------------------------------------------------------- #
# ComfyUI wiring (additive; does not modify comfyui_adapter.build_workflow)
# --------------------------------------------------------------------------- #

_GUIDE_TYPE_TO_SEMANTIC = {
    "layout": "controlnet_image",
    "mask": "mask_image",
    "pose": "pose_image",
    "depth": "depth_image",
}


def augment_template_with_guide_inputs(template: WorkflowTemplate) -> WorkflowTemplate:
    """Return a NEW template that adds guide-input nodes + semantic_inputs.

    The existing base workflows (e.g. realistic_base.json) intentionally lack
    ControlNet / mask / pose / depth nodes (DISABLED_FOR_BASE_PROFILE). This makes
    the missing structural-control path explicit and writable for the CPU gate
    without mutating the live ComfyUI install or the base template files.
    """
    import copy

    nodes = copy.deepcopy(dict(template.nodes))
    semantic = dict(template.semantic_inputs)
    idx = 900
    for guide_type, semantic_key in _GUIDE_TYPE_TO_SEMANTIC.items():
        node_id = f"guide_{guide_type}"
        if node_id not in nodes:
            nodes[node_id] = {
                "class_type": "GuideImageReference",
                "inputs": {"image": ""},
            }
        semantic[semantic_key] = {"node": node_id, "input": "image"}
        idx += 1
    return WorkflowTemplate(
        template_id=template.template_id,
        version=template.version,
        description=template.description,
        nodes=nodes,
        semantic_inputs=semantic,
        sha256=template.sha256,
    )


def attach_guides(
    workflow_nodes: Dict[str, Any],
    template: WorkflowTemplate,
    artifacts: Tuple[SpatialGuideArtifact, ...],
) -> None:
    """Inject canonical guide references into the augmented workflow (in place).

    Uses ``structural_guide_reference`` (the same content-addressed form the
    canonical ``build_structural_bindings`` boundary emits), NOT the artifact's
    on-disk path, so the resulting workflow identity is host-independent and
    output-dir-independent.
    """
    for art in artifacts:
        semantic_key = _GUIDE_TYPE_TO_SEMANTIC.get(art.guide_type)
        if not semantic_key:
            continue
        mapping = template.semantic_inputs.get(semantic_key)
        if not mapping:
            continue
        node_id = mapping["node"]
        if node_id not in workflow_nodes:
            continue
        workflow_nodes[node_id]["inputs"][mapping["input"]] = structural_guide_reference(art)


def build_guide_conditioned_workflow(
    template: WorkflowTemplate,
    spec: Any,
    artifacts: Tuple[SpatialGuideArtifact, ...],
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a workflow referencing guide artifacts (additive over build_workflow)."""
    aug = augment_template_with_guide_inputs(template)
    wf = build_workflow(aug, spec, seed=seed, refs=(), masks=())
    attach_guides(wf, aug, artifacts)
    return wf


# --------------------------------------------------------------------------- #
# Canonical structural-guide derivation (provider-neutral)
# --------------------------------------------------------------------------- #
# The boundary below turns a resolved GenerationSpec into a SpatialGuideRequest,
# then merges the deterministic SpatialGuideArtifact outputs with the request's
# semantics into StructuralGuideBinding objects consumed by comfyui_adapter's
# canonical attach_structural_guides boundary. The geometry is a deterministic
# LAYOUT CONVENTION (normalized rects/ellipses), NOT canon geometry; canon only
# supplies the semantic facts (subject identity, effect presence, object
# attachment, environment). No private Studio Bible paths are carried.

# Attachment anchor token contract (single owner: the anchor resolution below).
#   - unspecified ("") -> hand_grip default (established contract)
#   - "belt" | "strap" | "harness" -> hip anchor geometry
#   - "hand_grip" | "sheathed" | "mount" -> hand_grip geometry (explicit; these
#     are generation_spec-declared valid values; spatial_guide has no distinct
#     geometry for them, so they map to the established hand_grip default)
#   - any other explicit value is genuinely unrecognized and FAILS CLOSED.
_ATTACHMENT_HIP_TOKENS = ("belt", "strap", "harness")
_ATTACHMENT_HAND_GRIP_TOKENS = ("hand_grip", "sheathed", "mount")
_ATTACHMENT_SUPPORTED_TOKENS = frozenset(
    ("",) + _ATTACHMENT_HIP_TOKENS + _ATTACHMENT_HAND_GRIP_TOKENS
)


# (effect_substring, ((region_label, shape, x, y, w, h, body_zone), ...))
# Each token may expand to MULTIPLE deterministic regions so a supernatural
# effect can be encoded as a set of narrow, localized sub-regions rather than one
# broad body-sized ellipse. Geometry is a LAYOUT CONVENTION, not canon geometry.
_EFFECT_REGION_RULES = (
    # Golden ember: a SMALL, tightly chest-centered core. Materially smaller than
    # the torso; entirely inside the subject silhouette; never head/legs/most torso.
    ("golden ember", (
        ("golden_ember_core", "ellipse", 0.44, 0.36, 0.12, 0.14, "chest"),
    )),
    # Amber qi: a narrow central torso band PLUS separate left/right arm bands.
    # Keeps the canonical `amber_qi` torso_and_arms region (for existing bindings)
    # while adding distinct, narrow arm sub-regions that extend outward enough to
    # be distinguishable from the subject mask without becoming a full-body glow.
    ("amber qi", (
        ("amber_qi", "rect", 0.43, 0.34, 0.14, 0.22, "torso_and_arms"),
        ("amber_qi_left_arm", "rect", 0.30, 0.34, 0.08, 0.24, "left_arm"),
        ("amber_qi_right_arm", "rect", 0.62, 0.34, 0.08, 0.24, "right_arm"),
    )),
)


@dataclass(frozen=True)
class StructuralGuideBundle:
    """Carries one resolved scene's guide request + produced artifacts.

    Provider-neutral: the artifacts may come from LocalCpuReferenceProvider OR
    any test/alternate provider that satisfies the SpatialGuideArtifact contract.
    """

    request: SpatialGuideRequest
    artifacts: Tuple[SpatialGuideArtifact, ...]


def build_spatial_guide_request_from_spec(
    spec: Any,
    *,
    novel: str = "",
    request_id: str = "",
    seed: int = 1_000_003,
    hand_hilt_isolation: bool = False,
) -> Optional[SpatialGuideRequest]:
    """Deterministically derive a SpatialGuideRequest from a GenerationSpec.

    Returns None when no scene-resolved subject is present (e.g. Studio Bible
    enrichment OFF), so the OFF path produces NO structural guide and the
    workflow stays byte-identical to the pre-guide contract.

    CANON FACTS are read from the spec's structured fields:
      - subject identity (content.subjects / identity.character_id)
      - physical object identity + attachment (conditioning.object_identity)
      - effect presence (content.props tokens: golden ember / amber qi)
      - environment (content.environment)
    LAYOUT CONVENTION: normalized rect/ellipse placement is plumbing only.
    """
    subjects = tuple(s for s in (spec.content.subjects or ()) if s)
    if not subjects and spec.identity.character_id:
        subjects = (spec.identity.character_id,)
    if not subjects:
        return None
    subject_label = str(subjects[0])
    subject_key = subject_label.lower().replace(" ", "_")

    subject_regions = (Region(subject_key, "rect", 0.28, 0.18, 0.44, 0.70, zone="subject"),)

    object_regions: Tuple[Region, ...] = ()
    object_attachments: Tuple[Tuple[str, str], ...] = ()
    contact_regions: Tuple[Region, ...] = ()
    obj_id = spec.conditioning.object_identity or ""
    if obj_id:
        obj_key = obj_id.lower().replace(" ", "_")
        # Attachment anchor reuses the typed attachment contract when present
        # (hand_grip -> hand; belt/strap/harness -> hip; mount -> mount). The
        # contact/hilt sub-region is placed at the chosen subject-relative anchor
        # and the blade region is positioned so it INTERSECTS that contact zone,
        # making the wielding/grip relationship structurally explicit rather than
        # merely proximity-based.
        anchor = (spec.attachment.attachment_type or "").lower()
        if anchor in ("belt", "strap", "harness"):
            contact = Region("soulblade_contact", "rect", 0.50, 0.62, 0.12, 0.10, zone="hip")
            blade = Region(obj_key, "rect", 0.52, 0.30, 0.09, 0.36, zone="attached")
        elif anchor == "" or anchor in ("hand_grip", "sheathed", "mount"):
            # Unspecified default OR explicitly supported hand-grip aliases.
            contact = Region("soulblade_contact", "rect", 0.50, 0.56, 0.12, 0.12, zone="hand_grip")
            blade = Region(obj_key, "rect", 0.52, 0.30, 0.10, 0.30, zone="attached")
        else:
            # Genuinely unrecognized explicit token: fail closed (deterministic
            # error) instead of silently producing a plausible-but-wrong hand_grip
            # guide.
            raise ValueError(
                f"Unsupported attachment_type {spec.attachment.attachment_type!r}: "
                f"supported values are hand_grip, sheathed, mount (hand-grip anchor) "
                f"and belt, strap, harness (hip anchor); an empty value resolves to "
                f"the hand_grip default"
            )
        object_regions = (blade,)
        contact_regions = (contact,)
        object_attachments = ((obj_key, subject_key),)

    effect_regions: Tuple[Region, ...] = ()
    for token, regions in _EFFECT_REGION_RULES:
        if any(token in (p or "").lower() for p in (spec.content.props or ())):
            for label, shape, x, y, w, h, zone in regions:
                effect_regions = effect_regions + (Region(label, shape, x, y, w, h, zone=zone),)

    environment_regions: Tuple[Region, ...] = ()
    if spec.content.environment:
        environment_regions = (Region("environment", "rect", 0.0, 0.0, 1.0, 1.0, zone="background"),)

    depth_layers = [(subject_key, 0.0)]
    for o in object_regions:
        depth_layers.append((o.label, 0.1))
    for e in effect_regions:
        depth_layers.append((e.label, 0.2))
    if environment_regions:
        depth_layers.append(("environment", 1.0))

    # No physical object => the scene must not contain a weapon region.
    forbidden = ("weapon",) if not obj_id else ()

    binding = spec.identity.studio_bible_binding
    request = SpatialGuideRequest(
        request_id=request_id or f"sg_{subject_key}",
        novel=novel or (binding.snapshot_ref or ""),
        character_id=subject_key,
        scene_id="",
        chapter="",
        width=int(spec.model_execution.resolution[0]),
        height=int(spec.model_execution.resolution[1]),
        camera_framing="medium_shot",
        subject_regions=subject_regions,
        object_regions=object_regions,
        object_attachments=object_attachments,
        contact_regions=contact_regions,
        effect_regions=effect_regions,
        depth_layers=tuple(depth_layers),
        pose="stable" if subjects else "",
        environment_regions=environment_regions,
        forbidden_regions=forbidden,
        seed=seed,
        canon_snapshot_hash=binding.snapshot_sha256 or "",
    )
    if hand_hilt_isolation:
        request = add_hand_hilt_isolation_to_request(request)
    return request


def _region_semantics(request: SpatialGuideRequest) -> Tuple[Dict[str, Any], ...]:
    """Inspectable per-region semantics (canon fact, not geometry bytes)."""
    out: List[Dict[str, Any]] = []
    subject_key = request.character_id
    for r in request.subject_regions:
        out.append({"label": r.label, "role": "subject", "zone": r.zone,
                    "shape": r.shape, "target": subject_key})
    for r in request.object_regions:
        out.append({"label": r.label, "role": "object", "zone": r.zone,
                    "shape": r.shape, "target_object": r.label,
                    "attachment_target": subject_key})
    for r in request.contact_regions:
        out.append({"label": r.label, "role": "contact", "zone": r.zone,
                    "shape": r.shape, "attachment_target": subject_key})
    for r in request.effect_regions:
        out.append({"label": r.label, "role": "effect", "zone": r.zone,
                    "shape": r.shape, "target": subject_key})
    for r in request.environment_regions:
        out.append({"label": r.label, "role": "environment", "zone": r.zone,
                    "shape": r.shape})
    return tuple(out)


def build_structural_bindings(
    artifacts: Tuple[SpatialGuideArtifact, ...],
    request: SpatialGuideRequest,
) -> Tuple[StructuralGuideBinding, ...]:
    """Merge deterministic artifacts with request semantics into bindings.

    The artifact's on-disk path is intentionally NOT embedded; only a
    deterministic content-addressed reference (spatial_guide://<type>/<sha>.png)
    is used so the workflow hash is stable across hosts/output dirs.
    """
    subject_key = request.character_id
    obj_attach = dict(request.object_attachments)

    def role_for(guide_type: str) -> Dict[str, str]:
        # All guide types encode the same request; semantics are carried at the
        # region level. Per-guide role is coarse (the guide KIND), while the
        # spatial semantics live in _region_semantics / the metadata regions.
        return {"semantic_role": guide_type}

    bindings = []
    for art in artifacts:
        ref = structural_guide_reference(art)
        role_meta = role_for(art.guide_type)
        attachment_target = ""
        target_object = ""
        if art.guide_type == "layout":
            if request.object_attachments:
                attachment_target = obj_attach.get(request.object_regions[0].label, "")
                target_object = request.object_regions[0].label if request.object_regions else ""
        bindings.append(StructuralGuideBinding(
            guide_type=art.guide_type,
            artifact_path=ref,
            sha256=art.sha256,
            width=art.width,
            height=art.height,
            coordinate_space=COORDINATE_SPACE_NORMALIZED,
            source_provider=art.provider,
            source_request_hash=art.source_request_sha256,
            semantic_role=role_meta["semantic_role"],
            target_subject=subject_key,
            target_object=target_object,
            body_region="",
            depth_role="near" if art.guide_type == "depth" else "",
            attachment_target=attachment_target,
        ))
    return tuple(bindings)


def bind_structural_guides_to_workflow(
    workflow: Dict[str, Any],
    bundle: StructuralGuideBundle,
) -> Dict[str, Any]:
    """Canonical pipeline wiring: attach a scene's guide bundle to a workflow.

    Delegates to comfyui_adapter.attach_structural_guides (the single canonical
    structural-control boundary). Provider-neutral: only the artifact contract
    and request semantics are consumed.
    """
    bindings = build_structural_bindings(bundle.artifacts, bundle.request)
    regions = _region_semantics(bundle.request)
    return attach_structural_guides(
        workflow, bindings, regions=regions, novel=bundle.request.novel
    )


# --------------------------------------------------------------------------- #
# Real mask / regional control adapter support (provider-neutral)
# --------------------------------------------------------------------------- #
# The first runtime structural-control family chosen for this stage is
# A = MASK / REGIONAL CONTROL. ComfyUI 0.33.2 ships the required nodes
# (ConditioningSetMask, ConditioningSetArea, LoadImageMask, ImageToMask,
# SolidMask, MaskComposite, ...) in CORE, so NO custom-node package and NO
# external SDXL ControlNet model download is required. The single minimal
# structural factor is region-masked conditioning: each subject / effect /
# object region gets a deterministic binary mask + a re-emphasis prompt, wired
# through ComfyUI's built-in ConditioningSetMask node chain.
#
# The artifact's on-disk path is intentionally NOT embedded in the workflow;
# only a deterministic content-addressed basename (derived from the region
# mask sha256) is referenced, so the workflow hash stays host-independent.

_REGION_PROMPT_BY_EFFECT = {
    "golden_ember_core": (
        "golden ember core glowing warmly at the chest, radiant amber-gold light source"
    ),
    "amber_qi": (
        "amber qi energy visibly swirling and wrapping around the torso and arms"
    ),
    "amber_qi_left_arm": (
        "amber qi thread visibly wrapping and trailing along Kai's left arm"
    ),
    "amber_qi_right_arm": (
        "amber qi thread visibly wrapping and trailing along Kai's right arm"
    ),
}


# --------------------------------------------------------------------------- #
# HAND_HILT_ISOLATION regional factor (canonical owner: this module + comfyui_adapter)
# --------------------------------------------------------------------------- #
# A single narrow regional factor that isolates the gripping-hand / Soulblade
# hilt junction. It is expressed ONLY through the existing regional
# (ConditioningSetMask) conditioning owner; it does NOT create a parallel
# regional system, does NOT alter the global prompt, and does NOT alter the
# OpenPose hand guide / ControlNet parameters.
#
# The factor is added only to the TREATMENT arm of the bounded GPU causal
# experiment; the CONTROL arm is the existing qualified-EN-grip configuration.
HAND_HILT_ISOLATION_REGION_LABEL = "hand_hilt_isolation"

HAND_HILT_ISOLATION_POSITIVE = (
    "five distinct fingers wrapped around the Soulblade hilt, "
    "anatomically coherent gripping hand, visible separation between digits, "
    "thumb opposing the fingers, intact palm, clear physical hand-to-hilt "
    "contact, Soulblade hilt structurally distinct from skin"
)

HAND_HILT_ISOLATION_NEGATIVE = (
    "fused fingers, merged digits, extra fingers, missing fingers, "
    "hand-object fusion, blade passing through palm, glowing material "
    "replacing fingers, glowing material merging with skin, melted hand, "
    "duplicated hand, malformed wrist"
)

# Per-region negative re-emphasis prompts (opt-in by label; all existing regions
# stay positive-only so the prior behaviour is byte-for-byte unchanged).
_REGION_NEGATIVE_BY_LABEL: Dict[str, str] = {
    HAND_HILT_ISOLATION_REGION_LABEL: HAND_HILT_ISOLATION_NEGATIVE,
}


def compute_hand_hilt_isolation_region(contact: Region) -> Region:
    """Deterministic narrow mask enclosing the gripping hand + hilt junction.

    Derived from the existing ``soulblade_contact`` geometry (authority), grown
    just enough to enclose the wrapped fingers (above) and wrist transition
    (below) but clamped so it never reaches the torso edges, face, full blade,
    full arm, or unrelated glow effects.
    """
    cx = contact.x + contact.w / 2.0
    cy = contact.y + contact.h / 2.0
    iw = min(0.16, float(contact.w) * 1.4)
    ih = min(0.24, float(contact.h) * 2.2)
    ix = _clamp01(cx - iw / 2.0)
    iy = _clamp01(cy - ih / 2.0 + 0.01)
    iw = min(iw, 1.0 - ix)
    ih = min(ih, 1.0 - iy)
    return Region(
        HAND_HILT_ISOLATION_REGION_LABEL, "rect", ix, iy, iw, ih,
        zone="hand_hilt_isolation",
    )


def add_hand_hilt_isolation_to_request(
    request: SpatialGuideRequest,
) -> SpatialGuideRequest:
    """Return a NEW request with the hand-hilt isolation region appended.

    Idempotent: a request that already carries the isolation region is returned
    unchanged. The isolation region is appended to ``contact_regions`` so it is
    discovered by ``render_region_masks``; its specialised prompt/negative are
    resolved by label in ``_region_prompt`` / ``render_region_masks``.
    """
    if any(r.label == HAND_HILT_ISOLATION_REGION_LABEL for r in request.contact_regions):
        return request
    if not request.contact_regions:
        return request
    iso = compute_hand_hilt_isolation_region(request.contact_regions[0])
    return replace(
        request, contact_regions=request.contact_regions + (iso,)
    )


def _region_prompt(region: Region, request: SpatialGuideRequest) -> str:
    """Deterministic region re-emphasis prompt (no private data, no novel leak)."""
    if region.label == HAND_HILT_ISOLATION_REGION_LABEL:
        return HAND_HILT_ISOLATION_POSITIVE
    role = ""
    if region in request.subject_regions:
        role = "subject"
    elif region in request.object_regions:
        role = "object"
    elif region in request.contact_regions:
        role = "contact"
    elif region in request.effect_regions:
        role = "effect"
    label_human = region.label.replace("_", " ")

    if role == "subject":
        return f"{request.character_id.replace('_', ' ')}, the centered main subject, clearly distinct"
    if role == "object":
        target = request.character_id.replace("_", " ")
        return (
            f"{label_human}, a glowing energy weapon held in hand, "
            f"attached to and wielded by {target}"
        )
    if role == "contact":
        target = request.character_id.replace("_", " ")
        return (
            f"{label_human}, the blade hilt firmly grasped and anchored to {target}, "
            f"a deliberate grip and carry relationship"
        )
    if role == "effect":
        return _REGION_PROMPT_BY_EFFECT.get(
            region.label, f"{label_human} effect localized to its region"
        )
    return label_human


def render_region_masks(
    request: SpatialGuideRequest, output_dir: Any
) -> Dict[str, Dict[str, Any]]:
    """Materialize one deterministic binary mask PNG per structural region.

    Returns a dict keyed by region label with deterministic metadata
    (basename, sha256, role, prompt, target). Host paths are kept OUT of the
    returned mapping's semantic identity; only the content-addressed basename
    is safe to embed in a workflow.

    Iterates subject + object + contact (hilt/anchor) + effect regions. The
    explicit environment/background region is intentionally NOT produced here
    (it would become an unwanted background-emphasis conditioning node); use
    ``render_environment_mask`` for the protected-background artifact.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    req_hash = request.sha256()[:12]
    w, h = request.width, request.height

    regions: List[Region] = []
    for r in list(request.subject_regions) + list(request.object_regions) \
            + list(request.contact_regions) + list(request.effect_regions):
        regions.append(r)

    result: Dict[str, Dict[str, Any]] = {}
    for r in regions:
        img = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(img)
        box = _region_px(r, w, h)
        if r.shape == "ellipse":
            d.ellipse(box, fill=255)
        else:
            d.rectangle(box, fill=255)
        # Content-addressed basename: derived from THIS mask's sha256, not the
        # request hash, so adding/removing one region changes only that region's
        # identity and leaves every other region's mask basename stable
        # (single-factor isolation across arms). The PNG is rendered into the
        # basename-derived path so the on-disk file matches the node reference.
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        sha = hashlib.sha256(data).hexdigest()
        basename = f"sgmask_{r.label}_{sha[:12]}.png"
        path = out / basename
        path.write_bytes(data)
        role = (
            "subject" if r in request.subject_regions
            else "object" if r in request.object_regions
            else "contact" if r in request.contact_regions
            else "effect"
        )
        if r.label == HAND_HILT_ISOLATION_REGION_LABEL:
            role = "isolation"
        target = request.character_id
        if role == "object":
            target = request.object_attachments[0][1] if request.object_attachments else request.character_id
        elif role in ("contact", "isolation"):
            target = request.character_id
        result[r.label] = {
            "basename": basename,
            "sha256": sha,
            "role": role,
            "target": target,
            "zone": r.zone,
            "prompt": _region_prompt(r, request),
            "negative_prompt": _REGION_NEGATIVE_BY_LABEL.get(r.label, ""),
            "region_label": r.label,
        }
    return result


def render_environment_mask(
    request: SpatialGuideRequest, output_dir: Any
) -> Dict[str, Dict[str, Any]]:
    """Materialize the EXPLICIT protected-background (environment) mask.

    The background region is the complement of the union of all foreground
    structural regions (subject + object + contact + effect). This deterministically
    encodes that the rainy back-alley environment remains visually dominant outside
    the localized subject/effect area, so supernatural effect masks cannot overwrite
    most of the frame. Content-addressed and deterministic.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    req_hash = request.sha256()[:12]
    w, h = request.width, request.height

    fg = (
        list(request.subject_regions)
        + list(request.object_regions)
        + list(request.contact_regions)
        + list(request.effect_regions)
    )
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    for r in fg:
        box = _region_px(r, w, h)
        if r.shape == "ellipse":
            d.ellipse(box, fill=0)
        else:
            d.rectangle(box, fill=0)
    basename = f"sgmask_environment_{req_hash}.png"
    path = out / basename
    img.save(path, format="PNG")
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    return {
        "environment": {
            "basename": basename,
            "sha256": sha,
            "role": "environment",
            "target": "",
            "zone": "background",
            "prompt": "rainy back-alley environment preserved outside the localized subject and effect regions",
            "region_label": "environment",
        }
    }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj
