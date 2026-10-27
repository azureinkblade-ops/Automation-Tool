"""PRODUCTION_ORCHESTRATION_LIVE_WIRING

Connect CHAPTER_PRODUCTION_AND_POSTING_ORCHESTRATION to real execution surfaces
in dry-run / no-publish mode first.

Surfaces:
- Windows Task Scheduler entrypoint (tick-driven; this module does not sleep)
- Durable OrchStore controller
- Hermes prose generation (dry-run local writer; live Hermes behind flag OFF)
- Chapter validation + durable chapter store
- Media enqueue (injected ChapterToMediaWorkflow)
- Patreon / Royal Road / social adapters in dry-run (intent-only, no network)

Default: LIVE_PUBLISH_ENABLED=False. Real publication requires an explicit
future enablement after a controlled canary proving restart/resume + idempotency.
No still/video/social asset becomes identity canon automatically.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.chapter_production_posting_orchestration import (
    VIDEO_CREATES_IDENTITY_CANON,
    BacklogItem,
    ChapterDraft,
    ChapterProductionPostingOrchestrator,
    OrchResult,
    OrchStore,
    PublishResult,
    SocialPostResult,
    ValidationResult,
    compute_publish_idempotency_key,
)
from tools.chapter_to_media_workflow import ChapterToMediaWorkflow


WIRING_VERSION = "production_orch_live_wiring_v1"
LIVE_PUBLISH_ENABLED_DEFAULT = False
SOCIAL_READY_CREATES_IDENTITY_CANON = False


@dataclass
class DryRunIntent:
    channel: str
    novel_id: str
    chapter_id: str
    idempotency_key: str
    status: str
    remote_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class IntentStore:
    """Durable dry-run publish / social intent log (restart-safe)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[DryRunIntent]:
        path = self._path(key)
        if not path.exists():
            return None
        return DryRunIntent(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, intent: DryRunIntent) -> None:
        path = self._path(intent.idempotency_key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(asdict(intent), indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)


class DryRunHermes:
    """Local prose writer for dry-run. Does not call live Hermes unless enabled."""

    def __init__(self, *, allow_live_hermes: bool = False, live_hermes: Optional[Callable[..., ChapterDraft]] = None) -> None:
        self.allow_live_hermes = allow_live_hermes
        self.live_hermes = live_hermes
        self.calls = 0

    def generate_prose(self, *, novel_id: str, chapter_id: str, workflow_id: str) -> ChapterDraft:
        self.calls += 1
        if self.allow_live_hermes and self.live_hermes is not None:
            return self.live_hermes(novel_id=novel_id, chapter_id=chapter_id, workflow_id=workflow_id)
        body = f"# {chapter_id}\n\nDry-run prose for {novel_id}/{chapter_id} wf={workflow_id}\n"
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return ChapterDraft(
            chapter_id=chapter_id,
            novel_id=novel_id,
            prose_sha256=digest,
            body_path=f"dry-run://{novel_id}/{chapter_id}/{digest[:12]}",
        )


class SimpleValidator:
    def validate(self, draft: ChapterDraft) -> ValidationResult:
        if not draft.prose_sha256 or not draft.chapter_id:
            return ValidationResult(ok=False, validation_status="REJECTED", reason="empty_draft")
        return ValidationResult(ok=True, validation_status="VALIDATED")


class DurableChapterStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def store_validated(self, draft: ChapterDraft, validation: ValidationResult) -> str:
        store_id = f"chstore-{draft.novel_id}-{draft.chapter_id}-{draft.prose_sha256[:12]}"
        path = self.root / f"{store_id}.json"
        path.write_text(
            json.dumps(
                {
                    "store_id": store_id,
                    "chapter_id": draft.chapter_id,
                    "novel_id": draft.novel_id,
                    "prose_sha256": draft.prose_sha256,
                    "body_path": draft.body_path,
                    "validation_status": validation.validation_status,
                    "wiring_version": WIRING_VERSION,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return store_id


class FileBacklog:
    def __init__(self, items: Optional[List[BacklogItem]] = None, path: Optional[Path] = None) -> None:
        self.items = list(items or [])
        self.path = Path(path) if path else None

    def list_backlog(self) -> List[BacklogItem]:
        if self.path and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [BacklogItem(**row) for row in raw]
        return list(self.items)


class DryRunPatreonPost:
    def __init__(self, intents: IntentStore, *, live_publish_enabled: bool = False) -> None:
        self.intents = intents
        self.live_publish_enabled = live_publish_enabled
        self.calls = 0

    def post_chapter(self, *, novel_id: str, chapter_id: str, store_id: str, idempotency_key: str) -> PublishResult:
        self.calls += 1
        if self.live_publish_enabled:
            raise RuntimeError("live Patreon publish not enabled in this lane")
        existing = self.intents.get(idempotency_key)
        if existing:
            return PublishResult(
                channel="patreon",
                remote_id=existing.remote_id,
                idempotency_key=idempotency_key,
                status="SKIPPED_IDEMPOTENT",
            )
        remote_id = f"dry-patreon-{chapter_id}"
        self.intents.save(
            DryRunIntent(
                channel="patreon",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=remote_id,
                payload={"store_id": store_id},
            )
        )
        return PublishResult(
            channel="patreon",
            remote_id=remote_id,
            idempotency_key=idempotency_key,
            status="POSTED",
        )


class DryRunRoyalRoadPost:
    def __init__(self, intents: IntentStore, *, live_publish_enabled: bool = False) -> None:
        self.intents = intents
        self.live_publish_enabled = live_publish_enabled
        self.calls = 0

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
        if self.live_publish_enabled:
            raise RuntimeError("live Royal Road publish not enabled in this lane")
        existing = self.intents.get(idempotency_key)
        if existing:
            return PublishResult(
                channel="royal_road",
                remote_id=existing.remote_id,
                idempotency_key=idempotency_key,
                status="SKIPPED_IDEMPOTENT",
            )
        remote_id = f"dry-rr-{remote_fiction_id}-{chapter_id}"
        self.intents.save(
            DryRunIntent(
                channel="royal_road",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=remote_id,
                payload={"store_id": store_id, "remote_fiction_id": remote_fiction_id},
            )
        )
        return PublishResult(
            channel="royal_road",
            remote_id=remote_id,
            idempotency_key=idempotency_key,
            status="POSTED",
        )


class DryRunSocialPost:
    def __init__(self, intents: IntentStore, *, live_publish_enabled: bool = False) -> None:
        self.intents = intents
        self.live_publish_enabled = live_publish_enabled
        self.calls = 0

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
        if self.live_publish_enabled:
            raise RuntimeError("live social publish not enabled in this lane")
        existing = self.intents.get(idempotency_key)
        if existing:
            return SocialPostResult(
                status="SKIPPED_IDEMPOTENT",
                asset_kind=existing.payload.get("asset_kind"),
                asset_sha256=existing.payload.get("asset_sha256"),
            )
        if asset_kind is None and asset_path is None:
            return SocialPostResult(status="SKIPPED_NO_ASSET")
        self.intents.save(
            DryRunIntent(
                channel="social",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=f"dry-social-{chapter_id}",
                payload={
                    "asset_path": asset_path,
                    "asset_sha256": asset_sha256,
                    "asset_kind": asset_kind,
                    "identity_canon": False,
                },
            )
        )
        return SocialPostResult(status="POSTED", asset_kind=asset_kind, asset_sha256=asset_sha256)


@dataclass
class LiveWiringConfig:
    root: Path
    live_publish_enabled: bool = LIVE_PUBLISH_ENABLED_DEFAULT
    allow_live_hermes: bool = False
    fiction_ids: Optional[Dict[str, str]] = None
    backlog_items: Optional[List[BacklogItem]] = None
    backlog_path: Optional[Path] = None
    next_inventory: Optional[Callable[[], Optional[BacklogItem]]] = None


@dataclass
class TaskSchedulerEntrypoint:
    """Windows Task Scheduler owns the clock; this is the tick handler only."""

    config: LiveWiringConfig
    chapter_media: ChapterToMediaWorkflow
    orch_store: Optional[OrchStore] = None
    intent_store: Optional[IntentStore] = None

    def __post_init__(self) -> None:
        root = Path(self.config.root)
        self.orch_store = self.orch_store or OrchStore(root / "orch_store")
        self.intent_store = self.intent_store or IntentStore(root / "intent_store")
        self.chapter_store = DurableChapterStore(root / "chapter_store")
        self.hermes = DryRunHermes(allow_live_hermes=self.config.allow_live_hermes)
        self.validator = SimpleValidator()
        self.backlog = FileBacklog(self.config.backlog_items, self.config.backlog_path)
        self.patreon = DryRunPatreonPost(self.intent_store, live_publish_enabled=self.config.live_publish_enabled)
        self.royal_road = DryRunRoyalRoadPost(self.intent_store, live_publish_enabled=self.config.live_publish_enabled)
        self.social = DryRunSocialPost(self.intent_store, live_publish_enabled=self.config.live_publish_enabled)
        fiction = dict(self.config.fiction_ids or {})
        inventory = self.config.next_inventory or (lambda: None)

        self.orchestrator = ChapterProductionPostingOrchestrator(
            store=self.orch_store,
            hermes=self.hermes,
            validator=self.validator,
            chapter_store=self.chapter_store,
            patreon_backlog=self.backlog,
            patreon_post=self.patreon,
            royal_road_post=self.royal_road,
            social_post=self.social,
            chapter_media=self.chapter_media,
            royal_road_fiction_id_for=lambda novel_id: fiction.get(novel_id, f"fiction-{novel_id}"),
            next_inventory_chapter=inventory,
        )

    def run_tick(self, *, tick_id: str, workflow_id: Optional[str] = None) -> OrchResult:
        if self.config.live_publish_enabled:
            raise RuntimeError("LIVE_PUBLISH_ENABLED must stay False until canary + explicit enablement")
        return self.orchestrator.run_tick(tick_id=tick_id, workflow_id=workflow_id)

    def run_canary_dry_run(self, *, tick_id: str, workflow_id: str) -> Dict[str, Any]:
        """Prove restart/resume + idempotency before any real publication."""
        first = self.run_tick(tick_id=tick_id, workflow_id=workflow_id)
        second = self.run_tick(tick_id=tick_id, workflow_id=workflow_id)
        return {
            "first_state": first.state,
            "second_reused_existing": second.reused_existing,
            "same_idempotency_key": first.idempotency_key == second.idempotency_key,
            "live_publish_enabled": self.config.live_publish_enabled,
            "video_creates_identity_canon": VIDEO_CREATES_IDENTITY_CANON,
            "social_ready_creates_identity_canon": SOCIAL_READY_CREATES_IDENTITY_CANON,
            "hermes_calls": self.hermes.calls,
            "patreon_calls": self.patreon.calls,
            "royal_road_calls": self.royal_road.calls,
            "first": first.to_dict(),
            "second": second.to_dict(),
        }


def build_entrypoint(
    root: Path,
    chapter_media: ChapterToMediaWorkflow,
    *,
    backlog_items: Optional[List[BacklogItem]] = None,
    fiction_ids: Optional[Dict[str, str]] = None,
    next_inventory: Optional[Callable[[], Optional[BacklogItem]]] = None,
    live_publish_enabled: bool = False,
) -> TaskSchedulerEntrypoint:
    return TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=Path(root),
            live_publish_enabled=live_publish_enabled,
            fiction_ids=fiction_ids,
            backlog_items=backlog_items,
            next_inventory=next_inventory,
        ),
        chapter_media=chapter_media,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry for Task Scheduler. Dry-run only; refuses live publish."""
    import argparse

    parser = argparse.ArgumentParser(description="Production orchestration tick (dry-run)")
    parser.add_argument("--root", required=True, help="Durable state root")
    parser.add_argument("--tick-id", required=True)
    parser.add_argument("--workflow-id", default=None)
    parser.add_argument("--backlog-json", default=None, help="Optional backlog JSON path")
    args = parser.parse_args(argv)

    # Media workflow must be injected by a higher composition root for real runs;
    # CLI dry-run without media refuses to invent live GPU work.
    raise SystemExit(
        "composition root required: construct TaskSchedulerEntrypoint with an injected "
        "ChapterToMediaWorkflow; CLI refuses bare GPU/media defaults"
    )


if __name__ == "__main__":
    raise SystemExit(main())
