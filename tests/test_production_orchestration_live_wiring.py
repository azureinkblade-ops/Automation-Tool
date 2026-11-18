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
    PublishResult,
    SocialPostResult,
)
from tools.chapter_to_media_workflow import ChapterMediaOutcome
from tools.production_orchestration_live_wiring import (
    LIVE_PUBLISH_APPROVE_SHA_ENV,
    LIVE_PUBLISH_ENABLED_DEFAULT,
    SOCIAL_READY_CREATES_IDENTITY_CANON,
    DryRunHermes,
    IntentStore,
    LivePatreonPost,
    LiveRoyalRoadPost,
    LiveSocialPost,
    LiveWiringConfig,
    TaskSchedulerEntrypoint,
    assert_live_publish_approved,
    build_entrypoint,
    ha113_publish_asset_metadata,
    is_ha113_chapter,
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


def test_live_publish_flag_refused_on_tick(tmp_path, monkeypatch):
    """(b) live=True without approve token fails closed."""
    monkeypatch.delenv(LIVE_PUBLISH_APPROVE_SHA_ENV, raising=False)
    monkeypatch.delenv("LIVE_PUBLISH_APPROVE_FILE", raising=False)
    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=tmp_path,
            live_publish_enabled=True,
            backlog_items=[],
            code_sha="abc123deadbeef",
            live_publish_approve_file=tmp_path / "missing_oneshot.txt",
            live_publish_evidence_dir=tmp_path / "evidence",
        ),
        chapter_media=_media_social(),
    )
    with pytest.raises(RuntimeError, match="LIVE_PUBLISH refused"):
        ep.run_tick(tick_id="t", workflow_id="w")
    assert isinstance(ep.patreon, LivePatreonPost)


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


def test_live_publish_mismatch_token_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(LIVE_PUBLISH_APPROVE_SHA_ENV, "wrong-token")
    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=tmp_path,
            live_publish_enabled=True,
            backlog_items=[],
            code_sha="expected-sha-001",
        ),
        chapter_media=_media_social(),
    )
    with pytest.raises(RuntimeError, match="mismatch"):
        ep.run_tick(tick_id="t", workflow_id="w")


def test_live_publish_with_matching_env_token_reaches_live_fakes(tmp_path, monkeypatch):
    """(c) live=True + matching token reaches Live* call sites; publishers are fakes (no network)."""
    code_sha = "approve-sha-for-test-001"
    monkeypatch.setenv(LIVE_PUBLISH_APPROVE_SHA_ENV, code_sha)

    patreon_calls = []
    rr_calls = []
    social_calls = []

    def fake_patreon(**kwargs):
        patreon_calls.append(kwargs)
        return PublishResult(
            channel="patreon",
            remote_id="fake-live-patreon",
            idempotency_key=kwargs["idempotency_key"],
            status="POSTED",
        )

    def fake_rr(**kwargs):
        rr_calls.append(kwargs)
        return PublishResult(
            channel="royal_road",
            remote_id="fake-live-rr",
            idempotency_key=kwargs["idempotency_key"],
            status="POSTED",
        )

    def fake_social(**kwargs):
        social_calls.append(kwargs)
        return SocialPostResult(
            status="POSTED",
            asset_kind=kwargs.get("asset_kind"),
            asset_sha256=kwargs.get("asset_sha256"),
        )

    backlog = [BacklogItem(chapter_id="HA-113", novel_id="HA", channel="patreon", priority=1)]
    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=tmp_path,
            live_publish_enabled=True,
            backlog_items=backlog,
            fiction_ids={"HA": "fiction-ha"},
            code_sha=code_sha,
            live_patreon_publisher=fake_patreon,
            live_royal_road_publisher=fake_rr,
            live_social_publisher=fake_social,
            worktree_root=tmp_path,
        ),
        chapter_media=_media_social(),
    )
    assert isinstance(ep.patreon, LivePatreonPost)
    assert isinstance(ep.royal_road, LiveRoyalRoadPost)
    assert isinstance(ep.social, LiveSocialPost)

    r = ep.run_tick(tick_id="live-tick", workflow_id="live-wf")
    assert ep.live_publish_approval_mode == "env"
    assert r.state == OrchState.READY.value
    assert r.patreon_status == "POSTED"
    assert r.royal_road_status == "POSTED"
    assert r.social_status == "POSTED"
    assert r.video_creates_identity_canon is False
    assert len(patreon_calls) == 1
    assert len(rr_calls) == 1
    assert len(social_calls) == 1
    # HA-113 SOCIAL_READY + STILL_OK wired into publish intent payload
    assert patreon_calls[0]["payload"].get("still_ok") is True
    assert patreon_calls[0]["payload"].get("ha113", {}).get("presented_sha256")
    assert patreon_calls[0]["payload"].get("identity_canon") is False


