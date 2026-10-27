"""I2V presentation adapter: raw SVD 1024x576 -> social-ready 9:16 MP4.

Bounded lane: I2V_PRESENTATION_ADAPTER_IMPLEMENTATION
- Input: raw SVD clip (native 1024x576) with authoritative video_sha256
- Output: 9:16 social MP4 (default 1080x1920) via FIT_INSIDE + LETTERBOX/PILLARBOX
- No crop / no stretch of semantic content by default
- VIDEO_CREATES_IDENTITY_CANON = NO (presentation never promotes identity canon)
- No chapter orchestration / posting wiring
- Content hashes authoritative over paths
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional


PRESENTATION_TRANSFORM_ID = "FIT_INSIDE_LETTERBOX_9x16"
SVD_NATIVE_WIDTH = 1024
SVD_NATIVE_HEIGHT = 576
DEFAULT_SOCIAL_WIDTH = 1080
DEFAULT_SOCIAL_HEIGHT = 1920  # 9:16
VIDEO_CREATES_IDENTITY_CANON = False
WORKFLOW_VERSION = "i2v_presentation_v1"


class PresentationState(str, Enum):
    QUEUED = "QUEUED"
    VERIFYING_SOURCE = "VERIFYING_SOURCE"
    TRANSFORMING = "TRANSFORMING"
    READY = "READY"
    FAILED = "FAILED"


class PresentationValidation(str, Enum):
    PASS = "PASS"
    INFRA_FAILURE = "INFRA_FAILURE"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"


class PresentationError(Exception):
    code = "PRESENTATION_ERROR"


class SourceVideoHashMismatch(PresentationError):
    code = "SOURCE_HASH_MISMATCH"


@dataclass
class PresentationTransform:
    transform_id: str
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    content_width: int
    content_height: int
    pad_left: int
    pad_right: int
    pad_top: int
    pad_bottom: int
    transform_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_fit_inside_letterbox_9x16(
    source_width: int = SVD_NATIVE_WIDTH,
    source_height: int = SVD_NATIVE_HEIGHT,
    target_width: int = DEFAULT_SOCIAL_WIDTH,
    target_height: int = DEFAULT_SOCIAL_HEIGHT,
) -> PresentationTransform:
    """Scale SVD frame to FIT INSIDE 9:16; pad remaining (no crop, no stretch)."""
    if source_width <= 0 or source_height <= 0:
        raise PresentationError("invalid source dims")
    if target_width <= 0 or target_height <= 0:
        raise PresentationError("invalid target dims")
    scale = min(target_width / source_width, target_height / source_height)
    content_w = int(round(source_width * scale))
    content_h = int(round(source_height * scale))
    # Keep aspect exact: prefer rounding that does not exceed target
    if content_w > target_width:
        content_w = target_width
    if content_h > target_height:
        content_h = target_height
    pad_x = target_width - content_w
    pad_y = target_height - content_h
    pad_left = pad_x // 2
    pad_right = pad_x - pad_left
    pad_top = pad_y // 2
    pad_bottom = pad_y - pad_top
    desc = (
        f"{PRESENTATION_TRANSFORM_ID}|src={source_width}x{source_height}|"
        f"tgt={target_width}x{target_height}|content={content_w}x{content_h}|"
        f"pad=L{pad_left}/R{pad_right}/T{pad_top}/B{pad_bottom}|nocrop|nostretch"
    )
    return PresentationTransform(
        transform_id=PRESENTATION_TRANSFORM_ID,
        source_width=source_width,
        source_height=source_height,
        target_width=target_width,
        target_height=target_height,
        content_width=content_w,
        content_height=content_h,
        pad_left=pad_left,
        pad_right=pad_right,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        transform_sha256=hashlib.sha256(desc.encode("utf-8")).hexdigest(),
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class RawSvdClipRef:
    video_path: str
    video_sha256: str
    source_image_sha256: str
    width: int = SVD_NATIVE_WIDTH
    height: int = SVD_NATIVE_HEIGHT
    frame_count: int = 25
    fps: int = 6


@dataclass
class PresentationJobRecord:
    presentation_job_id: str
    workflow_id: str
    idempotency_key: str
    state: str
    source_video_sha256: str
    source_image_sha256: str
    result: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    result_artifact_path: Optional[str] = None
    result_video_sha256: Optional[str] = None
    transform_sha256: Optional[str] = None
    updated_at: float = field(default_factory=time.time)


class PresentationJobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{safe}.json"

    def get_by_idempotency(self, key: str) -> Optional[PresentationJobRecord]:
        path = self._path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return PresentationJobRecord(**data)

    def save(self, record: PresentationJobRecord) -> None:
        record.updated_at = time.time()
        path = self._path(record.idempotency_key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(asdict(record), indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)

    def verify_ready_artifact(self, record: PresentationJobRecord) -> bool:
        if not record.result_video_sha256 or not record.result_artifact_path:
            return False
        path = Path(record.result_artifact_path)
        if not path.is_file():
            return False
        return sha256_file(path) == record.result_video_sha256


def compute_presentation_idempotency_key(
    *,
    workflow_id: str,
    source_video_sha256: str,
    target_width: int,
    target_height: int,
    transform_id: str,
) -> str:
    raw = (
        f"pres|{workflow_id}|src={source_video_sha256}|"
        f"tgt={target_width}x{target_height}|tx={transform_id}|{WORKFLOW_VERSION}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class PresentVideoResult:
    workflow_id: str
    presentation_job_id: str
    source_video_sha256: str
    source_image_sha256: str
    presented_video_sha256: Optional[str]
    presented_video_path: Optional[str]
    source_width: int
    source_height: int
    presented_width: int
    presented_height: int
    transform_id: str
    transform_sha256: str
    validation_status: str
    failure_reason: Optional[str]
    video_creates_identity_canon: bool
    presentation_idempotency_key: str
    state: str
    reused_existing: bool = False
    transform: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RenderFn = Callable[[RawSvdClipRef, PresentationTransform, Path], bytes]


def default_ffmpeg_render(clip: RawSvdClipRef, transform: PresentationTransform, out_path: Path) -> bytes:
    """Render with ffmpeg scale+pad (FIT_INSIDE). Requires ffmpeg on PATH or FFMPEG_PATH."""
    ffmpeg = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise PresentationError("ffmpeg not available")
    src = Path(clip.video_path)
    if not src.is_file():
        raise PresentationError(f"missing source video: {src}")
    vf = (
        f"scale={transform.content_width}:{transform.content_height}:force_original_aspect_ratio=decrease,"
        f"pad={transform.target_width}:{transform.target_height}:{transform.pad_left}:{transform.pad_top}:black,"
        f"setsar=1"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.is_file():
        raise PresentationError(f"ffmpeg failed: {proc.stderr[-500:]}")
    return out_path.read_bytes()


def mock_render(clip: RawSvdClipRef, transform: PresentationTransform, out_path: Path) -> bytes:
    """CPU/mock: deterministic bytes tagged with transform + source hash (no ffmpeg)."""
    payload = (
        b"MOCK_PRESENTED_MP4|"
        + transform.transform_sha256.encode("ascii")
        + b"|"
        + clip.video_sha256.encode("ascii")
        + b"|"
        + f"{transform.target_width}x{transform.target_height}".encode("ascii")
    )
    out_path.write_bytes(payload)
    return payload


@dataclass
class I2VPresentationAdapter:
    store: PresentationJobStore
    render: RenderFn = mock_render
    clock: Callable[[], float] = time.time
    output_dir: Optional[Path] = None

    def present_video(
        self,
        clip: RawSvdClipRef,
        *,
        workflow_id: Optional[str] = None,
        target_width: int = DEFAULT_SOCIAL_WIDTH,
        target_height: int = DEFAULT_SOCIAL_HEIGHT,
    ) -> PresentVideoResult:
        wf_id = workflow_id or str(uuid.uuid4())
        transform = compute_fit_inside_letterbox_9x16(
            source_width=clip.width,
            source_height=clip.height,
            target_width=target_width,
            target_height=target_height,
        )
        idem = compute_presentation_idempotency_key(
            workflow_id=wf_id,
            source_video_sha256=clip.video_sha256,
            target_width=target_width,
            target_height=target_height,
            transform_id=transform.transform_id,
        )

        existing = self.store.get_by_idempotency(idem)
        if existing and existing.state == PresentationState.READY.value and existing.result:
            if self.store.verify_ready_artifact(existing):
                reused = PresentVideoResult(**existing.result)
                reused.reused_existing = True
                return reused
            existing.state = PresentationState.QUEUED.value
            existing.failure_reason = "READY_ARTIFACT_HASH_MISMATCH"
            self.store.save(existing)

        job_id = existing.presentation_job_id if existing else str(uuid.uuid4())
        record = PresentationJobRecord(
            presentation_job_id=job_id,
            workflow_id=wf_id,
            idempotency_key=idem,
            state=PresentationState.QUEUED.value,
            source_video_sha256=clip.video_sha256,
            source_image_sha256=clip.source_image_sha256,
            transform_sha256=transform.transform_sha256,
        )
        self.store.save(record)

        try:
            record.state = PresentationState.VERIFYING_SOURCE.value
            self.store.save(record)

            src_path = Path(clip.video_path) if clip.video_path else None
            if src_path is not None and src_path.is_file():
                actual = sha256_file(src_path)
                if actual != clip.video_sha256:
                    raise SourceVideoHashMismatch(
                        f"source video hash mismatch: expected {clip.video_sha256} got {actual}"
                    )
            elif not clip.video_sha256:
                raise PresentationError("video_sha256 required")

            record.state = PresentationState.TRANSFORMING.value
            self.store.save(record)

            out_root = Path(self.output_dir) if self.output_dir else Path(tempfile.mkdtemp(prefix="i2v_pres_"))
            out_root.mkdir(parents=True, exist_ok=True)
            out_path = out_root / f"{job_id}_9x16.mp4"
            presented_bytes = self.render(clip, transform, out_path)
            presented_sha = sha256_bytes(presented_bytes)

            record.result_artifact_path = str(out_path)
            record.result_video_sha256 = presented_sha
            self.store.save(record)

            result = PresentVideoResult(
                workflow_id=wf_id,
                presentation_job_id=job_id,
                source_video_sha256=clip.video_sha256,
                source_image_sha256=clip.source_image_sha256,
                presented_video_sha256=presented_sha,
                presented_video_path=str(out_path),
                source_width=clip.width,
                source_height=clip.height,
                presented_width=transform.target_width,
                presented_height=transform.target_height,
                transform_id=transform.transform_id,
                transform_sha256=transform.transform_sha256,
                validation_status=PresentationValidation.PASS.value,
                failure_reason=None,
                video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
                presentation_idempotency_key=idem,
                state=PresentationState.READY.value,
                transform=transform.to_dict(),
            )
            record.state = PresentationState.READY.value
            record.result = result.to_dict()
            self.store.save(record)
            return result
        except SourceVideoHashMismatch as exc:
            record.state = PresentationState.FAILED.value
            record.failure_reason = str(exc)
            self.store.save(record)
            return self._fail(clip, wf_id, job_id, idem, transform, PresentationValidation.SOURCE_HASH_MISMATCH, str(exc))
        except Exception as exc:  # noqa: BLE001 — surface as INFRA for CPU boundary
            record.state = PresentationState.FAILED.value
            record.failure_reason = str(exc)
            self.store.save(record)
            return self._fail(clip, wf_id, job_id, idem, transform, PresentationValidation.INFRA_FAILURE, str(exc))

    def _fail(
        self,
        clip: RawSvdClipRef,
        wf_id: str,
        job_id: str,
        idem: str,
        transform: PresentationTransform,
        status: PresentationValidation,
        reason: str,
    ) -> PresentVideoResult:
        return PresentVideoResult(
            workflow_id=wf_id,
            presentation_job_id=job_id,
            source_video_sha256=clip.video_sha256,
            source_image_sha256=clip.source_image_sha256,
            presented_video_sha256=None,
            presented_video_path=None,
            source_width=clip.width,
            source_height=clip.height,
            presented_width=transform.target_width,
            presented_height=transform.target_height,
            transform_id=transform.transform_id,
            transform_sha256=transform.transform_sha256,
            validation_status=status.value,
            failure_reason=reason,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            presentation_idempotency_key=idem,
            state=PresentationState.FAILED.value,
            transform=transform.to_dict(),
        )
