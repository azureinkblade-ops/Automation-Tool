"""SC-7 cleanup / Group A: backfill file-only root JSON into state_snapshots.

Idempotent: copies each Group A file that has NO existing state_snapshots row
into its logical key. Safe to re-run. Does NOT delete the source files (the app
keeps a file fallback during transition; quarantine happens after soak).

Usage: python tools/migrate_root_state.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db  # noqa: E402

# file name -> state_snapshots key (mirrors storage/root_state_repository.py KEYS)
FILE_TO_KEY = {
    "automatic-metrics-state.json": "automaticMetricsState",
    "release-automation-state.json": "releaseAutomationState",
    "story-hook-chatgpt-result.json": "storyHookChatgptResult",
    "pinned-content-plan.json": "pinnedContentPlan",
    "pinned-profile-assets.json": "pinnedProfileAssets",
    "analytics-lab.json": "analyticsLab",
    "youtube-end-screen-plan.json": "youtubeEndScreenPlan",
    "youtube-end-screen-state.json": "youtubeEndScreenState",
    "app-regression-dashboard.json": "appRegressionDashboard",
}


def main() -> int:
    automation_db.init_db(ROOT)
    migrated = 0
    for fname, key in FILE_TO_KEY.items():
        src = ROOT / fname
        existing = automation_db.load_state_snapshot(ROOT, key)
        if existing is not None:
            print(f"[skip] {key} already in DB")
            continue
        if not src.exists():
            print(f"[skip] {fname} absent (not migrated)")
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[error] {fname} not valid JSON: {e}")
            continue
        automation_db.upsert_state_snapshot(ROOT, key, data)
        migrated += 1
        print(f"[migrated] {fname} -> state_snapshots[{key}]")
    print(f"\nMigrated {migrated} file(s) into state_snapshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
