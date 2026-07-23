# Root JSON → SQLite Conversion Plan (post-SC-7 cleanup)

**Date:** 2026-07-23
**Context:** SC-1..SC-7 complete. Root cleanup classified 84 root JSON files:
- 51 quarantined (buckets 2/3/4: chapter scratch, regression scratch, probe dumps) — reversible via `tools/restore_trash_json.py`.
- 8 held (bucket 5: cron-context) — confirm cron consumers before any move.
- 25 kept (bucket 1: active app state) — **these are the conversion candidates.**

This plan covers converting the 25 kept files into `automation_state.db` so the
repo root carries **zero** app-authored JSON (matching the SQLite-source-of-truth
mandate). No data loss; every step reversible; tests on isolated temp DBs.

## Principle (from SC-3/SC-4)
Two storage homes already exist:
- `state_snapshots(state_key, payload_json, updated_at)` — generic key/value for
  opaque JSON state blobs. Used for `postingSchedule`, `deepTikTokRotation`.
- Dedicated tables (`platform_post_metrics`, `social_stats_daily`, etc.) — for
  structured, queryable data.

**Default:** any kept file that is an opaque state/config blob → a
`state_snapshots` row (one migration, low risk). Only promote to a dedicated
table if the data is queried/aggregated relationally (none of these currently
are — they are consumed as whole blobs by app.py).

## Kept-file → DB mapping

### Group A — opaque state → `state_snapshots` (straightforward, 1 migration)
| File | state_key | Notes |
|------|-----------|-------|
| `release_status.json` | `releaseStatus` | Large (148KB) but consumed as blob. |
| `release-automation-state.json` | `releaseAutomationState` | |
| `automatic-metrics-state.json` | `automaticMetricsState` | Tiny (600B). |
| `pinned-content-plan.json` | `pinnedContentPlan` | |
| `pinned-profile-assets.json` | `pinnedProfileAssets` | |
| `story-hook-chatgpt-result.json` | `storyHookChatgptResult` | |
| `youtube-comment-queue.json` | `youtubeCommentQueue` | Large (162KB) blob. |
| `youtube-end-screen-plan.json` | `youtubeEndScreenPlan` | |
| `youtube-end-screen-state.json` | `youtubeEndScreenState` | |
| `analytics-lab.json` | `analyticsLab` | 891KB — consider keeping as file, NOT DB (size). See note. |
| `creator-benchmarks.json` | `creatorBenchmarks` | |
| `app-regression-dashboard.json` | `appRegressionDashboard` | UI reads whole blob. |

### Group B — backups, DO NOT convert (hold per plan)
`chapter-release-queue.backup-*.json` (12 files) — recovery artifacts. Leave on
disk (or move to a `backups/` dir), never into live state. Not converted.

### Group C — held (bucket 5 cron-context), convert ONLY after confirming cron
`cron-EN-context.json`, `cron-EN-prior.json`, `cron-EN-prior.pretty.json`,
`en_context.json`, `en_ctx.json`, `ha_ctx.json`, `hp_ctx.json`, `sf_ctx.json`.
Map each to a `state_snapshots` key (e.g. `cronEnContext`, `enContext`, ...).
**Gate:** verify which are read by the cron scheduler first; some `*_ctx` may be
obsolete chapter-context scratch (reclassify to quarantine if unused).

## Size caution (do not blindly DB everything)
- `analytics-lab.json` (891KB), `release_status.json` (148KB),
  `youtube-comment-queue.json` (162KB) are large blobs. SQLite handles this fine
  (BLOB up to 1GB), but loading a 162KB/891KB JSON on every request is wasteful.
  **Decision needed:** keep large read-only artifacts as files under `runtime/`
  (like SC-5) rather than DB, OR store in DB but lazy-load. Recommendation: store
  in `state_snapshots` for consistency; add lazy-load if perf shows up. Flag for
  David's call.

## Execution sequence (each an isolated, committed, reversible step)
1. **Migration `005_root_state_to_db`**: add rows to `state_snapshots` for Group A
   keys from the existing root files (idempotent; skip if key exists). Provide
   `storage/root_state_repository.py` with `load/save` delegating to
   `state_snapshots` (mirroring `schedule_repository`).
2. **app.py cutover (Option A pattern)**: repoint each `ROOT / "<file>.json"`
   constant's read/write to the repository. Fail-soft: if DB read fails, fall
   back to the file (preserve current behavior, since files still exist).
3. **Soak**: restart server, confirm each endpoint/feature that uses these files
   works; confirm files no longer written at root.
4. **Quarantine the now-dead root files** (reversible) — same as SC-7.
5. **Group C**: after cron confirmation, repeat 1-4 for the 8 cron-context files.
6. **Tests**: `tests/test_storage_root_state.py` — migration idempotency,
   round-trip per key, fail-soft fallback — on isolated temp DB.

## Acceptance criteria
- [ ] All Group A files load from SQLite; app features behave identically.
- [ ] Root no longer contains Group A JSON (quarantined, reversible).
- [ ] Migration `005` idempotent; storage tests pass on temp DB.
- [ ] Server soak green; no root JSON writes for these.
- [ ] Group B backups untouched; Group C gated on cron confirmation.

## Open decisions for David
1. Large blobs (`analytics-lab` 891KB, `youtube-comment-queue` 162KB,
   `release_status` 148KB): DB vs `runtime/` file? (Recommendation: DB + lazy-load.)
2. Group C cron-context: confirm which are live before converting.
3. `app-regression-dashboard.json` is written by the regression runner — confirm
   the runner is pointed at the new DB path or kept as a file.

## Phase-3 retirement outcome (2026-07-23, commits 23e159b / b829f36 / <commit3> / <commit4>)
- Commits 1-2 retired all Group A root JSON to SQLite (state_snapshots +
  release_status table), lazy-loaded the 3 large blobs, replaced filesystem
  `file` API responses with typed SQLite references
  (`{"file":null,"storage":"sqlite","resource":"state_snapshots","state_key":...}`;
  release_status uses `resource:"release_status"`).
- Commit 3 added retirement enforcement: `storage/retired_state.py` registry +
  guards in `release_state.write_json_atomic` (raises on retired write),
  `promo_copy.read_json_safe` (fails safe to None + warns), and
  `database_state_files()`/`bootstrap_state_database_from_json()` re-registration
  guards. `tests/test_phase3_enforcement.py` (14 tests) covers write-block,
  read-fail-safe, no re-registration, typed responses, lazy-load-during-bootstrap,
  stale-JSON-vs-newer-DB bootstrap regression, and no-runtime-recreation.
  `tools/verify_phase3_retirement.py` is the CI gate (DB health, bootstrap,
  enforcement, large-blob homes, optional --enforce-no-mirrors).

### Known test failures EXCLUDED from the Phase-3 acceptance gate (documented, NOT fixed in Commit 3)
These are pre-existing and unrelated to Phase-3 storage; left as-is per directive.
1. `tests/test_promo_copy.py::test_build_platform_posts_*` (3 asserts): caption
   text + campaign name drift (`weekly_general_promo` vs `catch_up_archive`).
   Post-copy generation logic, untouched by Phase 3. Owner: promo-copy feature.
2. `tests/test_release_state.py` harness defect: references
   `chapter_ledger.json` in a temp dir that the test setup does not create
   (FileNotFoundError). Test-harness bug, not a code regression. `release_state`
   itself is already SQLite-only (verified: load/save go to chapter_ledger /
   release_status tables).

Do NOT "fix" these inside Commit 3; they are tracked separately.
