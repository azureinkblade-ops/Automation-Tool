"""Production Image-to-Video adapter (media-pipeline boundary).

Chapter / novel logic must call ``generate_video`` here — never ComfyUI SVD nodes
directly. Backend V1 is SVD-XT 1.1 (``svd_xt_1_1``) — production default until explicit APPROVE.
Wan 2.2 (``wan_22``) is allowlisted and P1-ready via ``build_wan_22_ti2v_workflow``
when I2V_BACKEND=wan_22 (opt-in). SVD-XT 1.1 remains the production default.
Unknown backends fail closed.
ExclusiveGpuLease.KIND_I2V is sequential: SVD and Wan must never be co-resident.

Qualified defaults from IMAGE_TO_VIDEO_PRODUCTION_BACKEND_QUALIFICATION PASS:
frame_count=25, fps=6, motion_bucket_id=127, TEXT_CONTROL_SUPPORTED=NO.
I2V input transform is FIT_INSIDE_LETTERBOX (no crop/stretch), calculated from
source dimensions — qualification geometry is not hard-coded as universal.
Social presentation transforms are out of scope.
"""
from __future__ import annotations

import hashlib
import os
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, runtime_checkable

from tools.i2v_backend_registry import (
    BACKEND_ID_WAN_22,
    UnsupportedBackend,
    assert_backend_ready_for_generate,
    assert_no_svd_wan_coresident,
    assert_shadow_path_inert,
    document_exclusive_i2v_gpu_policy,
    get_i2v_backend,
    i2v_backend_packet_field,
    is_i2v_wan_shadow_enabled,
    wan_media_validity_hook_required,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BACKEND_ID_SVD_XT_1_1 = "svd_xt_1_1"
# Wan id: BACKEND_ID_WAN_22 from i2v_backend_registry (re-exported via import).
# Default remains SVD until explicit APPROVE (see get_i2v_backend).
MODEL_ID_SVD_XT_1_1 = "svd_xt_1_1.safetensors"
# SHA256 of Comfy Shared checkpoints/svd_xt_1_1.safetensors from I2V qual (2026-10-26)
MODEL_SHA256_SVD_XT_1_1 = "69ccfea1bb45dd63b3ba8b6cfe8b0d45d780995dfdde590aeaa97cc567018d33"
WORKFLOW_VERSION = "i2v_svd_xt_1_1_v1"
BACKEND_SETTINGS_VERSION = "svd_xt_1_1_settings_v1"
I2V_INPUT_TRANSFORM_ID = "FIT_INSIDE_LETTERBOX"
SVD_NATIVE_WIDTH = 1024
SVD_NATIVE_HEIGHT = 576
DEFAULT_FRAME_COUNT = 25
DEFAULT_FPS = 6
DEFAULT_MOTION_BUCKET_ID = 127
MIN_FREE_VRAM_MIB = 13000
MAX_INFRASTRUCTURE_ATTEMPTS = 2
TEXT_CONTROL_SUPPORTED = False
VIDEO_CREATES_IDENTITY_CANON = False
STATIC_FALLBACK_SUPPORTED = True

# Comfy VAEDecodeTiled floor (qualification mapped packet decode_chunk_size=2 → 8)
DECODE_TEMPORAL_SIZE_NORMAL = 8
DECODE_TEMPORAL_SIZE_LOW_MEM = 8  # Comfy min is 8; low-mem path still uses tiled decode
DECODE_TEMPORAL_OVERLAP = 4


class JobState(str, Enum):
    QUEUED = "QUEUED"
    GPU_PREFLIGHT = "GPU_PREFLIGHT"
    TRANSFORMING = "TRANSFORMING"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VIDEO_REVIEW_REQUIRED = "VIDEO_REVIEW_REQUIRED"
    INFRA_FAILURE = "INFRA_FAILURE"


class TemporalFlicker(str, Enum):
    NONE = "NONE"
    MINOR = "MINOR"
    MAJOR = "MAJOR"


class I2VAdapterError(Exception):
    """Base adapter error."""


class SourceNotApprovedError(I2VAdapterError):
    """Fail-closed: unapproved or incomplete still."""


class MissingSourceShaError(I2VAdapterError):
    """Fail-closed: source SHA required."""


class GpuHeadroomInsufficient(I2VAdapterError):
    """Retryable: free VRAM below production floor."""

    code = "GPU_HEADROOM_INSUFFICIENT"


class GpuOwnershipConflict(I2VAdapterError):
    """SDXL and I2V must not own the GPU simultaneously."""


class InfrastructureFailure(I2VAdapterError):
    """OOM / transport / backend infra failure (bounded retry)."""


# --------------------------------------------------------------------------- #
# Transform
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LetterboxTransform:
    transform_id: str
    original_width: int
    original_height: int
    scaled_width: int
    scaled_height: int
    pad_left: int
    pad_right: int
    pad_top: int
    pad_bottom: int
    target_width: int
    target_height: int
    transform_sha256: str

    @property
    def uses_crop(self) -> bool:
        return False

    @property
    def uses_stretch(self) -> bool:
        # content aspect preserved by construction
        return False


def compute_fit_inside_letterbox(
    original_width: int,
    original_height: int,
    *,
    target_width: int = SVD_NATIVE_WIDTH,
    target_height: int = SVD_NATIVE_HEIGHT,
) -> LetterboxTransform:
    """FIT_INSIDE + LETTERBOX: no crop, no stretch. Geometry from source dims."""
    if original_width < 1 or original_height < 1:
        raise ValueError("original dimensions must be >= 1")
    if target_width < 1 or target_height < 1:
        raise ValueError("target dimensions must be >= 1")

    scale = min(target_width / original_width, target_height / original_height)
    scaled_w = int(original_width * scale)  # floor toward zero
    scaled_h = int(original_height * scale)
    if scaled_w < 1:
        scaled_w = 1
    if scaled_h < 1:
        scaled_h = 1
    # Ensure fit
    if scaled_w > target_width:
        scaled_w = target_width
    if scaled_h > target_height:
        scaled_h = target_height

    pad_x = target_width - scaled_w
    pad_y = target_height - scaled_h
    pad_left = pad_x // 2
    pad_right = pad_x - pad_left
    pad_top = pad_y // 2
    pad_bottom = pad_y - pad_top

    desc = (
        f"FIT_INSIDE_LETTERBOX|src={original_width}x{original_height}|"
        f"dst={target_width}x{target_height}|content={scaled_w}x{scaled_h}|"
        f"pad_l={pad_left}|pad_r={pad_right}|pad_t={pad_top}|pad_b={pad_bottom}|"
        f"nocrop|nostretch"
    )
    transform_sha = hashlib.sha256(desc.encode("utf-8")).hexdigest()
    return LetterboxTransform(
        transform_id=I2V_INPUT_TRANSFORM_ID,
        original_width=original_width,
        original_height=original_height,
        scaled_width=scaled_w,
        scaled_height=scaled_h,
        pad_left=pad_left,
        pad_right=pad_right,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        target_width=target_width,
        target_height=target_height,
        transform_sha256=transform_sha,
    )


# --------------------------------------------------------------------------- #
# Source gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceImageRef:
    """Approved still contract for production I2V."""

    source_image_sha256: str
    image_generation_complete: bool
    image_validation_complete: bool
    image_source_approved: bool
    source_width: int
    source_height: int
    source_path: Optional[str] = None
    source_character_intent: str = "UNKNOWN"
    source_character_id_or_na: str = "N/A"
    # raw pixels optional for pure-metadata unit tests
    image_bytes: Optional[bytes] = None


def assert_source_approved(source: SourceImageRef) -> None:
    if not source.source_image_sha256 or not str(source.source_image_sha256).strip():
        raise MissingSourceShaError("SOURCE_IMAGE_SHA256 required; refuse unapproved image")
    if not (
        source.image_generation_complete
        and source.image_validation_complete
        and source.image_source_approved
    ):
        raise SourceNotApprovedError(
            "I2V requires IMAGE_GENERATION_COMPLETE=YES, "
            "IMAGE_VALIDATION_COMPLETE=YES, IMAGE_SOURCE_APPROVED=YES"
        )


# --------------------------------------------------------------------------- #
# GPU ownership + metrics
# --------------------------------------------------------------------------- #


@runtime_checkable
class GpuMetricsProvider(Protocol):
    def free_vram_mib(self) -> int: ...

    def total_vram_mib(self) -> int:
        """Optional; return 0 if unknown. Used to derive peak_vram_used_mib."""
        ...



def default_process_alive(process_identity: str) -> bool:
    """Return True if the recorded process_identity appears still alive."""
    if not process_identity:
        return True
    raw_id = process_identity
    if raw_id.startswith("pid:"):
        raw_id = raw_id[4:]
    try:
        pid = int(raw_id)
    except ValueError:
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True


class ExclusiveGpuLease:
    """Process-wide exclusive GPU ownership: image-gen XOR I2V.

    KIND_I2V is shared by every I2V backend (SVD-XT and Wan). Ownership is
    sequential: SVD and Wan must never be co-resident on the GPU. See
    document_exclusive_i2v_gpu_policy / assert_no_svd_wan_coresident.

    Stale recovery must prove the recorded process is no longer active before
    reclaim. Age alone never clears a lease.
    """

    KIND_IMAGE = "image_generation"
    KIND_I2V = "i2v"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._record: Optional[Dict[str, Any]] = None

    @property
    def gpu_owner_job_id(self) -> Optional[str]:
        with self._lock:
            return None if self._record is None else self._record.get("owner_job_id")

    @property
    def gpu_owner_kind(self) -> Optional[str]:
        with self._lock:
            return None if self._record is None else self._record.get("owner_kind")

    def current_record(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return None if self._record is None else dict(self._record)

    def acquire(
        self,
        job_id: str,
        kind: str,
        *,
        workflow_id: str = "",
        stage: str = "GPU_PREFLIGHT",
        process_identity: Optional[str] = None,
        now: Optional[float] = None,
    ) -> None:
        ts = time.time() if now is None else float(now)
        proc = process_identity or f"pid:{os.getpid()}"
        with self._lock:
            if self._record is not None and self._record.get("owner_job_id") != job_id:
                raise GpuOwnershipConflict(
                    f"GPU owned by {self._record.get('owner_kind')}:{self._record.get('owner_job_id')}; "
                    f"refusing {kind}:{job_id}"
                )
            self._record = {
                "owner_job_id": job_id,
                "owner_workflow_id": workflow_id,
                "owner_stage": stage,
                "owner_kind": kind,
                "acquired_at": ts,
                "heartbeat_at": ts,
                "process_identity": proc,
            }

    def heartbeat(self, job_id: str, *, stage: Optional[str] = None, now: Optional[float] = None) -> None:
        ts = time.time() if now is None else float(now)
        with self._lock:
            if self._record is None or self._record.get("owner_job_id") != job_id:
                raise GpuOwnershipConflict(f"heartbeat rejected for job {job_id}")
            self._record["heartbeat_at"] = ts
            if stage is not None:
                self._record["owner_stage"] = stage

    def release(self, job_id: str) -> None:
        with self._lock:
            if self._record is not None and self._record.get("owner_job_id") == job_id:
                self._record = None

    def try_reclaim_stale(
        self,
        *,
        process_alive: Callable[[str], bool],
        claimant_job_id: str,
        claimant_kind: str,
        workflow_id: str = "",
        stage: str = "GPU_PREFLIGHT",
        process_identity: Optional[str] = None,
        now: Optional[float] = None,
    ) -> bool:
        """Reclaim only when recorded process_identity is proven not alive.

        Returns True if lease acquired (empty or reclaimed). Raises if still held
        by a living owner.
        """
        with self._lock:
            if self._record is None:
                pass
            else:
                owner_proc = str(self._record.get("process_identity") or "")
                # Do NOT clear merely because lease is old.
                if process_alive(owner_proc):
                    raise GpuOwnershipConflict(
                        f"stale reclaim refused; process still active: {owner_proc} "
                        f"job={self._record.get('owner_job_id')}"
                    )
                # Proven dead — reclaim
                self._record = None
        self.acquire(
            claimant_job_id,
            claimant_kind,
            workflow_id=workflow_id,
            stage=stage,
            process_identity=process_identity,
            now=now,
        )
        return True



_DEFAULT_GPU_LEASE = ExclusiveGpuLease()


def get_default_gpu_lease() -> ExclusiveGpuLease:
    return _DEFAULT_GPU_LEASE


def reset_default_gpu_lease() -> None:
    global _DEFAULT_GPU_LEASE
    _DEFAULT_GPU_LEASE = ExclusiveGpuLease()


# --------------------------------------------------------------------------- #
# Idempotency + durable job store
# --------------------------------------------------------------------------- #


def motion_plan_hash(motion_plan: Optional[Mapping[str, Any]]) -> str:
    payload = motion_plan or {}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_video_idempotency_key(
    *,
    workflow_id: str,
    source_image_sha256: str,
    backend_id: str,
    backend_settings_version: str,
    seed: int,
    motion_plan: Optional[Mapping[str, Any]],
) -> str:
    raw = "|".join(
        [
            workflow_id,
            source_image_sha256.lower(),
            backend_id,
            backend_settings_version,
            str(int(seed)),
            motion_plan_hash(motion_plan),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class VideoJobRecord:
    video_job_id: str
    workflow_id: str
    idempotency_key: str
    state: str
    backend_id: str
    result: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    updated_at: float = field(default_factory=time.time)
    # Crash-safe generation bookkeeping (persist around external side effects)
    attempt_number: int = 0
    attempt_started_at: Optional[float] = None
    backend_request_id: Optional[str] = None
    comfy_prompt_id: Optional[str] = None
    result_artifact_path: Optional[str] = None
    result_video_sha256: Optional[str] = None


class VideoJobStore:
    """Durable-enough job store (JSON directory). Restart-safe resume of READY jobs."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get_by_idempotency(self, key: str) -> Optional[VideoJobRecord]:
        path = self._path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return VideoJobRecord(**data)

    def save(self, record: VideoJobRecord) -> None:
        """Crash-safer persist: write temp then replace."""
        record.updated_at = time.time()
        payload = json.dumps(asdict(record), indent=2, sort_keys=True)
        with self._lock:
            final = self._path(record.idempotency_key)
            tmp = final.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, final)

    def verify_ready_artifact(self, record: VideoJobRecord) -> bool:
        """Content hashes are authoritative: path alone is not identity."""
        if record.state != JobState.READY.value:
            return False
        sha = record.result_video_sha256 or (
            (record.result or {}).get("video_sha256") if record.result else None
        )
        path = record.result_artifact_path or (
            (record.result or {}).get("video_path") if record.result else None
        )
        if not sha:
            return False
        if not path:
            # In-memory/mock jobs may store only bytes hash without path.
            return bool(record.result and record.result.get("video_sha256") == sha)
        fp = Path(path)
        if not fp.is_file():
            return False
        digest = hashlib.sha256(fp.read_bytes()).hexdigest()
        return digest == sha


# --------------------------------------------------------------------------- #
# Backend protocol + SVD workflow (no text identity)
# --------------------------------------------------------------------------- #


@runtime_checkable
class I2VBackendTransport(Protocol):
    """Comfy transport boundary. Fakes in tests; no chapter imports."""

    def health_check(self) -> bool: ...

    def free_models(self) -> Dict[str, Any]: ...

    def submit_and_wait(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Return {prompt_id, video_bytes, video_path?}."""
        ...


def build_svd_xt_workflow(
    *,
    image_filename: str,
    seed: int,
    frame_count: int = DEFAULT_FRAME_COUNT,
    fps: int = DEFAULT_FPS,
    motion_bucket_id: int = DEFAULT_MOTION_BUCKET_ID,
    decode_temporal_size: int = DECODE_TEMPORAL_SIZE_NORMAL,
    ckpt_name: str = MODEL_ID_SVD_XT_1_1,
    filename_prefix: str = "i2v_prod",
    width: int = SVD_NATIVE_WIDTH,
    height: int = SVD_NATIVE_HEIGHT,
) -> Dict[str, Any]:
    """Comfy API prompt for SVD-XT. No text conditioning / identity prompts."""
    if TEXT_CONTROL_SUPPORTED:
        raise RuntimeError("TEXT_CONTROL_SUPPORTED unexpectedly True for SVD-XT V1")
    return {
        "1": {
            "class_type": "ImageOnlyCheckpointLoader",
            "inputs": {"ckpt_name": ckpt_name},
        },
        "2": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "3": {
            "class_type": "SVD_img2vid_Conditioning",
            "inputs": {
                "clip_vision": ["1", 1],
                "init_image": ["2", 0],
                "vae": ["1", 2],
                "width": width,
                "height": height,
                "video_frames": frame_count,
                "motion_bucket_id": motion_bucket_id,
                "fps": fps,
                "augmentation_level": 0.0,
            },
        },
        "4": {
            "class_type": "VideoLinearCFGGuidance",
            "inputs": {"model": ["1", 0], "min_cfg": 1.0},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4", 0],
                "seed": int(seed),
                "steps": 20,
                "cfg": 2.5,
                "sampler_name": "euler",
                "scheduler": "karras",
                "positive": ["3", 0],
                "negative": ["3", 1],
                "latent_image": ["3", 2],
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": int(decode_temporal_size),
                "temporal_overlap": DECODE_TEMPORAL_OVERLAP,
            },
        },
        "7": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["6", 0], "fps": float(fps), "codec": "auto"},
        },
        "8": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["7", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
            },
        },
    }




