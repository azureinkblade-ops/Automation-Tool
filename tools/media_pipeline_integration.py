"""MEDIA_PIPELINE_INTEGRATION — approved still → I2V → presentation → social record.

Bounded lane: no Patreon / Royal Road / social publishing / chapter wiring.
Restart-safe, idempotent, hash-bound. Static approved still is fallback when
I2V or presentation fails.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol


VIDEO_CREATES_IDENTITY_CANON = False
PIPELINE_VERSION = "media_pipeline_v1"


class PipelineState(str, Enum):
    QUEUED = "QUEUED"
    STILL_BOUND = "STILL_BOUND"
    I2V = "I2V"
    PRESENTING = "PRESENTING"
    READY = "READY"
    STATIC_FALLBACK = "STATIC_FALLBACK"
    FAILED = "FAILED"


class PipelineOutcome(str, Enum):
    SOCIAL_READY = "SOCIAL_READY"
    STATIC_FALLBACK = "STATIC_FALLBACK"
    FAILED = "FAILED"


@dataclass
class ApprovedStillRef:
    image_path: str
    source_image_sha256: str
    image_source_approved: bool = True
    source_character_intent: str = "INTENT_NO"
    source_character_id_or_na: str = "n/a"
    source_width: int = 768
    source_height: int = 1344


@dataclass
class SocialMediaRecord:
    media_record_id: str
    workflow_id: str
    idempotency_key: str
    state: str
    outcome: str
    source_image_sha256: str
    raw_video_sha256: Optional[str] = None
    presented_video_sha256: Optional[str] = None
    asset_path: Optional[str] = None
    asset_sha256: Optional[str] = None
    asset_kind: str = "none"  # presented_mp4 | static_still
    video_creates_identity_canon: bool = False
    failure_reason: Optional[str] = None
    i2v_job_id: Optional[str] = None
    presentation_job_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    updated_at: float = field(default_factory=time.time)


class MediaRecordStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[SocialMediaRecord]:
        path = self._path(key)
        if not path.exists():
            return None
        return SocialMediaRecord(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, record: SocialMediaRecord) -> None:
        record.updated_at = time.time()
        path = self._path(record.idempotency_key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(asdict(record), indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)

    def verify_ready_asset(self, record: SocialMediaRecord) -> bool:
        if record.state not in {PipelineState.READY.value, PipelineState.STATIC_FALLBACK.value}:
            return False
        if not record.asset_sha256 or not record.asset_path:
            return False
        path = Path(record.asset_path)
        if not path.is_file():
            return False
        return _sha256_file(path) == record.asset_sha256


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_pipeline_idempotency_key(
    *,
    workflow_id: str,
    source_image_sha256: str,
    seed: int,
) -> str:
    raw = f"{PIPELINE_VERSION}|{workflow_id}|still={source_image_sha256}|seed={seed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class I2VPort(Protocol):
    def generate_video(self, still: ApprovedStillRef, *, seed: int, workflow_id: str) -> Any: ...


class PresentationPort(Protocol):
    def present_video(self, raw_video_path: str, video_sha256: str, source_image_sha256: str, *, workflow_id: str) -> Any: ...


@dataclass
class PipelineResult:
    workflow_id: str
    media_record_id: str
    idempotency_key: str
    outcome: str
    state: str
    source_image_sha256: str
    asset_path: Optional[str]
    asset_sha256: Optional[str]
    asset_kind: str
    raw_video_sha256: Optional[str]
    presented_video_sha256: Optional[str]
    video_creates_identity_canon: bool
    failure_reason: Optional[str]
    reused_existing: bool = False
    i2v_job_id: Optional[str] = None
    presentation_job_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MediaPipeline:
    store: MediaRecordStore
    i2v: I2VPort
    presentation: PresentationPort
    clock: Callable[[], float] = time.time

    def produce_social_media(
        self,
        still: ApprovedStillRef,
        *,
        workflow_id: Optional[str] = None,
        seed: int = 0,
    ) -> PipelineResult:
        if not still.image_source_approved:
            raise ValueError("approved still required")
        if not still.source_image_sha256:
            raise ValueError("source_image_sha256 required")

        # Bind still bytes when path present
        still_path = Path(still.image_path) if still.image_path else None
        if still_path is not None and still_path.is_file():
            actual = _sha256_file(still_path)
            if actual != still.source_image_sha256:
                return self._failed(
                    workflow_id or str(uuid.uuid4()),
                    still,
                    seed,
                    "source_image_sha256 mismatch",
                )

        wf_id = workflow_id or str(uuid.uuid4())
        idem = compute_pipeline_idempotency_key(
            workflow_id=wf_id,
            source_image_sha256=still.source_image_sha256,
            seed=seed,
        )

        existing = self.store.get(idem)
        if existing and existing.state in {PipelineState.READY.value, PipelineState.STATIC_FALLBACK.value}:
            if self.store.verify_ready_asset(existing) and existing.result:
                reused = PipelineResult(**existing.result)
                reused.reused_existing = True
                return reused
            existing.state = PipelineState.QUEUED.value
            existing.failure_reason = "READY_ASSET_HASH_MISMATCH"
            self.store.save(existing)

        record_id = existing.media_record_id if existing else str(uuid.uuid4())
        record = SocialMediaRecord(
            media_record_id=record_id,
            workflow_id=wf_id,
            idempotency_key=idem,
            state=PipelineState.QUEUED.value,
            outcome=PipelineOutcome.FAILED.value,
            source_image_sha256=still.source_image_sha256,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
        )
        self.store.save(record)

        record.state = PipelineState.STILL_BOUND.value
        self.store.save(record)

        # --- I2V ---
        record.state = PipelineState.I2V.value
        self.store.save(record)
        raw_path = None
        raw_sha = None
        i2v_job_id = None
        try:
            i2v_result = self.i2v.generate_video(still, seed=seed, workflow_id=wf_id)
            status = getattr(i2v_result, "validation_status", None) or (i2v_result.get("validation_status") if isinstance(i2v_result, dict) else None)
            if status not in {"PASS", "PARTIAL", "VIDEO_REVIEW_REQUIRED"}:
                raise RuntimeError(f"i2v_status={status}")
            raw_path = getattr(i2v_result, "video_path", None) or (i2v_result.get("video_path") if isinstance(i2v_result, dict) else None)
            raw_sha = getattr(i2v_result, "video_sha256", None) or (i2v_result.get("video_sha256") if isinstance(i2v_result, dict) else None)
            i2v_job_id = getattr(i2v_result, "video_job_id", None) or (i2v_result.get("video_job_id") if isinstance(i2v_result, dict) else None)
            if not raw_sha:
                raise RuntimeError("i2v missing video_sha256")
            record.raw_video_sha256 = raw_sha
            record.i2v_job_id = i2v_job_id
            self.store.save(record)
        except Exception as exc:  # noqa: BLE001
            return self._static_fallback(record, still, reason=f"i2v_failed:{exc}")

        # --- Presentation ---
        record.state = PipelineState.PRESENTING.value
        self.store.save(record)
        try:
            pres = self.presentation.present_video(
                str(raw_path or ""),
                str(raw_sha),
                still.source_image_sha256,
                workflow_id=wf_id,
            )
            p_status = getattr(pres, "validation_status", None) or (pres.get("validation_status") if isinstance(pres, dict) else None)
            if p_status != "PASS":
                raise RuntimeError(f"presentation_status={p_status}")
            asset_path = getattr(pres, "presented_video_path", None) or (pres.get("presented_video_path") if isinstance(pres, dict) else None)
            asset_sha = getattr(pres, "presented_video_sha256", None) or (pres.get("presented_video_sha256") if isinstance(pres, dict) else None)
            pres_job = getattr(pres, "presentation_job_id", None) or (pres.get("presentation_job_id") if isinstance(pres, dict) else None)
            if not asset_sha or not asset_path:
                raise RuntimeError("presentation missing asset identity")
            # Prefer rehash of file when present
            if Path(asset_path).is_file() and _sha256_file(Path(asset_path)) != asset_sha:
                raise RuntimeError("presented asset hash mismatch")
            record.presented_video_sha256 = asset_sha
            record.presentation_job_id = pres_job
            record.asset_path = asset_path
            record.asset_sha256 = asset_sha
            record.asset_kind = "presented_mp4"
            record.state = PipelineState.READY.value
            record.outcome = PipelineOutcome.SOCIAL_READY.value
            result = PipelineResult(
                workflow_id=wf_id,
                media_record_id=record.media_record_id,
                idempotency_key=idem,
                outcome=record.outcome,
                state=record.state,
                source_image_sha256=still.source_image_sha256,
                asset_path=asset_path,
                asset_sha256=asset_sha,
                asset_kind="presented_mp4",
                raw_video_sha256=raw_sha,
                presented_video_sha256=asset_sha,
                video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
                failure_reason=None,
                i2v_job_id=i2v_job_id,
                presentation_job_id=pres_job,
            )
            record.result = result.to_dict()
            self.store.save(record)
            return result
        except Exception as exc:  # noqa: BLE001
            return self._static_fallback(record, still, reason=f"presentation_failed:{exc}")

    def _static_fallback(self, record: SocialMediaRecord, still: ApprovedStillRef, *, reason: str) -> PipelineResult:
        asset_path = still.image_path
        asset_sha = still.source_image_sha256
        if asset_path and Path(asset_path).is_file():
            asset_sha = _sha256_file(Path(asset_path))
        record.state = PipelineState.STATIC_FALLBACK.value
        record.outcome = PipelineOutcome.STATIC_FALLBACK.value
        record.asset_path = asset_path
        record.asset_sha256 = asset_sha
        record.asset_kind = "static_still"
        record.failure_reason = reason
        record.video_creates_identity_canon = VIDEO_CREATES_IDENTITY_CANON
        result = PipelineResult(
            workflow_id=record.workflow_id,
            media_record_id=record.media_record_id,
            idempotency_key=record.idempotency_key,
            outcome=record.outcome,
            state=record.state,
            source_image_sha256=still.source_image_sha256,
            asset_path=asset_path,
            asset_sha256=asset_sha,
            asset_kind="static_still",
            raw_video_sha256=record.raw_video_sha256,
            presented_video_sha256=None,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            failure_reason=reason,
            i2v_job_id=record.i2v_job_id,
            presentation_job_id=record.presentation_job_id,
        )
        record.result = result.to_dict()
        self.store.save(record)
        return result

    def _failed(self, wf_id: str, still: ApprovedStillRef, seed: int, reason: str) -> PipelineResult:
        idem = compute_pipeline_idempotency_key(
            workflow_id=wf_id, source_image_sha256=still.source_image_sha256 or "missing", seed=seed
        )
        return PipelineResult(
            workflow_id=wf_id,
            media_record_id=str(uuid.uuid4()),
            idempotency_key=idem,
            outcome=PipelineOutcome.FAILED.value,
            state=PipelineState.FAILED.value,
            source_image_sha256=still.source_image_sha256,
            asset_path=None,
            asset_sha256=None,
            asset_kind="none",
            raw_video_sha256=None,
            presented_video_sha256=None,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            failure_reason=reason,
        )
