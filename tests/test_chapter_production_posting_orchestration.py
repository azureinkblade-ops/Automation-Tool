"""CPU/mock tests for CHAPTER_PRODUCTION_AND_POSTING_ORCHESTRATION."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytest

from tools.chapter_production_posting_orchestration import (
    VIDEO_CREATES_IDENTITY_CANON,
    BacklogItem,
    ChapterDraft,
    ChapterProductionPostingOrchestrator,
    OrchState,
    OrchStore,
    PublishResult,
    SelectionReason,
    SocialPostResult,
    ValidationResult,
    compute_publish_idempotency_key,
)
from tools.chapter_to_media_workflow import ChapterMediaOutcome


@dataclass
class FakeMediaResult:
    outcome: str
    asset_path: Optional[str] = None
    asset_sha256: Optional[str] = None
    asset_kind: Optional[str] = None
    state: str = "READY"


class FakeChapterMedia:
    def __init__(self, result: FakeMediaResult):
        self.result = result
        self.calls = 0
        self.last_chapter = None

    def enqueue_chapter_media(self, chapter, *, seed: int = 0):
        self.calls += 1
        self.last_chapter = chapter
        return self.result


class FakeHermes:
    def __init__(self):
        self.calls = 0

    def generate_prose(self, *, novel_id: str, chapter_id: str, workflow_id: str) -> ChapterDraft:
        self.calls += 1
        return ChapterDraft(
            chapter_id=chapter_id,
            novel_id=novel_id,
            prose_sha256="prose" + chapter_id,
            body_path=f"/tmp/{chapter_id}.md",
        )


class FakeValidator:
    def __init__(self, ok: bool = True, reason: Optional[str] = None):
        self.ok = ok
        self.reason = reason
        self.calls = 0

    def validate(self, draft: ChapterDraft) -> ValidationResult:
        self.calls += 1
        if self.ok:
            return ValidationResult(ok=True, validation_status="VALIDATED")
        return ValidationResult(ok=False, validation_status="REJECTED", reason=self.reason or "bad")


class FakeChapterStore:
    def __init__(self):
        self.calls = 0

    def store_validated(self, draft: ChapterDraft, validation: ValidationResult) -> str:
        self.calls += 1
        return f"store-{draft.chapter_id}"


class FakeBacklog:
    def __init__(self, items: List[BacklogItem]):
        self.items = items

    def list_backlog(self) -> List[BacklogItem]:
        return list(self.items)


class FakePatreonPost:
    def __init__(self):
        self.calls = 0
        self.keys: List[str] = []
        self._seen = set()

    def post_chapter(self, *, novel_id: str, chapter_id: str, store_id: str, idempotency_key: str) -> PublishResult:
        self.calls += 1
        self.keys.append(idempotency_key)
        if idempotency_key in self._seen:
            return PublishResult(channel="patreon", remote_id="pat-1", idempotency_key=idempotency_key, status="SKIPPED_IDEMPOTENT")
        self._seen.add(idempotency_key)
        return PublishResult(channel="patreon", remote_id="pat-1", idempotency_key=idempotency_key, status="POSTED")


class FakeRoyalRoadPost:
    def __init__(self):
        self.calls = 0
        self.keys: List[str] = []
        self.fiction_ids: List[str] = []
        self._seen = set()

    def post_chapter(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        store_id: str,
        remote_fiction_id: str,
        idempotency_key: str,
    ) -> PublishResult:
        self.calls += 1
        self.keys.append(idempotency_key)
        self.fiction_ids.append(remote_fiction_id)
        if idempotency_key in self._seen:
            return PublishResult(channel="royal_road", remote_id="rr-1", idempotency_key=idempotency_key, status="SKIPPED_IDEMPOTENT")
        self._seen.add(idempotency_key)
        return PublishResult(
            channel="royal_road",
            remote_id=f"rr-{remote_fiction_id}-{chapter_id}",
            idempotency_key=idempotency_key,
            status="POSTED",
        )


class FakeSocialPost:
    def __init__(self):
        self.calls = 0
        self.last_kind: Optional[str] = None
        self.last_sha: Optional[str] = None

    def post_social(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        asset_path: Optional[str],
        asset_sha256: Optional[str],
        asset_kind: Optional[str],
        idempotency_key: str,
    ) -> SocialPostResult:
        self.calls += 1
        self.last_kind = asset_kind
        self.last_sha = asset_sha256
        if asset_kind is None and asset_path is None:
            return SocialPostResult(status="SKIPPED_NO_ASSET")
        return SocialPostResult(status="POSTED", asset_kind=asset_kind, asset_sha256=asset_sha256)


def _build(
    tmp_path,
    *,
    backlog=None,
    inventory=None,
    media=None,
    validator=None,
):
    hermes = FakeHermes()
    patreon = FakePatreonPost()
    rr = FakeRoyalRoadPost()
    social = FakeSocialPost()
    media_wf = FakeChapterMedia(
        media
        or FakeMediaResult(
            outcome=ChapterMediaOutcome.SOCIAL_READY.value,
            asset_path="/tmp/vid.mp4",
            asset_sha256="vidhash",
            asset_kind="presented_video",
        )
    )
    inv = inventory  # None or BacklogItem

    orch = ChapterProductionPostingOrchestrator(
        store=OrchStore(tmp_path / "orch"),
        hermes=hermes,
        validator=validator or FakeValidator(),
        chapter_store=FakeChapterStore(),
        patreon_backlog=FakeBacklog(backlog or []),
        patreon_post=patreon,
        royal_road_post=rr,
        social_post=social,
        chapter_media=media_wf,
        royal_road_fiction_id_for=lambda novel_id: f"fiction-{novel_id}",
        next_inventory_chapter=lambda: inv,
    )
    return orch, hermes, patreon, rr, social, media_wf


def test_video_creates_identity_canon_is_false():
    assert VIDEO_CREATES_IDENTITY_CANON is False


def test_empty_tick_no_work(tmp_path):
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path)
    r = orch.run_tick(tick_id="t1", workflow_id="wf1")
    assert r.state == OrchState.READY.value
    assert r.selection_reason == SelectionReason.NONE.value
    assert hermes.calls == 0
    assert patreon.calls == 0
    assert media_wf.calls == 0


def test_patreon_backlog_beats_inventory(tmp_path):
    backlog = [
        BacklogItem(chapter_id="ch-backlog", novel_id="novel-a", channel="patreon", priority=10),
    ]
    inv = BacklogItem(chapter_id="ch-inv", novel_id="novel-a", channel="inventory", priority=0)
    orch, hermes, *_ = _build(tmp_path, backlog=backlog, inventory=inv)
    r = orch.run_tick(tick_id="t2", workflow_id="wf2")
    assert r.state == OrchState.READY.value
    assert r.selection_reason == SelectionReason.PATREON_BACKLOG.value
    assert r.chapter_id == "ch-backlog"
    assert hermes.calls == 1


def test_inventory_when_no_patreon_backlog(tmp_path):
    inv = BacklogItem(chapter_id="ch-inv", novel_id="novel-b", channel="inventory")
    orch, hermes, *_ = _build(tmp_path, backlog=[], inventory=inv)
    r = orch.run_tick(tick_id="t3", workflow_id="wf3")
    assert r.selection_reason == SelectionReason.NEXT_INVENTORY.value
    assert r.chapter_id == "ch-inv"
    assert hermes.calls == 1


def test_publication_does_not_wait_for_video_awaiting_approval(tmp_path):
    media = FakeMediaResult(outcome=ChapterMediaOutcome.AWAITING_APPROVAL.value)
    backlog = [BacklogItem(chapter_id="ch-1", novel_id="n1", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path, backlog=backlog, media=media)
    r = orch.run_tick(tick_id="t4", workflow_id="wf4")
    assert r.state == OrchState.READY.value
    assert r.media_outcome == ChapterMediaOutcome.AWAITING_APPROVAL.value
    assert r.publication_waited_for_video is False
    assert r.patreon_status == "POSTED"
    assert r.royal_road_status == "POSTED"
    assert r.social_status == "SKIPPED_NO_ASSET"
    assert social.last_kind is None
    assert patreon.calls == 1
    assert rr.calls == 1


def test_static_fallback_is_success_for_publication_and_social(tmp_path):
    media = FakeMediaResult(
        outcome=ChapterMediaOutcome.STATIC_FALLBACK.value,
        asset_path="/tmp/still.png",
        asset_sha256="stillhash",
        asset_kind="static_still",
        state="READY_STATIC_FALLBACK",
    )
    backlog = [BacklogItem(chapter_id="ch-2", novel_id="n1", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path, backlog=backlog, media=media)
    r = orch.run_tick(tick_id="t5", workflow_id="wf5")
    assert r.state == OrchState.READY.value
    assert r.media_outcome == ChapterMediaOutcome.STATIC_FALLBACK.value
    assert r.publication_waited_for_video is False
    assert r.patreon_status == "POSTED"
    assert r.social_status == "POSTED"
    assert social.last_kind == "static_still"
    assert social.last_sha == "stillhash"
    assert r.video_creates_identity_canon is False


def test_royal_road_uses_stored_fiction_id_and_idempotency_key(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-3", novel_id="novel-x", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path, backlog=backlog)
    r = orch.run_tick(tick_id="t6", workflow_id="wf6")
    assert rr.fiction_ids == ["fiction-novel-x"]
    expected = compute_publish_idempotency_key(channel="royal_road", novel_id="novel-x", chapter_id="ch-3")
    assert rr.keys == [expected]
    assert r.royal_road_status == "POSTED"


def test_tick_idempotent_reuse(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-4", novel_id="n1", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path, backlog=backlog)
    r1 = orch.run_tick(tick_id="t7", workflow_id="wf7")
    r2 = orch.run_tick(tick_id="t7", workflow_id="wf7")
    assert r1.state == OrchState.READY.value
    assert r2.reused_existing is True
    assert hermes.calls == 1
    assert patreon.calls == 1
    assert media_wf.calls == 1


def test_validation_failure_blocks_publish(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-5", novel_id="n1", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(
        tmp_path, backlog=backlog, validator=FakeValidator(ok=False, reason="bad_prose")
    )
    r = orch.run_tick(tick_id="t8", workflow_id="wf8")
    assert r.state == OrchState.FAILED.value
    assert r.failure_reason == "bad_prose"
    assert patreon.calls == 0
    assert media_wf.calls == 0
    assert hermes.calls == 1


def test_higher_priority_patreon_selected(tmp_path):
    backlog = [
        BacklogItem(chapter_id="low", novel_id="n1", channel="patreon", priority=1),
        BacklogItem(chapter_id="high", novel_id="n1", channel="patreon", priority=99),
    ]
    orch, *_ = _build(tmp_path, backlog=backlog)
    r = orch.run_tick(tick_id="t9", workflow_id="wf9")
    assert r.chapter_id == "high"


def test_happy_path_social_ready_video(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-10", novel_id="n1", channel="patreon", priority=1)]
    orch, hermes, patreon, rr, social, media_wf = _build(tmp_path, backlog=backlog)
    r = orch.run_tick(tick_id="t10", workflow_id="wf10")
    assert r.state == OrchState.READY.value
    assert r.media_outcome == ChapterMediaOutcome.SOCIAL_READY.value
    assert social.last_kind == "presented_video"
    assert r.video_creates_identity_canon is False
    assert r.publication_waited_for_video is False