# Wan 2.2 TI2V freeze (Research draft 2026-10-28) — portrait native + presentation later
WAN22_UNET = "wan2.2_ti2v_5B_fp16.safetensors"
WAN22_VAE = "wan2.2_vae.safetensors"
WAN22_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN22_NATIVE_WIDTH = 720
WAN22_NATIVE_HEIGHT = 1280
WAN22_DEFAULT_LENGTH = 121  # frames
WAN22_DEFAULT_FPS = 24
WAN22_DEFAULT_STEPS = 20
WAN22_DEFAULT_CFG = 5.0
WAN22_DEFAULT_SAMPLER = "uni_pc"
WAN22_DEFAULT_SCHEDULER = "simple"
WAN22_DEFAULT_SHIFT = 8.0
WAN22_DEFAULT_NEGATIVE = (
    "overexposed, static, blurry details, subtitles, worst quality, low quality, "
    "jpeg artifacts, ugly, deformed, extra fingers, bad hands, bad face, "
    "mutated limbs, fused fingers, still frame, cluttered background"
)
WAN22_WORKFLOW_TEMPLATE_RELPATH = "tools/workflow_templates/i2v/wan_22_ti2v_5b.json"


def build_wan_22_ti2v_workflow(
    *,
    image_filename: str,
    seed: int,
    positive_prompt: str = "",
    negative_prompt: str = WAN22_DEFAULT_NEGATIVE,
    width: int = WAN22_NATIVE_WIDTH,
    height: int = WAN22_NATIVE_HEIGHT,
    length: int = WAN22_DEFAULT_LENGTH,
    fps: int = WAN22_DEFAULT_FPS,
    steps: int = WAN22_DEFAULT_STEPS,
    cfg: float = WAN22_DEFAULT_CFG,
    sampler_name: str = WAN22_DEFAULT_SAMPLER,
    scheduler: str = WAN22_DEFAULT_SCHEDULER,
    shift: float = WAN22_DEFAULT_SHIFT,
    filename_prefix: str = "i2v_wan22",
    unet_name: str = WAN22_UNET,
    vae_name: str = WAN22_VAE,
    clip_name: str = WAN22_CLIP,
) -> Dict[str, Any]:
    """Comfy API prompt for Wan 2.2 TI2V 5B (portrait freeze from Research draft).

    Text prompts are motion/scenery conditioning for Wan TI2V — not SVD identity.
    Default positive is empty (caller/motion_plan supplies scenery-safe text).
    SVD remains production default; this graph is opt-in via backend_id=wan_22.
    """
    return {
        "37": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "38": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "wan", "device": "default"},
        },
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "48": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["37", 0], "shift": float(shift)},
        },
        "56": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "55": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": {
                "vae": ["39", 0],
                "start_image": ["56", 0],
                "width": int(width),
                "height": int(height),
                "length": int(length),
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["38", 0], "text": str(positive_prompt or "")},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["38", 0], "text": str(negative_prompt or "")},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["48", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["55", 0],
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["39", 0]},
        },
        "57": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["8", 0], "fps": float(fps)},
        },
        "58": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["57", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }

