"""SC-6 analytics normalization tests.

Verifies the decision to extend existing tables (no new DB):
- migration 004_analytics_provenance adds raw_source_hash to social_stats_daily
- record_social_stats_from_gather() upserts one row per (platform,channel,date)
  with the raw-source provenance hash persisted and idempotent on re-run
- metrics_gather_results raw scrape stays transient (not a normalization target)

All tests use isolated temp DBs; none touch the live automation_state.db.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import automation_db
import storage.migrations as mig


def _temp_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="sc6-"))


def test_migration_adds_provenance_column():
    root = _temp_root()
    automation_db.init_db(root)
    mig.apply_migrations(root)
    # column should now exist
    cols = {r["name"] for r in automation_db.connect(root).execute(
        "PRAGMA table_info(social_stats_daily)").fetchall()}
    assert "raw_source_hash" in cols, cols
    # re-running migration is a no-op (idempotent, no error)
    mig.apply_migrations(root)
    cols2 = {r["name"] for r in automation_db.connect(root).execute(
        "PRAGMA table_info(social_stats_daily)").fetchall()}
    assert "raw_source_hash" in cols2


def test_record_social_stats_from_gather_upserts_and_proves():
    root = _temp_root()
    automation_db.init_db(root)
    mig.apply_migrations(root)

    raw_payload = {"gatheredAt": "2026-07-22T14:09:13Z", "results": [{"platform": "youtube", "channel": "UCx", "metrics": {"views": 345}}]}
    normalized = [{"platform": "youtube", "channel": "UCx", "collected_date": "2026-07-22", "metrics": {"views": 345}}]

    written = automation_db.record_social_stats_from_gather(root, normalized, raw_payload)
    assert written == 1

    row = automation_db.connect(root).execute(
        "SELECT raw_source_hash, metrics_json FROM social_stats_daily WHERE platform='youtube'"
    ).fetchone()
    assert row is not None
    # provenance hash is the sha256 of the raw payload, deterministic
    expected = __import__("hashlib").sha256(
        json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    assert row["raw_source_hash"] == expected
    assert json.loads(row["metrics_json"]) == {"views": 345}


def test_record_social_stats_from_gather_idempotent():
    root = _temp_root()
    automation_db.init_db(root)
    mig.apply_migrations(root)

    normalized = [{"platform": "tiktok", "channel": "tt", "collected_date": "2026-07-22", "metrics": {"views": 2000}}]
    first = automation_db.record_social_stats_from_gather(root, normalized, {"a": 1})
    second = automation_db.record_social_stats_from_gather(root, normalized, {"a": 1})
    assert first == 1 and second == 1  # no duplicate rows
    count = automation_db.connect(root).execute(
        "SELECT COUNT(*) FROM social_stats_daily WHERE platform='tiktok'"
    ).fetchone()[0]
    assert count == 1


def test_empty_results_noop():
    root = _temp_root()
    automation_db.init_db(root)
    mig.apply_migrations(root)
    assert automation_db.record_social_stats_from_gather(root, [], {"x": 1}) == 0


if __name__ == "__main__":
    raise SystemExit(1)
