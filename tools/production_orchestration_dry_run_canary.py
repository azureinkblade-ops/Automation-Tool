"""PRODUCTION_ORCHESTRATION_DRY_RUN_CANARY

Controlled production canary: one real chapter workflow with posting still dry-run.

Allowed / required:
- Task Scheduler-style invocation (tick entrypoint; no self-scheduling)
- Real Hermes prose call (injected live adapter; not the dry stub)
- Real chapter validation + durable storage
- Real media enqueue (injected ChapterToMediaWorkflow; image/video generation allowed)
- Patreon / Royal Road / social adapters remain DRY_RUN (no actual publication)
- Restart/resume mid-workflow; duplicate-publication count must remain 0
- READY_STATIC_FALLBACK accepted if video fails / review-blocks
- Still/video/social assets remain non-canon

Not in scope for this lane: enabling real Patreon/RR/social posting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.chapter_production_posting_orchestration import (
    VIDEO_CREATES_IDENTITY_CANON,
    BacklogItem,
    ChapterDraft,
    OrchResult,
    OrchState,
    ValidationResult,
)
from tools.chapter_to_media_workflow import ChapterMediaOutcome, ChapterToMediaWorkflow
from tools.production_orchestration_live_wiring import (
    LIVE_PUBLISH_ENABLED_DEFAULT,
    SOCIAL_READY_CREATES_IDENTITY_CANON,
    DryRunPatreonPost,
    DryRunRoyalRoadPost,
    DryRunSocialPost,
    DurableChapterStore,
    FileBacklog,
    IntentStore,
    LiveWiringConfig,
    SimpleValidator,
    TaskSchedulerEntrypoint,
)


CANARY_VERSION = "production_orch_dry_run_canary_v1"


class LiveHermesRequired(RuntimeError):
    pass


@dataclass
class LiveHermesAdapter:
    """Adapter that MUST call real Hermes (or an injected live callable). Dry stub forbidden."""

    live_generate: Callable[..., ChapterDraft]
    calls: int = 0

    def generate_prose(self, *, novel_id: str, chapter_id: str, workflow_id: str) -> ChapterDraft:
        self.calls += 1
        draft = self.live_generate(novel_id=novel_id, chapter_id=chapter_id, workflow_id=workflow_id)
        if not isinstance(draft, ChapterDraft):
            raise LiveHermesRequired("live Hermes must return ChapterDraft")
        if not draft.prose_sha256 or draft.body_path.startswith("dry-run://"):
            raise LiveHermesRequired("refusing dry-run Hermes stub in canary lane")
        return draft


@dataclass
class CanaryGates:
    live_publish_enabled: bool
    video_creates_identity_canon: bool
    social_ready_creates_identity_canon: bool
    duplicate_publication_count: int
    publication_waited_for_video: bool
    restart_resumed: bool
    hermes_live_calls: int
    media_enqueues: int
    patreon_intent_count: int
    royal_road_intent_count: int
    social_intent_count: int
    media_outcome: Optional[str]
    static_fallback_accepted: bool
    state: str
    ok: bool
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CanaryReport:
    canary_id: str
    tick_id: str
    workflow_id: str
    novel_id: str
    chapter_id: str
    first: Dict[str, Any]
    resumed: Dict[str, Any]
    gates: CanaryGates
    version: str = CANARY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["gates"] = self.gates.to_dict()
        return d


@dataclass
class DryRunCanaryRunner:
    """Composition root for one controlled dry-run canary chapter."""

    root: Path
    chapter_media: ChapterToMediaWorkflow
    live_hermes: LiveHermesAdapter
    novel_id: str
    chapter_id: str
    fiction_id: str
    media_call_counter: Optional[Any] = None  # object with .calls if provided

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        if LIVE_PUBLISH_ENABLED_DEFAULT:
            raise RuntimeError("LIVE_PUBLISH_ENABLED_DEFAULT must be False for canary")
        self.entrypoint = TaskSchedulerEntrypoint(
            config=LiveWiringConfig(
                root=self.root,
                live_publish_enabled=False,
                allow_live_hermes=True,
                fiction_ids={self.novel_id: self.fiction_id},
                backlog_items=[
                    BacklogItem(
                        chapter_id=self.chapter_id,
                        novel_id=self.novel_id,
                        channel="patreon",
                        priority=100,
                    )
                ],
            ),
            chapter_media=self.chapter_media,
        )
        # Replace dry Hermes with live adapter (canary requirement)
        self.entrypoint.hermes = self.live_hermes
        self.entrypoint.orchestrator.hermes = self.live_hermes

    def _count_intents(self, channel: str) -> int:
        store = self.entrypoint.intent_store
        assert store is not None
        n = 0
        for path in (self.root / "intent_store").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("channel") == channel and data.get("status") == "POSTED_DRY_RUN":
                n += 1
        return n

    def _duplicate_publication_count(self) -> int:
        """Count extra POSTED_DRY_RUN intents sharing the same idempotency key (must be 0)."""
        by_key: Dict[str, int] = {}
        for path in (self.root / "intent_store").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") != "POSTED_DRY_RUN":
                continue
            key = data.get("idempotency_key") or path.stem
            by_key[key] = by_key.get(key, 0) + 1
        return sum(max(0, c - 1) for c in by_key.values())

    def run(
        self,
        *,
        tick_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        inject_mid_workflow_restart: bool = True,
    ) -> CanaryReport:
        tick = tick_id or f"canary-tick-{uuid.uuid4().hex[:10]}"
        wf = workflow_id or f"canary-wf-{uuid.uuid4().hex[:10]}"
        canary_id = f"canary-{uuid.uuid4().hex[:12]}"

        first = self.entrypoint.run_tick(tick_id=tick, workflow_id=wf)

        resumed: OrchResult
        restart_resumed = False
        if inject_mid_workflow_restart:
            # 1) Exact tick replay → orch READY reuse (no new work).
            exact = self.entrypoint.run_tick(tick_id=tick, workflow_id=wf)
            # 2) Fresh tick same chapter → publish intents must SKIPPED_IDEMPOTENT;
            #    durable intent store keeps duplicate_publication_count at 0.
            mid = self.entrypoint.run_tick(tick_id=tick + "-mid-restart", workflow_id=wf + "-mid-restart")
            restart_resumed = bool(exact.reused_existing) and mid.state in {
                OrchState.READY.value,
                OrchState.FAILED.value,
            }
            resumed = exact if exact.reused_existing else mid
        else:
            resumed = self.entrypoint.run_tick(tick_id=tick, workflow_id=wf)

        media_calls = 0
        if self.media_call_counter is not None and hasattr(self.media_call_counter, "calls"):
            media_calls = int(self.media_call_counter.calls)
        elif hasattr(self.chapter_media, "calls"):
            media_calls = int(getattr(self.chapter_media, "calls"))

        dup = self._duplicate_publication_count()
        media_outcome = first.media_outcome
        static_ok = media_outcome in {
            ChapterMediaOutcome.STATIC_FALLBACK.value,
            ChapterMediaOutcome.SOCIAL_READY.value,
            ChapterMediaOutcome.AWAITING_APPROVAL.value,
            None,
        }
        # static fallback is accepted for publication success
        if media_outcome == ChapterMediaOutcome.STATIC_FALLBACK.value:
            static_accepted = first.state == OrchState.READY.value and first.patreon_status == "POSTED"
        else:
            static_accepted = media_outcome != ChapterMediaOutcome.STATIC_FALLBACK.value

        ok = (
            first.state == OrchState.READY.value
            and dup == 0
            and self.live_hermes.calls >= 1
            and first.video_creates_identity_canon is False
            and first.publication_waited_for_video is False
            and LIVE_PUBLISH_ENABLED_DEFAULT is False
            and SOCIAL_READY_CREATES_IDENTITY_CANON is False
            and VIDEO_CREATES_IDENTITY_CANON is False
        )
        reason = None
        if not ok:
            reason = (
                f"state={first.state} dup={dup} hermes={self.live_hermes.calls} "
                f"canon={first.video_creates_identity_canon}"
            )

        gates = CanaryGates(
            live_publish_enabled=False,
            video_creates_identity_canon=VIDEO_CREATES_IDENTITY_CANON,
            social_ready_creates_identity_canon=SOCIAL_READY_CREATES_IDENTITY_CANON,
            duplicate_publication_count=dup,
            publication_waited_for_video=bool(first.publication_waited_for_video),
            restart_resumed=restart_resumed,
            hermes_live_calls=self.live_hermes.calls,
            media_enqueues=media_calls,
            patreon_intent_count=self._count_intents("patreon"),
            royal_road_intent_count=self._count_intents("royal_road"),
            social_intent_count=self._count_intents("social"),
            media_outcome=media_outcome,
            static_fallback_accepted=static_accepted if media_outcome == ChapterMediaOutcome.STATIC_FALLBACK.value else (
                True if media_outcome != ChapterMediaOutcome.FAILED.value else False
            ),
            state=first.state,
            ok=ok,
            failure_reason=reason,
        )

        report = CanaryReport(
            canary_id=canary_id,
            tick_id=tick,
            workflow_id=wf,
            novel_id=self.novel_id,
            chapter_id=self.chapter_id,
            first=first.to_dict(),
            resumed=resumed.to_dict(),
            gates=gates,
        )
        out = self.root / "canary_report.json"
        out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return report


def write_live_prose_file(root: Path, *, novel_id: str, chapter_id: str, workflow_id: str, body: str) -> ChapterDraft:
    """Helper for a live Hermes callable that persists real prose to disk (non dry-run://)."""
    import hashlib

    prose_dir = Path(root) / "hermes_prose"
    prose_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    path = prose_dir / f"{novel_id}_{chapter_id}_{digest[:12]}.md"
    path.write_text(body, encoding="utf-8")
    return ChapterDraft(
        chapter_id=chapter_id,
        novel_id=novel_id,
        prose_sha256=digest,
        body_path=str(path.resolve()),
    )
