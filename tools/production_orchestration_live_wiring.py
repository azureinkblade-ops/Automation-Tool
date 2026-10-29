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

Default: LIVE_PUBLISH_ENABLED=False / LIVE_PUBLISH_ENABLED_DEFAULT=False.
Real publication requires live_publish_enabled=True AND an approve-token gate:
  - env LIVE_PUBLISH_APPROVE_SHA must equal the current code SHA, OR
  - a one-shot approve file whose first line (or JSON approve_sha) equals that SHA
    (default under evidence: LIVE_PUBLISH_APPROVE_ONESHOT.txt; consumed on success).
DryRun* adapters stay dry-run; Live* adapters run only after the gate passes.
No still/video/social asset becomes identity canon automatically.
SOCIAL_READY_CREATES_IDENTITY_CANON and VIDEO_CREATES_IDENTITY_CANON stay False.
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
from tools.ledger_status import (
    LedgerStatus,
    NextChapterSelection,
    compute_ledger_status_from_db,
    compute_ledger_status_from_structured,
    preflight_chapter_gate,
    select_next_missing_chapter,
)


WIRING_VERSION = "production_orch_live_wiring_v1"

def report_ledger_status(status: LedgerStatus) -> Dict[str, Any]:
    """Observability packet — never a single ledger max."""
    return {
        "LATEST_MATERIALIZED_CHAPTER": status.latest_materialized_chapter,
        "LATEST_RESERVED_CHAPTER": status.latest_reserved_chapter,
        "LATEST_PUBLISHED_CHAPTER": status.latest_published_chapter or 0,
        "write_pending_without_materialization": list(
            status.write_pending_without_materialization
        ),
        "ledger_status": status.to_dict(),
        # Explicitly refuse collapsed reporting
        "ledger_max_collapsed": False,
    }


def next_inventory_from_ledger_status(
    status: LedgerStatus,
    *,
    novel_id: Optional[str] = None,
    channel: str = "patreon",
    priority: int = 50,
) -> Optional[BacklogItem]:
    """Controller select: prefer writePending reconcile over allocate max+1."""
    sel = select_next_missing_chapter(status, novel_id=novel_id)
    return BacklogItem(
        chapter_id=sel.chapter_id,
        novel_id=novel_id or status.novel_id or status.abbr or "XX",
        channel=channel,
        priority=priority,
    )


def controller_select_next_missing(
    db,
    *,
    novel_id: str,
    abbr: Optional[str] = None,
) -> NextChapterSelection:
    """Production controller path: DB → split status → reconcile-preferring select."""
    status = compute_ledger_status_from_db(db, novel_id=novel_id, abbr=abbr)
    return select_next_missing_chapter(status, novel_id=novel_id)


LIVE_PUBLISH_ENABLED_DEFAULT = False
SOCIAL_READY_CREATES_IDENTITY_CANON = False

LIVE_PUBLISH_APPROVE_SHA_ENV = "LIVE_PUBLISH_APPROVE_SHA"
LIVE_PUBLISH_APPROVE_FILE_ENV = "LIVE_PUBLISH_APPROVE_FILE"
LIVE_PUBLISH_APPROVE_ONESHOT_NAME = "LIVE_PUBLISH_APPROVE_ONESHOT.txt"

# HA-113 SOCIAL_READY presented asset + David STILL_OK (production posting soft-gap close).
# Paths are worktree-relative; sha256 values are locked evidence refs. Not identity canon.
HA113_CHAPTER_ID = "HA-113"
HA113_NOVEL_ID = "HA"
HA113_PRESENTED_RELPATH = (
    "output/ha-113-manual-media-package-20261028/presented/"
    "bd91fd87-8792-4294-a784-9ec98c68520c_9x16.mp4"
)
HA113_PRESENTED_SHA256 = (
    "70630d7fafead05f1991de30a1f3afc6a0eb1d234610e869ef90742a1ebc43ef"
)
HA113_STILL_RELPATH = (
    "output/ha-113-manual-media-package-20261028/stills/HA-113_manual_intent_no.png"
)
HA113_STILL_SHA256 = (
    "49352c29e1d234309240c4e9ba6a5efc59ccc3fe44b8476e9b963ba35991e093"
)
HA113_CANON_PROSE_SHA256 = (
    "5db7c792b5888b5c88bd821f4c41b4639ab01a1921432c9ce26ef607627ea557"
)
DEFAULT_EVIDENCE_DIR = Path("output/enable-first-real-publication-surface-20261028")


