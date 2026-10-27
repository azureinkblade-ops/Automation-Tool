"""CPU/mock tests for PRODUCTION_ORCHESTRATION_LIVE_WIRING (dry-run)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from tools.chapter_production_posting_orchestration import (
    VIDEO_CREATES_IDENTITY_CANON,
    BacklogItem,
    OrchState,
)
from tools.chapter_to_media_workflow import ChapterMediaOutcome
from tools.production_orchestration_live_wiring import (
    LIVE_PUBLISH_ENABLED_DEFAULT,
    SOCIAL_READY_CREATES_IDENTITY_CANON,
    DryRunHermes,
    IntentStore,
    LiveWiringConfig,
    TaskSchedulerEntrypoint,
    build_entrypoint,
)


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

    def enqueue_chapter_media(self, chapter, *, seed: int = 0):
        self.calls += 1
        return self.result


def _media_social():
    return FakeChapterMedia(
        FakeMediaResult(
            outcome=ChapterMediaOutcome.SOCIAL_READY.value,
            asset_path="/tmp/v.mp4",
            asset_sha256="vhash",
            asset_kind="presented_video",
        )
    )


def _media_static():
    return FakeChapterMedia(
        FakeMediaResult(
            outcome=ChapterMediaOutcome.STATIC_FALLBACK.value,
            asset_path="/tmp/s.png",
            asset_sha256="shash",
            asset_kind="static_still",
            state="READY_STATIC_FALLBACK",
        )
    )


def _media_awaiting():
    return FakeChapterMedia(FakeMediaResult(outcome=ChapterMediaOutcome.AWAITING_APPROVAL.value))


def test_defaults_refuse_live_publish_and_canon():
    assert LIVE_PUBLISH_ENABLED_DEFAULT is False
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert SOCIAL_READY_CREATES_IDENTITY_CANON is False


def test_entrypoint_dry_run_tick_happy_path(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-1", novel_id="n1", channel="patreon", priority=5)]
    ep = build_entrypoint(
        tmp_path,
        _media_social(),
        backlog_items=backlog,
        fiction_ids={"n1": "rr-100"},
    )
    r = ep.run_tick(tick_id="tick-1", workflow_id="wf-1")
    assert r.state == OrchState.READY.value
    assert r.patreon_status == "POSTED"
    assert r.royal_road_status == "POSTED"
    assert r.social_status == "POSTED"
    assert r.video_creates_identity_canon is False
    assert r.publication_waited_for_video is False
    # intents persisted
    intents = list((tmp_path / "intent_store").glob("*.json"))
    assert len(intents) >= 2


def test_live_publish_flag_refused_on_tick(tmp_path):
    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(root=tmp_path, live_publish_enabled=True, backlog_items=[]),
        chapter_media=_media_social(),
    )
    with pytest.raises(RuntimeError, match="LIVE_PUBLISH"):
        ep.run_tick(tick_id="t", workflow_id="w")


def test_canary_proves_restart_resume_idempotency(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-canary", novel_id="n1", channel="patreon", priority=1)]
    ep = build_entrypoint(tmp_path, _media_social(), backlog_items=backlog, fiction_ids={"n1": "rr-1"})
    report = ep.run_canary_dry_run(tick_id="canary-tick", workflow_id="canary-wf")
    assert report["first_state"] == OrchState.READY.value
    assert report["second_reused_existing"] is True
    assert report["same_idempotency_key"] is True
    assert report["hermes_calls"] == 1
    assert report["patreon_calls"] == 1
    assert report["royal_road_calls"] == 1
    assert report["live_publish_enabled"] is False
    assert report["video_creates_identity_canon"] is False


def test_static_fallback_social_dry_run(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-2", novel_id="n1", channel="patreon", priority=1)]
    ep = build_entrypoint(tmp_path, _media_static(), backlog_items=backlog)
    r = ep.run_tick(tick_id="t2", workflow_id="wf2")
    assert r.media_outcome == ChapterMediaOutcome.STATIC_FALLBACK.value
    assert r.patreon_status == "POSTED"
    assert r.social_status == "POSTED"


def test_awaiting_approval_still_publishes_dry_run(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-3", novel_id="n1", channel="patreon", priority=1)]
    ep = build_entrypoint(tmp_path, _media_awaiting(), backlog_items=backlog)
    r = ep.run_tick(tick_id="t3", workflow_id="wf3")
    assert r.media_outcome == ChapterMediaOutcome.AWAITING_APPROVAL.value
    assert r.publication_waited_for_video is False
    assert r.patreon_status == "POSTED"
    assert r.social_status == "SKIPPED_NO_ASSET"


def test_patreon_backlog_priority_over_inventory(tmp_path):
    backlog = [BacklogItem(chapter_id="backlog-ch", novel_id="n1", channel="patreon", priority=9)]
    inv = BacklogItem(chapter_id="inv-ch", novel_id="n1", channel="inventory")
    ep = build_entrypoint(
        tmp_path,
        _media_social(),
        backlog_items=backlog,
        next_inventory=lambda: inv,
    )
    r = ep.run_tick(tick_id="t4", workflow_id="wf4")
    assert r.chapter_id == "backlog-ch"


def test_rr_intent_stores_fiction_id(tmp_path):
    backlog = [BacklogItem(chapter_id="ch-rr", novel_id="novel-z", channel="patreon", priority=1)]
    ep = build_entrypoint(
        tmp_path,
        _media_social(),
        backlog_items=backlog,
        fiction_ids={"novel-z": "fiction-999"},
    )
    r = ep.run_tick(tick_id="t5", workflow_id="wf5")
    assert r.royal_road_status == "POSTED"
    # find rr intent
    store = IntentStore(tmp_path / "intent_store")
    # recompute key via orch helper
    from tools.chapter_production_posting_orchestration import compute_publish_idempotency_key

    key = compute_publish_idempotency_key(channel="royal_road", novel_id="novel-z", chapter_id="ch-rr")
    intent = store.get(key)
    assert intent is not None
    assert intent.payload.get("remote_fiction_id") == "fiction-999"
    assert intent.status == "POSTED_DRY_RUN"


def test_dry_run_hermes_does_not_need_live(tmp_path):
    h = DryRunHermes(allow_live_hermes=False)
    d = h.generate_prose(novel_id="n", chapter_id="c", workflow_id="w")
    assert d.prose_sha256
    assert d.body_path.startswith("dry-run://")


def test_adapter_raises_if_live_flag_set_on_port(tmp_path):
    from tools.production_orchestration_live_wiring import DryRunPatreonPost

    port = DryRunPatreonPost(IntentStore(tmp_path / "i"), live_publish_enabled=True)
    with pytest.raises(RuntimeError, match="not enabled"):
        port.post_chapter(novel_id="n", chapter_id="c", store_id="s", idempotency_key="k")