def test_live_publish_oneshot_file_token(tmp_path, monkeypatch):
    monkeypatch.delenv(LIVE_PUBLISH_APPROVE_SHA_ENV, raising=False)
    code_sha = "oneshot-sha-xyz"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    oneshot = evidence / "LIVE_PUBLISH_APPROVE_ONESHOT.txt"
    oneshot.write_text(code_sha + "\n", encoding="utf-8")

    backlog = [BacklogItem(chapter_id="ch-live", novel_id="n1", channel="patreon", priority=1)]
    fake_calls = []

    def fake_patreon(**kwargs):
        fake_calls.append("patreon")
        return PublishResult(
            channel="patreon",
            remote_id="p1",
            idempotency_key=kwargs["idempotency_key"],
            status="POSTED",
        )

    def fake_rr(**kwargs):
        fake_calls.append("rr")
        return PublishResult(
            channel="royal_road",
            remote_id="r1",
            idempotency_key=kwargs["idempotency_key"],
            status="POSTED",
        )

    def fake_social(**kwargs):
        fake_calls.append("social")
        return SocialPostResult(status="POSTED", asset_kind="presented_video", asset_sha256="v")

    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=tmp_path,
            live_publish_enabled=True,
            backlog_items=backlog,
            fiction_ids={"n1": "rr-1"},
            code_sha=code_sha,
            live_publish_approve_file=oneshot,
            consume_live_publish_oneshot=True,
            live_patreon_publisher=fake_patreon,
            live_royal_road_publisher=fake_rr,
            live_social_publisher=fake_social,
        ),
        chapter_media=_media_social(),
    )
    r = ep.run_tick(tick_id="t-oneshot", workflow_id="wf-oneshot")
    assert ep.live_publish_approval_mode == "file"
    assert r.state == OrchState.READY.value
    assert not oneshot.exists()
    assert oneshot.with_suffix(oneshot.suffix + ".consumed").exists()
    assert fake_calls == ["patreon", "rr", "social"]


def test_identity_canon_flags_stay_false_under_live_gate(tmp_path, monkeypatch):
    """(d) identity-canon flags stay False even when live gate passes."""
    code_sha = "canon-check-sha"
    monkeypatch.setenv(LIVE_PUBLISH_APPROVE_SHA_ENV, code_sha)
    backlog = [BacklogItem(chapter_id="HA-113", novel_id="HA", channel="patreon", priority=1)]
    ep = TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=tmp_path,
            live_publish_enabled=True,
            backlog_items=backlog,
            code_sha=code_sha,
            live_patreon_publisher=lambda **k: PublishResult(
                channel="patreon", remote_id="x", idempotency_key=k["idempotency_key"], status="POSTED"
            ),
            live_royal_road_publisher=lambda **k: PublishResult(
                channel="royal_road", remote_id="y", idempotency_key=k["idempotency_key"], status="POSTED"
            ),
            live_social_publisher=lambda **k: SocialPostResult(
                status="POSTED", asset_kind=k.get("asset_kind"), asset_sha256=k.get("asset_sha256")
            ),
        ),
        chapter_media=_media_social(),
    )
    r = ep.run_tick(tick_id="t-canon", workflow_id="wf-canon")
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert SOCIAL_READY_CREATES_IDENTITY_CANON is False
    assert LIVE_PUBLISH_ENABLED_DEFAULT is False
    assert r.video_creates_identity_canon is False
    meta = ha113_publish_asset_metadata(worktree_root=tmp_path)
    assert meta["identity_canon"] is False
    assert meta["social_ready_creates_identity_canon"] is False
    assert meta["still_ok"] is True
    assert is_ha113_chapter("HA-113", novel_id="HA")


def test_assert_live_publish_approved_helper_env(monkeypatch):
    monkeypatch.setenv(LIVE_PUBLISH_APPROVE_SHA_ENV, "tok")
    assert assert_live_publish_approved(code_sha="tok") == "env"
    with pytest.raises(RuntimeError, match="mismatch"):
        assert_live_publish_approved(code_sha="other")