def resolve_code_sha(*, explicit: Optional[str] = None, repo_root: Optional[Path] = None) -> str:
    """Return the code SHA used for LIVE_PUBLISH approve matching."""
    if explicit:
        return str(explicit).strip()
    env_sha = os.environ.get("LIVE_PUBLISH_CODE_SHA", "").strip()
    if env_sha:
        return env_sha
    root = Path(repo_root) if repo_root else Path.cwd()
    git_dir = root / ".git"
    # Prefer reading HEAD directly so tests need no subprocess network.
    try:
        import subprocess

        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except OSError:
        pass
    if git_dir.is_file():
        # worktree gitfile — fall through to failure
        pass
    raise RuntimeError("unable to resolve code SHA for LIVE_PUBLISH approve gate")


def _parse_approve_file_token(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key in ("approve_sha", "LIVE_PUBLISH_APPROVE_SHA", "sha", "sha256"):
                val = data.get(key)
                if val:
                    return str(val).strip()
    return text.splitlines()[0].strip()


def default_live_publish_approve_file(*, evidence_dir: Optional[Path] = None) -> Path:
    base = Path(evidence_dir) if evidence_dir else DEFAULT_EVIDENCE_DIR
    return Path(base) / LIVE_PUBLISH_APPROVE_ONESHOT_NAME


def assert_live_publish_approved(
    *,
    code_sha: Optional[str] = None,
    approve_file: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    consume_oneshot: bool = True,
) -> str:
    """Fail-closed LIVE_PUBLISH gate.

    Returns approval mode: "env" or "file".
    Requires env LIVE_PUBLISH_APPROVE_SHA == code SHA, OR a one-shot approve file
    whose token equals the code SHA. Missing/mismatch raises RuntimeError.
    """
    sha = resolve_code_sha(explicit=code_sha)
    env_token = os.environ.get(LIVE_PUBLISH_APPROVE_SHA_ENV, "").strip()
    if env_token:
        if env_token == sha:
            return "env"
        raise RuntimeError(
            f"LIVE_PUBLISH refused: {LIVE_PUBLISH_APPROVE_SHA_ENV} mismatch "
            f"(token!=code_sha)"
        )

    path: Optional[Path]
    if approve_file is not None:
        path = Path(approve_file)
    else:
        env_path = os.environ.get(LIVE_PUBLISH_APPROVE_FILE_ENV, "").strip()
        path = Path(env_path) if env_path else default_live_publish_approve_file(
            evidence_dir=evidence_dir
        )

    if path is None or not path.exists():
        raise RuntimeError(
            "LIVE_PUBLISH refused: missing approve token "
            f"(set {LIVE_PUBLISH_APPROVE_SHA_ENV}==code_sha or provide oneshot file)"
        )

    file_token = _parse_approve_file_token(path.read_text(encoding="utf-8"))
    if file_token != sha:
        raise RuntimeError(
            "LIVE_PUBLISH refused: approve file token mismatch (token!=code_sha)"
        )

    if consume_oneshot:
        consumed = path.with_suffix(path.suffix + ".consumed")
        try:
            os.replace(path, consumed)
        except OSError:
            # Best-effort oneshot consume; approval already validated.
            try:
                path.unlink()
            except OSError:
                pass
    return "file"


def normalize_chapter_id(chapter_id: str) -> str:
    return str(chapter_id or "").strip().upper().replace("_", "-")


def is_ha113_chapter(chapter_id: str, *, novel_id: Optional[str] = None) -> bool:
    cid = normalize_chapter_id(chapter_id)
    if cid in {HA113_CHAPTER_ID, "HA113", "CHAPTER-113"}:
        return True
    if cid.endswith("-113") and (novel_id or "").strip().upper() in {"", "HA", "HEAVENLY-ASCENSION"}:
        # e.g. HA-113 already covered; allow novel-scoped forms
        if cid == "HA-113":
            return True
    if cid == "113" and (novel_id or "").strip().upper() == "HA":
        return True
    return cid == HA113_CHAPTER_ID


def ha113_publish_asset_metadata(
    *,
    worktree_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """SOCIAL_READY presented mp4 + STILL_OK metadata for HA-113 publish intents."""
    root = Path(worktree_root) if worktree_root else Path.cwd()
    presented = root / HA113_PRESENTED_RELPATH
    still = root / HA113_STILL_RELPATH
    return {
        "chapter_id": HA113_CHAPTER_ID,
        "novel_id": HA113_NOVEL_ID,
        "media_outcome": "SOCIAL_READY",
        "asset_kind": "presented_video",
        "asset_path": str(presented),
        "asset_sha256": HA113_PRESENTED_SHA256,
        "presented_relpath": HA113_PRESENTED_RELPATH,
        "presented_sha256": HA113_PRESENTED_SHA256,
        "still_ok": True,
        "still_path": str(still),
        "still_sha256": HA113_STILL_SHA256,
        "still_relpath": HA113_STILL_RELPATH,
        "canon_prose_sha256": HA113_CANON_PROSE_SHA256,
        "identity_canon": False,
        "social_ready_creates_identity_canon": False,
        "video_creates_identity_canon": False,
        "disposition": "FULFILLED_BY_MANUAL",
    }


def enrich_publish_payload_for_chapter(
    payload: Dict[str, Any],
    *,
    novel_id: str,
    chapter_id: str,
    worktree_root: Optional[Path] = None,
) -> Dict[str, Any]:
    out = dict(payload)
    if is_ha113_chapter(chapter_id, novel_id=novel_id):
        meta = ha113_publish_asset_metadata(worktree_root=worktree_root)
        out["ha113"] = meta
        out.setdefault("asset_path", meta["asset_path"])
        out.setdefault("asset_sha256", meta["asset_sha256"])
        out.setdefault("asset_kind", meta["asset_kind"])
        out["still_ok"] = True
        out["still_path"] = meta["still_path"]
        out["still_sha256"] = meta["still_sha256"]
        out["identity_canon"] = False
    return out


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
        payload = enrich_publish_payload_for_chapter(
            {"store_id": store_id},
            novel_id=novel_id,
            chapter_id=chapter_id,
        )
        self.intents.save(
            DryRunIntent(
                channel="patreon",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=remote_id,
                payload=payload,
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
        payload = enrich_publish_payload_for_chapter(
            {"store_id": store_id, "remote_fiction_id": remote_fiction_id},
            novel_id=novel_id,
            chapter_id=chapter_id,
        )
        self.intents.save(
            DryRunIntent(
                channel="royal_road",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=remote_id,
                payload=payload,
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
        payload = enrich_publish_payload_for_chapter(
            {
                "asset_path": asset_path,
                "asset_sha256": asset_sha256,
                "asset_kind": asset_kind,
                "identity_canon": False,
            },
            novel_id=novel_id,
            chapter_id=chapter_id,
        )
        # Prefer HA-113 SOCIAL_READY presented asset when chapter matches and caller omitted asset
        if payload.get("ha113") and not asset_path:
            asset_path = payload.get("asset_path")
            asset_sha256 = payload.get("asset_sha256")
            asset_kind = payload.get("asset_kind")
            payload["asset_path"] = asset_path
            payload["asset_sha256"] = asset_sha256
            payload["asset_kind"] = asset_kind
        self.intents.save(
            DryRunIntent(
                channel="social",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="POSTED_DRY_RUN",
                remote_id=f"dry-social-{chapter_id}",
                payload=payload,
            )
        )
        return SocialPostResult(status="POSTED", asset_kind=asset_kind, asset_sha256=asset_sha256)


class LivePatreonPost:
    """Live Patreon surface — only constructed when live_publish_enabled and gate passes path.

    Network I/O is delegated to an injected publisher callable (tests use fakes).
    Without a publisher, records a durable LIVE_PUBLISH_INTENT only (no network).
    """

    def __init__(
        self,
        intents: IntentStore,
        *,
        publisher: Optional[Callable[..., PublishResult]] = None,
        worktree_root: Optional[Path] = None,
    ) -> None:
        self.intents = intents
        self.publisher = publisher
        self.worktree_root = Path(worktree_root) if worktree_root else None
        self.calls = 0

    def post_chapter(self, *, novel_id: str, chapter_id: str, store_id: str, idempotency_key: str) -> PublishResult:
        self.calls += 1
        existing = self.intents.get(idempotency_key)
        if existing:
            return PublishResult(
                channel="patreon",
                remote_id=existing.remote_id,
                idempotency_key=idempotency_key,
                status="SKIPPED_IDEMPOTENT",
            )
        payload = enrich_publish_payload_for_chapter(
            {"store_id": store_id, "live": True},
            novel_id=novel_id,
            chapter_id=chapter_id,
            worktree_root=self.worktree_root,
        )
        if self.publisher is not None:
            result = self.publisher(
                novel_id=novel_id,
                chapter_id=chapter_id,
                store_id=store_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            self.intents.save(
                DryRunIntent(
                    channel="patreon",
                    novel_id=novel_id,
                    chapter_id=chapter_id,
                    idempotency_key=idempotency_key,
                    status="POSTED_LIVE",
                    remote_id=result.remote_id,
                    payload=payload,
                )
            )
            return result
        remote_id = f"live-patreon-intent-{chapter_id}"
        self.intents.save(
            DryRunIntent(
                channel="patreon",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="LIVE_PUBLISH_INTENT",
                remote_id=remote_id,
                payload=payload,
            )
        )
        return PublishResult(
            channel="patreon",
            remote_id=remote_id,
            idempotency_key=idempotency_key,
            status="POSTED",
        )


class LiveRoyalRoadPost:
    def __init__(
        self,
        intents: IntentStore,
        *,
        publisher: Optional[Callable[..., PublishResult]] = None,
        worktree_root: Optional[Path] = None,
    ) -> None:
        self.intents = intents
        self.publisher = publisher
        self.worktree_root = Path(worktree_root) if worktree_root else None
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
        existing = self.intents.get(idempotency_key)
        if existing:
            return PublishResult(
                channel="royal_road",
                remote_id=existing.remote_id,
                idempotency_key=idempotency_key,
                status="SKIPPED_IDEMPOTENT",
            )
        payload = enrich_publish_payload_for_chapter(
            {"store_id": store_id, "remote_fiction_id": remote_fiction_id, "live": True},
            novel_id=novel_id,
            chapter_id=chapter_id,
            worktree_root=self.worktree_root,
        )
        if self.publisher is not None:
            result = self.publisher(
                novel_id=novel_id,
                chapter_id=chapter_id,
                store_id=store_id,
                remote_fiction_id=remote_fiction_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            self.intents.save(
                DryRunIntent(
                    channel="royal_road",
                    novel_id=novel_id,
                    chapter_id=chapter_id,
                    idempotency_key=idempotency_key,
                    status="POSTED_LIVE",
                    remote_id=result.remote_id,
                    payload=payload,
                )
            )
            return result
        remote_id = f"live-rr-intent-{remote_fiction_id}-{chapter_id}"
        self.intents.save(
            DryRunIntent(
                channel="royal_road",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="LIVE_PUBLISH_INTENT",
                remote_id=remote_id,
                payload=payload,
            )
        )
        return PublishResult(
            channel="royal_road",
            remote_id=remote_id,
            idempotency_key=idempotency_key,
            status="POSTED",
        )


class LiveSocialPost:
    def __init__(
        self,
        intents: IntentStore,
        *,
        publisher: Optional[Callable[..., SocialPostResult]] = None,
        worktree_root: Optional[Path] = None,
    ) -> None:
        self.intents = intents
        self.publisher = publisher
        self.worktree_root = Path(worktree_root) if worktree_root else None
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
        existing = self.intents.get(idempotency_key)
        if existing:
            return SocialPostResult(
                status="SKIPPED_IDEMPOTENT",
                asset_kind=existing.payload.get("asset_kind"),
                asset_sha256=existing.payload.get("asset_sha256"),
            )
        payload = enrich_publish_payload_for_chapter(
            {
                "asset_path": asset_path,
                "asset_sha256": asset_sha256,
                "asset_kind": asset_kind,
                "identity_canon": False,
                "live": True,
            },
            novel_id=novel_id,
            chapter_id=chapter_id,
            worktree_root=self.worktree_root,
        )
        if payload.get("ha113"):
            if not asset_path:
                asset_path = payload.get("asset_path")
            if not asset_sha256:
                asset_sha256 = payload.get("asset_sha256")
            if not asset_kind:
                asset_kind = payload.get("asset_kind")
            payload["asset_path"] = asset_path
            payload["asset_sha256"] = asset_sha256
            payload["asset_kind"] = asset_kind
        if asset_kind is None and asset_path is None:
            return SocialPostResult(status="SKIPPED_NO_ASSET")
        if self.publisher is not None:
            result = self.publisher(
                novel_id=novel_id,
                chapter_id=chapter_id,
                asset_path=asset_path,
                asset_sha256=asset_sha256,
                asset_kind=asset_kind,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            self.intents.save(
                DryRunIntent(
                    channel="social",
                    novel_id=novel_id,
                    chapter_id=chapter_id,
                    idempotency_key=idempotency_key,
                    status="POSTED_LIVE",
                    remote_id=f"live-social-{chapter_id}",
                    payload=payload,
                )
            )
            return result
        self.intents.save(
            DryRunIntent(
                channel="social",
                novel_id=novel_id,
                chapter_id=chapter_id,
                idempotency_key=idempotency_key,
                status="LIVE_PUBLISH_INTENT",
                remote_id=f"live-social-intent-{chapter_id}",
                payload=payload,
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
    ledger_status: Optional[LedgerStatus] = None
    ledger_db_path: Optional[Path] = None
    ledger_novel_id: Optional[str] = None
    ledger_abbr: Optional[str] = None
    # LIVE_PUBLISH approve-token gate (fail-closed). Tests pass explicit code_sha.
    code_sha: Optional[str] = None
    live_publish_approve_file: Optional[Path] = None
    live_publish_evidence_dir: Optional[Path] = None
    consume_live_publish_oneshot: bool = True
    # Optional Live* network publishers (tests inject fakes; default None = intent-only).
    live_patreon_publisher: Optional[Callable[..., PublishResult]] = None
    live_royal_road_publisher: Optional[Callable[..., PublishResult]] = None
    live_social_publisher: Optional[Callable[..., SocialPostResult]] = None
    worktree_root: Optional[Path] = None


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
        self.live_publish_approval_mode: Optional[str] = None
        wt = Path(self.config.worktree_root) if self.config.worktree_root else None
        if self.config.live_publish_enabled:
            # Live* adapters only — DryRun* must not silently no-op when live.
            self.patreon = LivePatreonPost(
                self.intent_store,
                publisher=self.config.live_patreon_publisher,
                worktree_root=wt,
            )
            self.royal_road = LiveRoyalRoadPost(
                self.intent_store,
                publisher=self.config.live_royal_road_publisher,
                worktree_root=wt,
            )
            self.social = LiveSocialPost(
                self.intent_store,
                publisher=self.config.live_social_publisher,
                worktree_root=wt,
            )
        else:
            self.patreon = DryRunPatreonPost(self.intent_store, live_publish_enabled=False)
            self.royal_road = DryRunRoyalRoadPost(self.intent_store, live_publish_enabled=False)
            self.social = DryRunSocialPost(self.intent_store, live_publish_enabled=False)
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
            self.live_publish_approval_mode = assert_live_publish_approved(
                code_sha=self.config.code_sha,
                approve_file=self.config.live_publish_approve_file,
                evidence_dir=self.config.live_publish_evidence_dir,
                consume_oneshot=self.config.consume_live_publish_oneshot,
            )
        else:
            self.live_publish_approval_mode = None
        return self.orchestrator.run_tick(tick_id=tick_id, workflow_id=workflow_id)

    def resolve_ledger_status(self) -> Optional[LedgerStatus]:
        if self.config.ledger_status is not None:
            return self.config.ledger_status
        if self.config.ledger_db_path and self.config.ledger_novel_id:
            return compute_ledger_status_from_db(
                self.config.ledger_db_path,
                novel_id=self.config.ledger_novel_id,
                abbr=self.config.ledger_abbr,
            )
        return None

    def run_canary_dry_run(self, *, tick_id: str, workflow_id: str) -> Dict[str, Any]:
        """Prove restart/resume + idempotency before any real publication."""
        first = self.run_tick(tick_id=tick_id, workflow_id=workflow_id)
        second = self.run_tick(tick_id=tick_id, workflow_id=workflow_id)
        out: Dict[str, Any] = {
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
        status = self.resolve_ledger_status()
        if status is not None:
            out.update(report_ledger_status(status))
            # Preflight against selected chapter when present
            ch_id = first.chapter_id or (second.chapter_id if second else None)
            if ch_id and "-" in str(ch_id):
                try:
                    cand = int(str(ch_id).rsplit("-", 1)[-1])
                except ValueError:
                    cand = None
                if cand is not None:
                    sel = select_next_missing_chapter(status, novel_id=status.novel_id)
                    gate = preflight_chapter_gate(
                        status, candidate_chapter=cand, mode=sel.mode
                    )
                    out["preflight"] = gate
                    out["controller_selection"] = sel.to_dict()
                    # Never claim clean allocate when reservation holds candidate
                    out["CHAPTER_ALREADY_EXISTS"] = gate["CHAPTER_ALREADY_EXISTS"]
                    out["LEDGER_CLEAN_FOR_ALLOCATE"] = gate["LEDGER_CLEAN_FOR_ALLOCATE"]
        return out


def build_entrypoint(
    root: Path,
    chapter_media: ChapterToMediaWorkflow,
    *,
    backlog_items: Optional[List[BacklogItem]] = None,
    fiction_ids: Optional[Dict[str, str]] = None,
    next_inventory: Optional[Callable[[], Optional[BacklogItem]]] = None,
    live_publish_enabled: bool = False,
    code_sha: Optional[str] = None,
    live_publish_approve_file: Optional[Path] = None,
    live_patreon_publisher: Optional[Callable[..., PublishResult]] = None,
    live_royal_road_publisher: Optional[Callable[..., PublishResult]] = None,
    live_social_publisher: Optional[Callable[..., SocialPostResult]] = None,
    worktree_root: Optional[Path] = None,
) -> TaskSchedulerEntrypoint:
    return TaskSchedulerEntrypoint(
        config=LiveWiringConfig(
            root=Path(root),
            live_publish_enabled=live_publish_enabled,
            fiction_ids=fiction_ids,
            backlog_items=backlog_items,
            next_inventory=next_inventory,
            code_sha=code_sha,
            live_publish_approve_file=live_publish_approve_file,
            live_patreon_publisher=live_patreon_publisher,
            live_royal_road_publisher=live_royal_road_publisher,
            live_social_publisher=live_social_publisher,
            worktree_root=worktree_root,
        ),
        chapter_media=chapter_media,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry for Task Scheduler. Default dry-run; live requires approve-token gate."""
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