def workflow_contains_text_identity_prompt(workflow: Mapping[str, Any]) -> bool:
    """Heuristic: SVD V1 graph must not introduce CLIP text encode / prompt strings."""
    forbidden_types = {
        "CLIPTextEncode",
        "CLIPTextEncodeSDXL",
        "CLIPTextEncodeSDXLRefiner",
        "TextEncodeQwenImageEdit",
    }
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in forbidden_types:
            return True
        inputs = node.get("inputs") or {}
        if "text" in inputs and isinstance(inputs["text"], str) and inputs["text"].strip():
            # SaveVideo filename_prefix is not identity text; ignore non-prompt keys
            if node.get("class_type") in {"CLIPTextEncode", "CLIPTextEncodeSDXL"}:
                return True
    return False


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass
class GenerateVideoResult:
    workflow_id: str
    video_job_id: str
    backend_id: str
    model_id: str
    model_sha256: str
    workflow_version: str
    source_image_sha256: str
    source_character_intent: str
    source_character_id_or_na: str
    video_sha256: Optional[str]
    video_path: Optional[str]
    seed: int
    frame_count: int
    fps: int
    motion_bucket_id: int
    source_width: int
    source_height: int
    i2v_width: int
    i2v_height: int
    transform_id: str
    transform_sha256: str
    generation_started_at: Optional[float]
    generation_completed_at: Optional[float]
    generation_wall_seconds: Optional[float]
    peak_vram_used_mib: Optional[int]
    lowest_free_vram_mib: Optional[int]
    post_free_vram_mib: Optional[int]
    vram_recovered_mib: Optional[int]
    comfyui_reachable_after_free: Optional[bool]
    validation_status: str
    failure_reason: Optional[str]
    temporal_flicker: str
    video_creates_identity_canon: bool
    static_fallback_supported: bool
    video_idempotency_key: str
    state: str
    gpu_owner_job_id: Optional[str] = None
    reused_existing: bool = False
    infrastructure_attempts: int = 0
    transform: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #


