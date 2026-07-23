"""Authoritative storage resource manifest for SQLite consolidation.

Every root-level JSON and logical state resource must resolve to exactly one
entry here. The manifest is the single source of truth for later migration and
quarantine stages. It is deliberately explicit and evidence-backed.

Classifications:
- sqlite_state: current durable state / mutable configuration
- sqlite_history: append-oriented metrics, experiments, history
- sqlite_job_state: job status, attempts, leases, durable results
- file_artifact: generated media or per-asset metadata.json provenance
- file_cache: regenerable file cache
- file_debug_output: manual diagnostic / audit report
- file_fixture: active test fixture or snapshot
- file_import_export: user or external interchange
- dead_file: no producer/consumer and no recovery value
- unknown: blocks cleanup until resolved

Known correction vs the preliminary 2026-07-22 audit: deep-tiktok-rotation.json
is durable READ+WRITE state. It is read at app.py:15583-15584 and written through
write_json_atomic at app.py:15619. It is not read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


CLASSIFICATIONS = (
    "sqlite_state",
    "sqlite_history",
    "sqlite_job_state",
    "file_artifact",
    "file_cache",
    "file_debug_output",
    "file_fixture",
    "file_import_export",
    "dead_file",
    "unknown",
)


ResourceClassification = str


@dataclass
class StorageResource:
    """One logical persistent object and its migration verdict."""

    resource: str
    classification: ResourceClassification
    storage: str
    legacy_file: Optional[str] = None
    current_writers: List[str] = field(default_factory=list)
    current_readers: List[str] = field(default_factory=list)
    durable: bool = False
    target: str = ""
    target_db: str = "automation_state.db"
    migration_status: str = "pending"
    migration_action: str = ""
    evidence: str = ""

    def is_unknown(self) -> bool:
        return self.classification == "unknown"

    def to_dict(self) -> Dict[str, object]:
        return {
            "resource": self.resource,
            "classification": self.classification,
            "storage": self.storage,
            "legacy_file": self.legacy_file,
            "current_writers": self.current_writers,
            "current_readers": self.current_readers,
            "durable": self.durable,
            "target": self.target,
            "target_db": self.target_db,
            "migration_status": self.migration_status,
            "migration_action": self.migration_action,
            "evidence": self.evidence,
        }


def _app_ref(line: str) -> str:
    return f"app.py:{line}"


# Posting schedule: confirmed gap. Live JSON (releaseQueueStartDate 2026-07-19)
# is newer than the stale DB snapshot (2026-07-03). JSON wins on one-time import.
POSTING_SCHEDULE = StorageResource(
    resource="postingSchedule",
    classification="sqlite_state",
    storage="sqlite",
    legacy_file="posting_schedule.json",
    current_writers=[_app_ref("13417"), _app_ref("18036")],
    current_readers=[_app_ref("13387"), _app_ref("13388")],
    durable=True,
    target="state_snapshots.postingSchedule",
    target_db="automation_state.db",
    migration_status="pending",
    migration_action="Migrate JSON to SQLite via one-time parity import (JSON authoritative), then remove runtime file I/O",
    evidence="Read at app.py:13387-13388; write at app.py:13417 and 18036. JSON newer than DB snapshot.",
)

# Deep-TikTok rotation: previously misclassified read-only. Confirmed durable.
DEEP_TIKTOK_ROTATION = StorageResource(
    resource="deepTikTokRotation",
    classification="sqlite_state",
    storage="sqlite",
    legacy_file="deep-tiktok-rotation.json",
    current_writers=[_app_ref("15619")],
    current_readers=[_app_ref("15583"), _app_ref("15584")],
    durable=True,
    target="state_snapshots.deepTikTokRotation",
    target_db="automation_state.db",
    migration_status="pending",
    migration_action="Migrate JSON to SQLite; remove file-stat cache behavior",
    evidence="Read at app.py:15583-15584 via read_json_safe; write at app.py:15619 via write_json_atomic.",
)

YOUTUBE_LIBRARY_SCAN = StorageResource(
    resource="youtubeLibraryScan",
    classification="file_cache",
    storage="file_cache",
    legacy_file="youtube-library-scan.json",
    current_writers=[_app_ref("2567")],
    current_readers=[_app_ref("11245")],
    durable=False,
    target="runtime/cache/youtube-library-scan.json",
    target_db="automation_state.db",
    migration_status="keep",
    migration_action="Relocate out of repo root; keep as regenerable cache",
    evidence="Write at app.py:2567; existence-gated read at app.py:11245.",
)

METADATA_SIDECAR = StorageResource(
    resource="assetMetadataSidecar",
    classification="file_artifact",
    storage="filesystem",
    legacy_file="metadata.json (per-asset sidecar)",
    current_writers=["asset pipeline"],
    current_readers=["asset pipeline"],
    durable=True,
    target="filesystem (per-asset metadata.json)",
    target_db="automation_state.db",
    migration_status="keep",
    migration_action="Retain by design; DB stores status/hash/provenance, not the sidecar",
    evidence="Hybrid storage model: SQLite state + filesystem artifacts + per-asset provenance sidecars.",
)


# Default seed. Later stages add entries; SC-1 verifies completeness against
# every root JSON and the per-asset metadata pattern.
STATE_RESOURCES: Dict[str, StorageResource] = {
    POSTING_SCHEDULE.resource: POSTING_SCHEDULE,
    DEEP_TIKTOK_ROTATION.resource: DEEP_TIKTOK_ROTATION,
    YOUTUBE_LIBRARY_SCAN.resource: YOUTUBE_LIBRARY_SCAN,
    METADATA_SIDECAR.resource: METADATA_SIDECAR,
}


def load_manifest() -> Dict[str, StorageResource]:
    """Return the authoritative resource map.

    Returns a copy so callers cannot mutate the module-level seed.
    """
    return dict(STATE_RESOURCES)


def classify_root_json(filename: str, manifest: Dict[str, StorageResource]) -> Optional[StorageResource]:
    """Resolve a root JSON filename to its manifest resource, if known.

    The per-asset metadata sidecar is matched by pattern, not exact filename.
    """
    if filename == "metadata.json" or filename.endswith("/metadata.json"):
        return manifest.get("assetMetadataSidecar")
    for resource in manifest.values():
        if resource.legacy_file and resource.legacy_file == filename:
            return resource
    return None
