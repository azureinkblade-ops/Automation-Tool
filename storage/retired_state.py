"""Phase-3 retirement registry and enforcement guards.

This module is the single source of truth for which root JSON mirrors have
been retired (their SQLite-backed replacements are the sole source of truth).
Enforcement helpers here block accidental re-creation or re-registration of
those mirrors, and provide the metadata needed by the verification tool and
the quarantine manifest.

Retirement contract (approved 2026-07-23):
- Each retired root JSON maps to a SQLite home: state_snapshots[<key>] or the
  dedicated `release_status` table.
- No code may write the retired JSON path (write_json_atomic raises).
- No code may read the retired JSON path as a live source (read_json_safe
  fails safe to None + warns).
- The retired keys must not re-appear in database_state_files() (bootstrap).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Root anchors resolve at import time; tests may monkeypatch ROOT via the
# helper below. We compute paths lazily against a passed-in ROOT.
RETIRED_FILE_NAMES = [
    "analytics-lab.json",
    "youtube-comment-queue.json",
    "youtube-pinned-comment-verified.json",
    "release_status.json",
    "pinned-content-plan.json",
    "pinned-profile-assets.json",
    "youtube-end-screen-plan.json",
    "youtube-end-screen-state.json",
    "app-regression-dashboard.json",
    "automatic-metrics-state.json",
    "story-hook-chatgpt-result.json",
    "release-automation-state.json",
]

# state_key -> SQLite home descriptor. resource is either "state_snapshots"
# (keyed by state_key) or "release_status" (relational table; release_status
# has no single state_snapshots key).
RETIRED_STATE_KEYS = {
    "analyticsLab": {"resource": "state_snapshots", "file": "analytics-lab.json"},
    "youtubeCommentQueue": {"resource": "state_snapshots", "file": "youtube-comment-queue.json"},
    "youtubePinnedCommentVerified": {"resource": "state_snapshots", "file": "youtube-pinned-comment-verified.json"},
    "release_status": {"resource": "release_status", "file": "release_status.json", "relational": True},
    "pinnedContentPlan": {"resource": "state_snapshots", "file": "pinned-content-plan.json"},
    "pinnedProfileAssets": {"resource": "state_snapshots", "file": "pinned-profile-assets.json"},
    "youtubeEndScreenPlan": {"resource": "state_snapshots", "file": "youtube-end-screen-plan.json"},
    "youtubeEndScreenState": {"resource": "state_snapshots", "file": "youtube-end-screen-state.json"},
    "appRegressionDashboard": {"resource": "state_snapshots", "file": "app-regression-dashboard.json"},
    "automaticMetricsState": {"resource": "state_snapshots", "file": "automatic-metrics-state.json"},
    "storyHookChatgptResult": {"resource": "state_snapshots", "file": "story-hook-chatgpt-result.json"},
    # release-automation-state.json had no DB row (dead constant); tracked only
    # so the no-recreation guard covers it.
    "releaseAutomationState": {"resource": None, "file": "release-automation-state.json"},
}

# Keys that must NOT re-appear in database_state_files() (bootstrap map).
RETIRED_BOOTSTRAP_KEYS = {
    "releaseStatus",
    "creatorBenchmarks",
    "youtubeCommentQueue",
    "youtubePinnedCommentVerified",
}


class RetiredStateError(RuntimeError):
    """Raised when code attempts to write a retired JSON mirror path."""


def retired_paths(root: Path) -> set[Path]:
    """Absolute set of retired root JSON paths for a given project root."""
    root = Path(root)
    return {root / name for name in RETIRED_FILE_NAMES}


def is_retired_path(path: Path, root: Path | None = None) -> bool:
    """True if `path` resolves to one of the retired root JSON mirrors.

    Matching is by canonical retired file name (anywhere), because the
    enforcement contract is "never write/read a retired mirror" regardless of
    which directory it would land in.
    """
    try:
        p = Path(path).resolve()
    except Exception:
        return False
    if root is not None and p in retired_paths(Path(root)):
        return True
    return p.name in RETIRED_FILE_NAMES


def assert_not_retired_write(path: Path, root: Path | None = None) -> None:
    """Raise RetiredStateError if `path` is a retired mirror (write guard)."""
    if is_retired_path(path, root):
        raise RetiredStateError(
            f"Refusing to write retired Phase-3 JSON mirror: {path}. "
            f"Write to SQLite (state_snapshots / release_status table) instead."
        )


def warn_if_retired_read(path: Path, root: Path | None = None) -> bool:
    """Return True if `path` is a retired mirror (read guard hook)."""
    return is_retired_path(path, root)