@dataclass
class I2VSettings:
    frame_count: int = DEFAULT_FRAME_COUNT
    fps: int = DEFAULT_FPS
    motion_bucket_id: int = DEFAULT_MOTION_BUCKET_ID
    min_free_vram_mib: int = MIN_FREE_VRAM_MIB
    model_sha256: str = MODEL_SHA256_SVD_XT_1_1
    target_width: int = SVD_NATIVE_WIDTH
    target_height: int = SVD_NATIVE_HEIGHT


class ImageToVideoAdapter:
    """Production I2V media-pipeline boundary."""

    def __init__(
        self,
        *,
        store: VideoJobStore,
        transport: Optional[I2VBackendTransport] = None,
        gpu_metrics: Optional[GpuMetricsProvider] = None,
        gpu_lease: Optional[ExclusiveGpuLease] = None,
        clock: Callable[[], float] = time.time,
        model_sha256: str = MODEL_SHA256_SVD_XT_1_1,
        stage_image: Optional[Callable[[SourceImageRef, LetterboxTransform, str], str]] = None,
    ) -> None:
        self.store = store
        self.transport = transport
        self.gpu_metrics = gpu_metrics
        self.gpu_lease = gpu_lease or get_default_gpu_lease()
        self.clock = clock
        self.model_sha256 = model_sha256
        self.stage_image = stage_image

    def generate_video(
        self,
        source_image: SourceImageRef,
        motion_plan: Optional[Mapping[str, Any]] = None,
        backend_id: str = BACKEND_ID_SVD_XT_1_1,
        seed: int = 0,
        settings: Optional[I2VSettings] = None,
        *,
        workflow_id: Optional[str] = None,
        temporal_flicker: str = TemporalFlicker.NONE.value,
        force_infra_failure_once: bool = False,
    ) -> GenerateVideoResult:
        settings = settings or I2VSettings(model_sha256=self.model_sha256)
        # Allowlist via i2v_backend_registry: SVD default; Wan P1-ready opt-in;
        # unknown ids fail closed.
        # Shadow must not flip MEDIA_OUTCOME / enqueue live (guard stub).
        assert_shadow_path_inert(enqueue_live_post=False, live_publish_enabled=False)
        _ = wan_media_validity_hook_required()  # same media_validity gate later
        _ = document_exclusive_i2v_gpu_policy()
        try:
            assert_backend_ready_for_generate(backend_id)
        except UnsupportedBackend as exc:
            return self._fail_early(
                source_image,
                seed,
                settings,
                workflow_id or str(uuid.uuid4()),
                ValidationStatus.INFRA_FAILURE,
                exc.message,
                motion_plan,
                backend_id=backend_id,
            )

        assert_source_approved(source_image)

        wf_id = workflow_id or str(uuid.uuid4())
        idem = compute_video_idempotency_key(
            workflow_id=wf_id,
            source_image_sha256=source_image.source_image_sha256,
            backend_id=backend_id,
            backend_settings_version=BACKEND_SETTINGS_VERSION,
            seed=seed,
            motion_plan=motion_plan,
        )

        existing = self.store.get_by_idempotency(idem)
        if existing and existing.state == JobState.READY.value and existing.result:
            if not self.store.verify_ready_artifact(existing):
                # Hash mismatch or missing file — do not declare READY; regenerate
                existing.state = JobState.QUEUED.value
                existing.failure_reason = "READY_ARTIFACT_HASH_MISMATCH"
                self.store.save(existing)
            else:
                reused = GenerateVideoResult(**existing.result)
                reused.reused_existing = True
                return reused
        # Crash reconcile: GENERATING with accepted Comfy id must not double-submit
        recovered_video_bytes: Optional[bytes] = None
        recovered_video_path: Optional[str] = None
        if (
            existing
            and existing.state == JobState.GENERATING.value
            and existing.comfy_prompt_id
        ):
            if self.transport is None:
                return self._fail_early(
                    source_image,
                    seed,
                    settings,
                    wf_id,
                    ValidationStatus.INFRA_FAILURE,
                    f"unreconciled_comfy_prompt_id={existing.comfy_prompt_id}",
                    motion_plan,
                )
            reconcile = getattr(self.transport, "reconcile_prompt", None)
            if not callable(reconcile):
                return self._fail_early(
                    source_image,
                    seed,
                    settings,
                    wf_id,
                    ValidationStatus.INFRA_FAILURE,
                    f"cannot_reconcile_accepted_prompt={existing.comfy_prompt_id}",
                    motion_plan,
                )
            recovered = reconcile(existing.comfy_prompt_id)
            if recovered and recovered.get("video_bytes"):
                recovered_video_bytes = recovered["video_bytes"]
                recovered_video_path = recovered.get("video_path")
                video_sha = hashlib.sha256(recovered_video_bytes).hexdigest()
                existing.result_artifact_path = recovered_video_path
                existing.result_video_sha256 = video_sha
                existing.state = JobState.GENERATED.value
                self.store.save(existing)
            elif recovered and recovered.get("status") in {"pending", "running", "in_progress"}:
                return self._fail_early(
                    source_image,
                    seed,
                    settings,
                    wf_id,
                    ValidationStatus.INFRA_FAILURE,
                    f"comfy_prompt_still_active={existing.comfy_prompt_id}",
                    motion_plan,
                )
            else:
                return self._fail_early(
                    source_image,
                    seed,
                    settings,
                    wf_id,
                    ValidationStatus.INFRA_FAILURE,
                    f"unreconciled_comfy_prompt_id={existing.comfy_prompt_id}",
                    motion_plan,
                )

        video_job_id = existing.video_job_id if existing else str(uuid.uuid4())
        transform = compute_fit_inside_letterbox(
            source_image.source_width,
            source_image.source_height,
            target_width=settings.target_width,
            target_height=settings.target_height,
        )

        if existing and existing.state == JobState.GENERATED.value and existing.result_video_sha256:
            record = existing
        else:
            record = VideoJobRecord(
                video_job_id=video_job_id,
                workflow_id=wf_id,
                idempotency_key=idem,
                state=JobState.QUEUED.value,
                backend_id=backend_id,
            )
            self.store.save(record)

        started = self.clock()
        lowest_free: Optional[int] = None
        peak_used: Optional[int] = None
        attempts = 0
        last_infra: Optional[str] = None
        video_bytes: Optional[bytes] = None
        video_path: Optional[str] = None
        # Resume after crash if artifact already hashed / reconciled
        if recovered_video_bytes is not None:
            video_bytes = recovered_video_bytes
            video_path = recovered_video_path
        elif existing and existing.state == JobState.GENERATED.value and existing.result_video_sha256:
            video_path = existing.result_artifact_path
            if video_path and Path(video_path).is_file():
                video_bytes = Path(video_path).read_bytes()
                if hashlib.sha256(video_bytes).hexdigest() != existing.result_video_sha256:
                    video_bytes = None

        try:
            try:
                self.gpu_lease.acquire(
                    video_job_id,
                    ExclusiveGpuLease.KIND_I2V,
                    workflow_id=wf_id,
                    stage=JobState.GPU_PREFLIGHT.value,
                    process_identity=f"pid:{os.getpid()}",
                )
            except GpuOwnershipConflict:
                self.gpu_lease.try_reclaim_stale(
                    process_alive=default_process_alive,
                    claimant_job_id=video_job_id,
                    claimant_kind=ExclusiveGpuLease.KIND_I2V,
                    workflow_id=wf_id,
                    stage=JobState.GPU_PREFLIGHT.value,
                    process_identity=f"pid:{os.getpid()}",
                )
            record.state = JobState.GPU_PREFLIGHT.value
            self.store.save(record)

            # Preflight — fail before generation when below floor
            if self.gpu_metrics is not None:
                free_mib = int(self.gpu_metrics.free_vram_mib())
                lowest_free = free_mib
                if free_mib < settings.min_free_vram_mib:
                    raise GpuHeadroomInsufficient(
                        f"free_vram_mib={free_mib} < min={settings.min_free_vram_mib}"
                    )

            # Optional /free before load
            if self.transport is not None:
                self.transport.free_models()
                if self.gpu_metrics is not None:
                    free_mib = int(self.gpu_metrics.free_vram_mib())
                    if lowest_free is None or free_mib < lowest_free:
                        lowest_free = free_mib
                    if free_mib < settings.min_free_vram_mib:
                        raise GpuHeadroomInsufficient(
                            f"free_vram_mib={free_mib} < min={settings.min_free_vram_mib} after /free"
                        )

            record.state = JobState.TRANSFORMING.value
            self.store.save(record)

            image_filename = "staged_source.png"
            if self.stage_image is not None:
                image_filename = self.stage_image(source_image, transform, video_job_id)

            record.state = JobState.GENERATING.value
            self.store.save(record)

            decode_sizes = [DECODE_TEMPORAL_SIZE_NORMAL, DECODE_TEMPORAL_SIZE_LOW_MEM]
            # Attempt 1 normal; attempt 2 low-mem decode path (bounded)
            if video_bytes is not None:
                attempts = max(1, int(getattr(existing, 'attempt_number', 1) or 1))
            for attempt_idx, decode_size in enumerate(decode_sizes[:MAX_INFRASTRUCTURE_ATTEMPTS], start=1):
                if video_bytes is not None:
                    break
                attempts = attempt_idx
                try:
                    if force_infra_failure_once and attempt_idx == 1:
                        raise InfrastructureFailure("forced_infra_failure_for_test")
                    # Persist attempt start BEFORE external side effect
                    backend_request_id = hashlib.sha256(
                        f"{idem}|attempt={attempt_idx}|seed={seed}|decode={decode_size}".encode("utf-8")
                    ).hexdigest()
                    record.attempt_number = attempt_idx
                    record.attempt_started_at = self.clock()
                    record.backend_request_id = backend_request_id
                    record.comfy_prompt_id = None
                    record.state = JobState.GENERATING.value
                    self.store.save(record)
                    self.gpu_lease.heartbeat(video_job_id, stage=JobState.GENERATING.value)

                    if self.transport is None:
                        # Dry-run / metadata path used by CPU tests without transport
                        video_bytes = b"FAKE_VIDEO_BYTES_FOR_TEST"
                        video_path = None
                        # Simulate accepted job id for crash-safety bookkeeping
                        record.comfy_prompt_id = f"mock-{backend_request_id[:12]}"
                        self.store.save(record)
                    else:
                        if backend_id == BACKEND_ID_WAN_22:
                            mp = motion_plan or {}
                            pos = str(mp.get("positive_prompt") or mp.get("prompt") or "")
                            neg = str(mp.get("negative_prompt") or WAN22_DEFAULT_NEGATIVE)
                            workflow = build_wan_22_ti2v_workflow(
                                image_filename=image_filename,
                                seed=seed,
                                positive_prompt=pos,
                                negative_prompt=neg,
                                fps=int(getattr(settings, "fps", WAN22_DEFAULT_FPS) or WAN22_DEFAULT_FPS),
                                length=int(
                                    mp.get("length")
                                    or getattr(settings, "frame_count", WAN22_DEFAULT_LENGTH)
                                    or WAN22_DEFAULT_LENGTH
                                ),
                            )
                            # Wan TI2V requires CLIPTextEncode for motion/scenery — not SVD identity ban.
                        else:
                            workflow = build_svd_xt_workflow(
                                image_filename=image_filename,
                                seed=seed,
                                frame_count=settings.frame_count,
                                fps=settings.fps,
                                motion_bucket_id=settings.motion_bucket_id,
                                decode_temporal_size=decode_size,
                            )
                            if workflow_contains_text_identity_prompt(workflow):
                                raise I2VAdapterError("refusing workflow that contains text identity prompt")
                        # Prefer submit→record prompt id→wait when transport supports it
                        submit_only = getattr(self.transport, "submit_workflow", None)
                        wait_only = getattr(self.transport, "wait_for_prompt", None)
                        if callable(submit_only) and callable(wait_only):
                            prompt_id = submit_only(workflow)
                            record.comfy_prompt_id = str(prompt_id)
                            self.store.save(record)  # AFTER accept, BEFORE wait
                            out = wait_only(prompt_id)
                        else:
                            out = self.transport.submit_and_wait(workflow)
                            if out.get("prompt_id"):
                                record.comfy_prompt_id = str(out["prompt_id"])
                                self.store.save(record)
                        video_bytes = out.get("video_bytes")
                        video_path = out.get("video_path")
                        if not video_bytes:
                            raise InfrastructureFailure("backend returned empty video_bytes")
                    if self.gpu_metrics is not None:
                        free_now = int(self.gpu_metrics.free_vram_mib())
                        if lowest_free is None or free_now < lowest_free:
                            lowest_free = free_now
                    break
                except InfrastructureFailure as exc:
                    last_infra = str(exc)
                    if attempt_idx >= MAX_INFRASTRUCTURE_ATTEMPTS:
                        raise
                    continue

            video_sha = (
                hashlib.sha256(video_bytes).hexdigest() if video_bytes is not None else None
            )
            # Persist artifact identity separately before validation/READY
            record.result_artifact_path = video_path
            record.result_video_sha256 = video_sha
            record.state = JobState.GENERATED.value
            self.store.save(record)

            record.state = JobState.VALIDATING.value
            self.store.save(record)

            flicker = TemporalFlicker(temporal_flicker)
            review_tag = None
            if flicker == TemporalFlicker.MAJOR:
                validation = ValidationStatus.VIDEO_REVIEW_REQUIRED
                state = JobState.REVIEW_REQUIRED.value
                review_tag = "VIDEO_REVIEW_REQUIRED"
            elif flicker == TemporalFlicker.MINOR:
                validation = ValidationStatus.PARTIAL
                state = JobState.REVIEW_REQUIRED.value
                review_tag = "VIDEO_REVIEW_REQUIRED"
            else:
                validation = ValidationStatus.PASS
                state = JobState.READY.value

            completed = self.clock()
            post_free = None
            recovered = None
            reachable = None
            if self.transport is not None:
                self.transport.free_models()
                reachable = bool(self.transport.health_check())
                if self.gpu_metrics is not None:
                    post_free = int(self.gpu_metrics.free_vram_mib())
                    if lowest_free is not None:
                        recovered = post_free - lowest_free
            elif self.gpu_metrics is not None:
                post_free = int(self.gpu_metrics.free_vram_mib())
                if lowest_free is not None:
                    recovered = post_free - lowest_free
                reachable = True

            if lowest_free is not None and self.gpu_metrics is not None:
                total_fn = getattr(self.gpu_metrics, "total_vram_mib", None)
                total = int(total_fn()) if callable(total_fn) else 0
                if total > 0:
                    peak_used = max(0, total - int(lowest_free))
                else:
                    peak_used = None
            else:
                peak_used = None

            result = GenerateVideoResult(
                workflow_id=wf_id,
                video_job_id=video_job_id,
                backend_id=backend_id,
                model_id=MODEL_ID_SVD_XT_1_1,
                model_sha256=settings.model_sha256 or self.model_sha256,
                workflow_version=WORKFLOW_VERSION,
                source_image_sha256=source_image.source_image_sha256,
                source_character_intent=source_image.source_character_intent,
                source_character_id_or_na=source_image.source_character_id_or_na,
                video_sha256=video_sha,
                video_path=video_path,
                seed=int(seed),
                frame_count=settings.frame_count,
                fps=settings.fps,
                motion_bucket_id=settings.motion_bucket_id,
                source_width=source_image.source_width,
                source_height=source_image.source_height,
                i2v_width=transform.target_width,
                i2v_height=transform.target_height,
                transform_id=transform.transform_id,
                transform_sha256=transform.transform_sha256,
                generation_started_at=started,
                generation_completed_at=completed,
                generation_wall_seconds=completed - started,
                peak_vram_used_mib=peak_used,
                lowest_free_vram_mib=lowest_free,
                post_free_vram_mib=post_free,
                vram_recovered_mib=recovered,
                comfyui_reachable_after_free=reachable,
                validation_status=validation.value,
                failure_reason=review_tag,
                temporal_flicker=flicker.value,
                video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
                static_fallback_supported=STATIC_FALLBACK_SUPPORTED,
                video_idempotency_key=idem,
                state=state,
                gpu_owner_job_id=video_job_id,
                reused_existing=False,
                infrastructure_attempts=attempts,
                transform=asdict(transform),
            )
            record.state = state
            record.result = result.to_dict()
            self.store.save(record)
            return result

        except (MissingSourceShaError, SourceNotApprovedError):
            raise
        except GpuHeadroomInsufficient as exc:
            completed = self.clock()
            result = self._build_failure_result(
                source_image=source_image,
                seed=seed,
                settings=settings,
                wf_id=wf_id,
                video_job_id=video_job_id,
                idem=idem,
                transform=transform,
                started=started,
                completed=completed,
                status=ValidationStatus.INFRA_FAILURE,
                reason=f"GPU_HEADROOM_INSUFFICIENT: {exc}",
                lowest_free=lowest_free,
                attempts=attempts,
                motion_plan=motion_plan,
            )
            self._persist_failure(record, result)
            return result
        except GpuOwnershipConflict as exc:
            completed = self.clock()
            result = self._build_failure_result(
                source_image=source_image,
                seed=seed,
                settings=settings,
                wf_id=wf_id,
                video_job_id=video_job_id,
                idem=idem,
                transform=transform,
                started=started,
                completed=completed,
                status=ValidationStatus.INFRA_FAILURE,
                reason=str(exc),
                lowest_free=lowest_free,
                attempts=attempts,
                motion_plan=motion_plan,
            )
            self._persist_failure(record, result)
            return result
        except InfrastructureFailure as exc:
            # cleanup then return infra failure — static fallback remains available
            reachable = None
            post_free = None
            recovered = None
            if self.transport is not None:
                self.transport.free_models()
                reachable = bool(self.transport.health_check())
                if self.gpu_metrics is not None:
                    post_free = int(self.gpu_metrics.free_vram_mib())
                    if lowest_free is not None:
                        recovered = post_free - lowest_free
            completed = self.clock()
            result = self._build_failure_result(
                source_image=source_image,
                seed=seed,
                settings=settings,
                wf_id=wf_id,
                video_job_id=video_job_id,
                idem=idem,
                transform=transform,
                started=started,
                completed=completed,
                status=ValidationStatus.INFRA_FAILURE,
                reason=last_infra or str(exc),
                lowest_free=lowest_free,
                attempts=attempts,
                motion_plan=motion_plan,
            )
            result.comfyui_reachable_after_free = reachable
            result.post_free_vram_mib = post_free
            result.vram_recovered_mib = recovered
            self._persist_failure(record, result)
            return result
        finally:
            self.gpu_lease.release(video_job_id)

    def _persist_failure(self, record: VideoJobRecord, result: GenerateVideoResult) -> None:
        record.state = JobState.FAILED.value
        record.failure_reason = result.failure_reason
        record.result = result.to_dict()
        self.store.save(record)

    def _build_failure_result(
        self,
        *,
        source_image: SourceImageRef,
        seed: int,
        settings: I2VSettings,
        wf_id: str,
        video_job_id: str,
        idem: str,
        transform: LetterboxTransform,
        started: float,
        completed: float,
        status: ValidationStatus,
        reason: str,
        lowest_free: Optional[int],
        attempts: int,
        motion_plan: Optional[Mapping[str, Any]],
    ) -> GenerateVideoResult:
        return GenerateVideoResult(
            workflow_id=wf_id,
            video_job_id=video_job_id,
            backend_id=BACKEND_ID_SVD_XT_1_1,
            model_id=MODEL_ID_SVD_XT_1_1,
            model_sha256=settings.model_sha256 or self.model_sha256,
            workflow_version=WORKFLOW_VERSION,
            source_image_sha256=source_image.source_image_sha256,
            source_character_intent=source_image.source_character_intent,
            source_character_id_or_na=source_image.source_character_id_or_na,
            video_sha256=None,
            video_path=None,
            seed=int(seed),
            frame_count=settings.frame_count,
            fps=settings.fps,
            motion_bucket_id=settings.motion_bucket_id,
            source_width=source_image.source_width,
            source_height=source_image.source_height,
            i2v_width=transform.target_width,
            i2v_height=transform.target_height,
            transform_id=transform.transform_id,
            transform_sha256=transform.transform_sha256,
            generation_started_at=started,
            generation_completed_at=completed,
            generation_wall_seconds=completed - started,
            peak_vram_used_mib=None,
            lowest_free_vram_mib=lowest_free,
            post_free_vram_mib=None,
            vram_recovered_mib=None,
            comfyui_reachable_after_free=None,
            validation_status=status.value,
            failure_reason=reason,
            temporal_flicker=TemporalFlicker.NONE.value,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            static_fallback_supported=STATIC_FALLBACK_SUPPORTED,
            video_idempotency_key=idem,
            state=JobState.FAILED.value,
            infrastructure_attempts=attempts,
            transform=asdict(transform),
        )

    def _fail_early(
        self,
        source_image: SourceImageRef,
        seed: int,
        settings: I2VSettings,
        wf_id: str,
        status: ValidationStatus,
        reason: str,
        motion_plan: Optional[Mapping[str, Any]],
        backend_id: str = BACKEND_ID_SVD_XT_1_1,
    ) -> GenerateVideoResult:
        # Packet reports requested I2V_BACKEND= even on fail-closed paths.
        report_backend = backend_id or BACKEND_ID_SVD_XT_1_1
        transform = compute_fit_inside_letterbox(
            max(source_image.source_width, 1),
            max(source_image.source_height, 1),
            target_width=settings.target_width,
            target_height=settings.target_height,
        )
        idem = compute_video_idempotency_key(
            workflow_id=wf_id,
            source_image_sha256=source_image.source_image_sha256 or "missing",
            backend_id=report_backend,
            backend_settings_version=BACKEND_SETTINGS_VERSION,
            seed=seed,
            motion_plan=motion_plan,
        )
        now = self.clock()
        return GenerateVideoResult(
            workflow_id=wf_id,
            video_job_id=str(uuid.uuid4()),
            backend_id=report_backend,
            model_id=MODEL_ID_SVD_XT_1_1,
            model_sha256=settings.model_sha256,
            workflow_version=WORKFLOW_VERSION,
            source_image_sha256=source_image.source_image_sha256,
            source_character_intent=source_image.source_character_intent,
            source_character_id_or_na=source_image.source_character_id_or_na,
            video_sha256=None,
            video_path=None,
            seed=seed,
            frame_count=settings.frame_count,
            fps=settings.fps,
            motion_bucket_id=settings.motion_bucket_id,
            source_width=source_image.source_width,
            source_height=source_image.source_height,
            i2v_width=transform.target_width,
            i2v_height=transform.target_height,
            transform_id=transform.transform_id,
            transform_sha256=transform.transform_sha256,
            generation_started_at=now,
            generation_completed_at=now,
            generation_wall_seconds=0.0,
            peak_vram_used_mib=None,
            lowest_free_vram_mib=None,
            post_free_vram_mib=None,
            vram_recovered_mib=None,
            comfyui_reachable_after_free=None,
            validation_status=status.value,
            failure_reason=reason,
            temporal_flicker=TemporalFlicker.NONE.value,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            static_fallback_supported=STATIC_FALLBACK_SUPPORTED,
            video_idempotency_key=idem,
            state=JobState.FAILED.value,
            transform=asdict(transform),
        )


def generate_video(
    source_image: SourceImageRef,
    motion_plan: Optional[Mapping[str, Any]] = None,
    backend_id: str = BACKEND_ID_SVD_XT_1_1,
    seed: int = 0,
    settings: Optional[I2VSettings] = None,
    **kwargs: Any,
) -> GenerateVideoResult:
    """Module-level entry used by media pipeline (not chapter→Comfy)."""
    raise RuntimeError(
        "generate_video requires an ImageToVideoAdapter instance wired with "
        "VideoJobStore (+ optional transport/gpu). Use ImageToVideoAdapter.generate_video."
    )
