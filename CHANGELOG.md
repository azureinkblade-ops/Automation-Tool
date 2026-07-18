# Changelog

## 2026-07-18 — SQLite Phase 1 + regression safety guard

### Phase 1: workflow-correctness state → SQLite read-first + dual-write
- `approval_inbox.save_approval_cleared_state` now mirrors every cleared item to
  `automation_db.upsert_approval_cleared` (read path was already DB-first; the
  save path wrote JSON only, so cleared items could reappear — fixed).
- `load/save_promo_rotation_state` and `read/write_youtube_daily_status` now use
  `state_snapshots` kv (`promoRotation`, `youtubeDailyStatus`) as SQLite-first
  with JSON backfill + dual-write.
- `release_status` / `chapter_ledger` / `post_records` / `release_automation_jobs`
  and the `nextSelections` paths (release upload, full YouTube, variants) were
  already DB-backed and DB-first — no change needed.
- JSON files kept as mirrors during the soak period (not deleted).

### Regression safety guard (`tools/regression_check.py::check_db_source_of_truth`)
- Verifies approval cleared, promo rotation, and YouTube daily status are
  SQLite-backed, DB-first, and dual-written.
- **Test-hygiene rule added:** no regression check may write to live JSON state
  files or `automation_state.db` unless running in a disposable test workspace;
  state-mutating checks must use `TEST_STATE_ROOT()` (tempdir).

### ⚠️ Incident: `promo-image-rotation.json` image-reuse history reset
On 2026-07-18, during verification of the Phase 1 changes, a regression-style
check wrote test data into the untracked runtime state file
`promo-image-rotation.json` (image-dedup `IMAGE_USAGE` timestamps) and there was
no backup. The real image-usage history was overwritten and is unrecoverable
from the workspace. The file was deleted so the app regenerates it cleanly, but
**image-reuse "last used" history was reset to empty** — meaning images may be
reused somewhat sooner than they would have been until the history rebuilds.
Any unexpected early image reuse after this date is explainable by this reset.
This incident is exactly why the `check_db_source_of_truth` test-hygiene rule
(now) forbids regression checks from writing live runtime state.
