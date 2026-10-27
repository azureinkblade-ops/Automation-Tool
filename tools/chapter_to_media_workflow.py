"""CHAPTER_TO_MEDIA_WORKFLOW_INTEGRATION

validated chapter → image request → approved still → media pipeline → social-ready record

Out of scope: Patreon, Royal Road, social publishing, posting automation.
Restart-safe / idempotent. Static fallback from media pipeline is a successful
non-blocking chapter media outcome (not a chapter failure).
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

from tools.media_pipeline_integration import (
    VIDEO_CREATES_IDENTITY_CANON,
    ApprovedStillRef,
    MediaPipeline,
    PipelineOutcome,
)


WORKFLOW_VERSION = "chapter_to_media_v1"


class ChapterMediaState(str, Enum):
    QUEUED = "QUEUED"
    IMAGE_REQUESTED = "IMAGE_REQUESTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    MEDIA_RUNNING = "MEDIA_RUNNING"
    READY = "READY"
    READY_STATIC_FALLBACK = "READY_STATIC_FALLBACK"
    FAILED = "FAILED"


class ChapterMediaOutcome(str, Enum):
    SOCIAL_READY = "SOCIAL_READY"
    STATIC_FALLBACK = "STATIC_FALLBACK"
    FAILED = "FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


@dataclass
class ValidatedChapterRef:
    chapter_id: str
    novel_id: str
    validation_status: str = "VALIDATED"  # must be VALIDATED
    workflow_id: Optional[str] = None


@dataclass
class ImageRequestResult:
    request_id: str
    still: Optional[ApprovedStillRef] = None
    awaiting_approval: bool = False
    failure_reason: Optional[str] = None


class ImageRequestPort(Protocol):
    def request_approved_still(self, chapter: ValidatedChapterRef, *, workflow_id: str) -> ImageRequestResult: ...


@dataclass
class ChapterMediaRecord:
    chapter_media_job_id: str
    chapter_id: str
    novel_id: str
    workflow_id: str
    idempotency_key: str
    state: str
    outcome: str
    image_request_id: Optional[str] = None
    source_image_sha256: Optional[str] = None
    media_record_id: Optional[str] = None
    media_outcome: Optional[str] = None
    asset_path: Optional[str] = None
    asset_sha256: Optional[str] = None
    asset_kind: Optional[str] = None
    video_creates_identity_canon: bool = False
    failure_reason: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    updated_at: float = field(default_factory=time.time)


class ChapterMediaStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[ChapterMediaRecord]:
        path = self._path(key)
        if not path.exists():
            return None
        return ChapterMediaRecord(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, record: ChapterMediaRecord) -> None:
        record.updated_at = time.time()
        path = self._path(record.idempotency_key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(asdict(record), indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)

    def verify_ready_asset(self, record: ChapterMediaRecord) -> bool:
        if record.state not in {
            ChapterMediaState.READY.value,
            ChapterMediaState.READY_STATIC_FALLBACK.value,
        }:
            return False
        if not record.asset_sha256 or not record.asset_path:
            return False
        p = Path(record.asset_path)
        if not p.is_file():
            return False
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest() == record.asset_sha256


def compute_chapter_media_idempotency_key(*, chapter_id: str, novel_id: str, workflow_id: str) -> str:
    raw = f"{WORKFLOW_VERSION}|novel={novel_id}|chapter={chapter_id}|wf={workflow_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ChapterMediaResult:
    chapter_id: str
    novel_id: str
    workflow_id: str
    chapter_media_job_id: str
    idempotency_key: str
    outcome: str
    state: str
    asset_path: Optional[str]
    asset_sha256: Optional[str]
    asset_kind: Optional[str]
    media_outcome: Optional[str]
    video_creates_identity_canon: bool
    failure_reason: Optional[str]
    reused_existing: bool = False
    awaiting_approval: bool = False
    publishing_wired: bool = False
    chapter_posting_wired: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChapterToMediaWorkflow:
    store: ChapterMediaStore
    image_requests: ImageRequestPort
    media_pipeline: MediaPipeline
    clock: Callable[[], float] = time.time

    def enqueue_chapter_media(
        self,
        chapter: ValidatedChapterRef,
        *,
        seed: int = 0,
    ) -> ChapterMediaResult:
        if chapter.validation_status != "VALIDATED":
            raise ValueError(f"chapter not VALIDATED: {chapter.validation_status}")

        wf_id = chapter.workflow_id or str(uuid.uuid4())
        idem = compute_chapter_media_idempotency_key(
            chapter_id=chapter.chapter_id,
            novel_id=chapter.novel_id,
            workflow_id=wf_id,
        )

        existing = self.store.get(idem)
        if existing and existing.state in {
            ChapterMediaState.READY.value,
            ChapterMediaState.READY_STATIC_FALLBACK.value,
        }:
            if self.store.verify_ready_asset(existing) and existing.result:
                reused = ChapterMediaResult(**existing.result)
                reused.reused_existing = True
                return reused
            existing.state = ChapterMediaState.QUEUED.value
            existing.failure_reason = "READY_ASSET_HASH_MISMATCH"
            self.store.save(existing)

        job_id = existing.chapter_media_job_id if existing else str(uuid.uuid4())
        record = ChapterMediaRecord(
            chapter_media_job_id=job_id,
            chapter_id=chapter.chapter_id,
            novel_id=chapter.novel_id,
            workflow_id=wf_id,
            idempotency_key=idem,
            state=ChapterMediaState.QUEUED.value,
            outcome=ChapterMediaOutcome.FAILED.value,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
        )
        self.store.save(record)

        # Image request
        record.state = ChapterMediaState.IMAGE_REQUESTED.value
        self.store.save(record)
        try:
            img = self.image_requests.request_approved_still(chapter, workflow_id=wf_id)
        except Exception as exc:  # noqa: BLE001
            return self._fail(record, f"image_request_failed:{exc}")

        record.image_request_id = img.request_id
        if img.awaiting_approval or (img.still is None):
            record.state = ChapterMediaState.AWAITING_APPROVAL.value
            record.outcome = ChapterMediaOutcome.AWAITING_APPROVAL.value
            result = ChapterMediaResult(
                chapter_id=chapter.chapter_id,
                novel_id=chapter.novel_id,
                workflow_id=wf_id,
                chapter_media_job_id=job_id,
                idempotency_key=idem,
                outcome=record.outcome,
                state=record.state,
                asset_path=None,
                asset_sha256=None,
                asset_kind=None,
                media_outcome=None,
                video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
                failure_reason=img.failure_reason,
                awaiting_approval=True,
            )
            record.result = result.to_dict()
            self.store.save(record)
            return result

        still = img.still
        assert still is not None
        if not still.image_source_approved:
            return self._fail(record, "still_not_approved")

        record.source_image_sha256 = still.source_image_sha256
        record.state = ChapterMediaState.MEDIA_RUNNING.value
        self.store.save(record)

        media = self.media_pipeline.produce_social_media(still, workflow_id=wf_id, seed=seed)
        record.media_record_id = media.media_record_id
        record.media_outcome = media.outcome
        record.asset_path = media.asset_path
        record.asset_sha256 = media.asset_sha256
        record.asset_kind = media.asset_kind

        if media.outcome == PipelineOutcome.SOCIAL_READY.value:
            record.state = ChapterMediaState.READY.value
            record.outcome = ChapterMediaOutcome.SOCIAL_READY.value
        elif media.outcome == PipelineOutcome.STATIC_FALLBACK.value:
            # Non-blocking: chapter media succeeds with static still
            record.state = ChapterMediaState.READY_STATIC_FALLBACK.value
            record.outcome = ChapterMediaOutcome.STATIC_FALLBACK.value
            record.failure_reason = media.failure_reason
        else:
            return self._fail(record, media.failure_reason or "media_pipeline_failed")

        result = ChapterMediaResult(
            chapter_id=chapter.chapter_id,
            novel_id=chapter.novel_id,
            workflow_id=wf_id,
            chapter_media_job_id=job_id,
            idempotency_key=idem,
            outcome=record.outcome,
            state=record.state,
            asset_path=record.asset_path,
            asset_sha256=record.asset_sha256,
            asset_kind=record.asset_kind,
            media_outcome=record.media_outcome,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            failure_reason=record.failure_reason,
        )
        record.result = result.to_dict()
        self.store.save(record)
        return result

    def _fail(self, record: ChapterMediaRecord, reason: str) -> ChapterMediaResult:
        record.state = ChapterMediaState.FAILED.value
        record.outcome = ChapterMediaOutcome.FAILED.value
        record.failure_reason = reason
        result = ChapterMediaResult(
            chapter_id=record.chapter_id,
            novel_id=record.novel_id,
            workflow_id=record.workflow_id,
            chapter_media_job_id=record.chapter_media_job_id,
            idempotency_key=record.idempotency_key,
            outcome=record.outcome,
            state=record.state,
            asset_path=None,
            asset_sha256=None,
            asset_kind=None,
            media_outcome=None,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            failure_reason=reason,
        )
        record.result = result.to_dict()
        self.store.save(record)
        return result
