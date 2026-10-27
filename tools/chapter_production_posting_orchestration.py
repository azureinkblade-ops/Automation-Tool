"""CHAPTER_PRODUCTION_AND_POSTING_ORCHESTRATION

Wire durable chapter controller around qualified media pieces.

Frozen rules:
- Windows Task Scheduler owns the clock (this module is tick-driven; it does not sleep/schedule).
- Durable controller owns workflow state.
- Hermes only performs prose generation (via HermesPort).
- Patreon backlog takes priority over creating unnecessary new inventory.
- Royal Road posting uses stored remote IDs and idempotency.
- Chapter publication does not wait for video.
- READY_STATIC_FALLBACK is a successful media state for publication.
- Social posting may use static media if video is unavailable or still under review.
- No still/video/social asset becomes identity canon automatically.
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
from typing import Any, Callable, Dict, List, Optional, Protocol

from tools.chapter_to_media_workflow import (
    ChapterMediaOutcome,
    ChapterToMediaWorkflow,
    ValidatedChapterRef,
)
from tools.media_pipeline_integration import VIDEO_CREATES_IDENTITY_CANON


ORCH_VERSION = "chapter_production_posting_v1"


class OrchState(str, Enum):
    QUEUED = "QUEUED"
    SELECTING = "SELECTING"
    GENERATING_PROSE = "GENERATING_PROSE"
    VALIDATING = "VALIDATING"
    STORING = "STORING"
    ENQUEUING_MEDIA = "ENQUEUING_MEDIA"
    PUBLISHING = "PUBLISHING"
    SOCIAL = "SOCIAL"
    READY = "READY"
    FAILED = "FAILED"


class SelectionReason(str, Enum):
    PATREON_BACKLOG = "PATREON_BACKLOG"
    NEXT_INVENTORY = "NEXT_INVENTORY"
    NONE = "NONE"


@dataclass
class BacklogItem:
    chapter_id: str
    novel_id: str
    channel: str  # patreon | inventory
    priority: int = 0


@dataclass
class ChapterDraft:
    chapter_id: str
    novel_id: str
    prose_sha256: str
    body_path: str


@dataclass
class ValidationResult:
    ok: bool
    validation_status: str  # VALIDATED | REJECTED
    reason: Optional[str] = None


@dataclass
class PublishResult:
    channel: str
    remote_id: str
    idempotency_key: str
    status: str  # POSTED | SKIPPED_IDEMPOTENT | FAILED
    failure_reason: Optional[str] = None


@dataclass
class SocialPostResult:
    status: str  # POSTED | SKIPPED_NO_ASSET | FAILED
    asset_kind: Optional[str] = None
    asset_sha256: Optional[str] = None
    failure_reason: Optional[str] = None


class HermesPort(Protocol):
    def generate_prose(self, *, novel_id: str, chapter_id: str, workflow_id: str) -> ChapterDraft: ...


class ValidatorPort(Protocol):
    def validate(self, draft: ChapterDraft) -> ValidationResult: ...


class ChapterStorePort(Protocol):
    def store_validated(self, draft: ChapterDraft, validation: ValidationResult) -> str: ...


class PatreonBacklogPort(Protocol):
    def list_backlog(self) -> List[BacklogItem]: ...


class PatreonPostPort(Protocol):
    def post_chapter(self, *, novel_id: str, chapter_id: str, store_id: str, idempotency_key: str) -> PublishResult: ...


class RoyalRoadPostPort(Protocol):
    def post_chapter(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        store_id: str,
        remote_fiction_id: str,
        idempotency_key: str,
    ) -> PublishResult: ...


class SocialPostPort(Protocol):
    def post_social(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        asset_path: Optional[str],
        asset_sha256: Optional[str],
        asset_kind: Optional[str],
        idempotency_key: str,
    ) -> SocialPostResult: ...


@dataclass
class OrchRecord:
    orch_job_id: str
    workflow_id: str
    idempotency_key: str
    state: str
    novel_id: Optional[str] = None
    chapter_id: Optional[str] = None
    selection_reason: Optional[str] = None
    store_id: Optional[str] = None
    media_outcome: Optional[str] = None
    media_asset_kind: Optional[str] = None
    media_asset_sha256: Optional[str] = None
    patreon_remote_id: Optional[str] = None
    royal_road_remote_id: Optional[str] = None
    social_status: Optional[str] = None
    video_creates_identity_canon: bool = False
    publication_waited_for_video: bool = False
    failure_reason: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    updated_at: float = field(default_factory=time.time)


class OrchStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[OrchRecord]:
        path = self._path(key)
        if not path.exists():
            return None
        return OrchRecord(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, record: OrchRecord) -> None:
        record.updated_at = time.time()
        path = self._path(record.idempotency_key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(asdict(record), indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)


def compute_orch_idempotency_key(*, tick_id: str, workflow_id: str) -> str:
    raw = f"{ORCH_VERSION}|tick={tick_id}|wf={workflow_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_publish_idempotency_key(*, channel: str, novel_id: str, chapter_id: str) -> str:
    raw = f"publish|{channel}|{novel_id}|{chapter_id}|{ORCH_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class OrchResult:
    workflow_id: str
    orch_job_id: str
    idempotency_key: str
    state: str
    novel_id: Optional[str]
    chapter_id: Optional[str]
    selection_reason: Optional[str]
    media_outcome: Optional[str]
    media_asset_kind: Optional[str]
    patreon_status: Optional[str]
    royal_road_status: Optional[str]
    social_status: Optional[str]
    video_creates_identity_canon: bool
    publication_waited_for_video: bool
    failure_reason: Optional[str]
    reused_existing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChapterProductionPostingOrchestrator:
    store: OrchStore
    hermes: HermesPort
    validator: ValidatorPort
    chapter_store: ChapterStorePort
    patreon_backlog: PatreonBacklogPort
    patreon_post: PatreonPostPort
    royal_road_post: RoyalRoadPostPort
    social_post: SocialPostPort
    chapter_media: ChapterToMediaWorkflow
    royal_road_fiction_id_for: Callable[[str], str]
    next_inventory_chapter: Callable[[], Optional[BacklogItem]]
    clock: Callable[[], float] = time.time

    def run_tick(self, *, tick_id: str, workflow_id: Optional[str] = None) -> OrchResult:
        """Entry point for a Task Scheduler tick. Does not sleep or self-schedule."""
        wf_id = workflow_id or str(uuid.uuid4())
        idem = compute_orch_idempotency_key(tick_id=tick_id, workflow_id=wf_id)

        existing = self.store.get(idem)
        if existing and existing.state == OrchState.READY.value and existing.result:
            reused = OrchResult(**existing.result)
            reused.reused_existing = True
            return reused

        job_id = existing.orch_job_id if existing else str(uuid.uuid4())
        record = OrchRecord(
            orch_job_id=job_id,
            workflow_id=wf_id,
            idempotency_key=idem,
            state=OrchState.QUEUED.value,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            publication_waited_for_video=False,
        )
        self.store.save(record)

        try:
            # SELECT — Patreon backlog wins over new inventory
            record.state = OrchState.SELECTING.value
            self.store.save(record)
            backlog = list(self.patreon_backlog.list_backlog() or [])
            backlog_patreon = sorted(
                [b for b in backlog if b.channel == "patreon"],
                key=lambda b: (-b.priority, b.chapter_id),
            )
            selected: Optional[BacklogItem] = None
            reason = SelectionReason.NONE.value
            if backlog_patreon:
                selected = backlog_patreon[0]
                reason = SelectionReason.PATREON_BACKLOG.value
            else:
                selected = self.next_inventory_chapter()
                if selected is not None:
                    reason = SelectionReason.NEXT_INVENTORY.value

            if selected is None:
                record.state = OrchState.READY.value
                record.selection_reason = SelectionReason.NONE.value
                result = self._result(record, patreon_status="SKIPPED_NO_WORK", royal_road_status="SKIPPED_NO_WORK", social_status="SKIPPED_NO_WORK")
                record.result = result.to_dict()
                self.store.save(record)
                return result

            record.novel_id = selected.novel_id
            record.chapter_id = selected.chapter_id
            record.selection_reason = reason
            self.store.save(record)

            # Hermes prose only
            record.state = OrchState.GENERATING_PROSE.value
            self.store.save(record)
            draft = self.hermes.generate_prose(
                novel_id=selected.novel_id,
                chapter_id=selected.chapter_id,
                workflow_id=wf_id,
            )

            record.state = OrchState.VALIDATING.value
            self.store.save(record)
            validation = self.validator.validate(draft)
            if not validation.ok or validation.validation_status != "VALIDATED":
                return self._fail(record, validation.reason or "validation_failed")

            record.state = OrchState.STORING.value
            self.store.save(record)
            store_id = self.chapter_store.store_validated(draft, validation)
            record.store_id = store_id
            self.store.save(record)

            # Enqueue media — do NOT block publication on video completion
            record.state = OrchState.ENQUEUING_MEDIA.value
            self.store.save(record)
            media = self.chapter_media.enqueue_chapter_media(
                ValidatedChapterRef(
                    chapter_id=selected.chapter_id,
                    novel_id=selected.novel_id,
                    validation_status="VALIDATED",
                    workflow_id=wf_id,
                )
            )
            record.media_outcome = media.outcome
            record.media_asset_kind = media.asset_kind
            record.media_asset_sha256 = media.asset_sha256
            # AWAITING_APPROVAL / STATIC_FALLBACK / SOCIAL_READY are all non-blocking for publish
            record.publication_waited_for_video = False
            self.store.save(record)

            # Publish chapter text — independent of video readiness
            record.state = OrchState.PUBLISHING.value
            self.store.save(record)
            patreon_key = compute_publish_idempotency_key(
                channel="patreon", novel_id=selected.novel_id, chapter_id=selected.chapter_id
            )
            patreon = self.patreon_post.post_chapter(
                novel_id=selected.novel_id,
                chapter_id=selected.chapter_id,
                store_id=store_id,
                idempotency_key=patreon_key,
            )
            record.patreon_remote_id = patreon.remote_id
            if patreon.status == "FAILED":
                return self._fail(record, f"patreon:{patreon.failure_reason}")

            rr_key = compute_publish_idempotency_key(
                channel="royal_road", novel_id=selected.novel_id, chapter_id=selected.chapter_id
            )
            rr = self.royal_road_post.post_chapter(
                novel_id=selected.novel_id,
                chapter_id=selected.chapter_id,
                store_id=store_id,
                remote_fiction_id=self.royal_road_fiction_id_for(selected.novel_id),
                idempotency_key=rr_key,
            )
            record.royal_road_remote_id = rr.remote_id
            if rr.status == "FAILED":
                return self._fail(record, f"royal_road:{rr.failure_reason}")

            # Social may use static if video unavailable / under review
            record.state = OrchState.SOCIAL.value
            self.store.save(record)
            social_key = compute_publish_idempotency_key(
                channel="social", novel_id=selected.novel_id, chapter_id=selected.chapter_id
            )
            use_kind = media.asset_kind
            use_path = media.asset_path
            use_sha = media.asset_sha256
            if media.outcome in {
                ChapterMediaOutcome.AWAITING_APPROVAL.value,
                ChapterMediaOutcome.FAILED.value,
            }:
                # No media asset yet — social may skip or use nothing; port decides
                use_kind = None
                use_path = None
                use_sha = None
            social = self.social_post.post_social(
                novel_id=selected.novel_id,
                chapter_id=selected.chapter_id,
                asset_path=use_path,
                asset_sha256=use_sha,
                asset_kind=use_kind,
                idempotency_key=social_key,
            )
            record.social_status = social.status
            if social.status == "FAILED":
                return self._fail(record, f"social:{social.failure_reason}")

            record.state = OrchState.READY.value
            result = self._result(
                record,
                patreon_status=patreon.status,
                royal_road_status=rr.status,
                social_status=social.status,
            )
            record.result = result.to_dict()
            self.store.save(record)
            return result
        except Exception as exc:  # noqa: BLE001
            return self._fail(record, str(exc))

    def _result(
        self,
        record: OrchRecord,
        *,
        patreon_status: Optional[str],
        royal_road_status: Optional[str],
        social_status: Optional[str],
    ) -> OrchResult:
        return OrchResult(
            workflow_id=record.workflow_id,
            orch_job_id=record.orch_job_id,
            idempotency_key=record.idempotency_key,
            state=record.state,
            novel_id=record.novel_id,
            chapter_id=record.chapter_id,
            selection_reason=record.selection_reason,
            media_outcome=record.media_outcome,
            media_asset_kind=record.media_asset_kind,
            patreon_status=patreon_status,
            royal_road_status=royal_road_status,
            social_status=social_status or record.social_status,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            publication_waited_for_video=record.publication_waited_for_video,
            failure_reason=record.failure_reason,
        )

    def _fail(self, record: OrchRecord, reason: str) -> OrchResult:
        record.state = OrchState.FAILED.value
        record.failure_reason = reason
        result = self._result(record, patreon_status=None, royal_road_status=None, social_status=None)
        record.result = result.to_dict()
        self.store.save(record)
        return result
