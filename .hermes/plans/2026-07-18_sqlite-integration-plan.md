# SQLite Integration Plan — Replace JSON state with the existing `automation_state.db`

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make `automation_state.db` (via `automation_db.py`) the single source of truth for all app state currently spread across ~50 JSON files, removing the JSON files without breaking live operations.

**Architecture:** `automation_db.py` already exists with 26+ tables and 61 functions (SCHEMA_VERSION=6). The app already dual-reads some state (e.g. `load_release_status` checks the DB then falls back to JSON). We generalize that dual-path pattern: (1) add any missing tables, (2) backfill them from the JSON files, (3) flip app reads/writes to the DB with JSON as a过渡 fallback, (4) delete the JSON files once the DB is confirmed source-of-truth. Migrations run behind `SCHEMA_VERSION` bumps with backfill, never destructive.

**Tech Stack:** Python `sqlite3` (stdlib), `automation_db.py` (existing module), `orjson` (optional fast JSON), `threading.RLock` (already used for DB serialization). No new dependencies.

---

## Current State (inventory)

### DB already covers these JSON files (partially wired)
| JSON file (`app.py` constant) | DB table |
|---|---|
| `release_status.json` (`RELEASE_STATUS_FILE`) | `release_status` |
| `chapter_ledger.json` (`CHAPTER_LEDGER_FILE`) | `chapter_ledger` |
| `post-records.json` (`POST_RECORDS_FILE`) | `post_records` |
| `approval-inbox-cleared.json` (`APPROVAL_INBOX_CLEARED_FILE`) | `approval_cleared` |
| `recovery_log.json` (`RECOVERY_LOG_FILE`) | `recovery_events` |
| `promo-image-rotation.json`? | `state_snapshots` (generic kv) |
| `chapter-release-queue.json` (`CHAPTER_RELEASE_QUEUE_FILE`) | `release_plan_rows` + `release_automation_jobs` |
| platform post files (`*_posts`) | `platform_posts`, `youtube_posts`, `tiktok_posts`, `instagram_posts`, `facebook_posts`, `x_posts`, `patreon_posts`, `royal_road_posts` |
| `growth-stats-history.json` / daily | `social_stats_daily` |
| `weekly-growth-report.json` / plan | `weekly_growth_plans` / `weekly_growth_slots` |

### JSON files with NO DB table yet (GAPS — new tables needed)
- **Story/media jobs:** `story-hook-video-status.json` (`STORY_HOOK_STATUS_FILE`), `image-lab.json` (`IMAGE_LAB_FILE`), `image-feedback.json` (`IMAGE_FEEDBACK_FILE`), `thumbnail-tests.json` (`THUMBNAIL_TESTS_FILE`), `chatgpt-chapter-status.json` (`CHATGPT_CHAPTER_STATUS_FILE`), `chatgpt-chapter-result.json`, `browser-image-assist.json` (`BROWSER_IMAGE_ASSIST_FILE`), `google-ai-image-usage.json` (`GOOGLE_AI_IMAGE_USAGE_FILE`).
- **Experiments/strategy:** `content_experiments.json` (`CONTENT_EXPERIMENTS_FILE`), `brand_brain.json` (`BRAND_BRAIN_FILE`), `automation-strategy.json` (`AUTOMATION_STRATEGY_FILE`), `growth-automation.json` (`GROWTH_AUTOMATION_FILE`), `arc-campaigns.json` (`ARC_CAMPAIGN_FILE`), `weekly-autopilot.json` (`WEEKLY_AUTOPILOT_FILE`), `weekly-growth-settings.json` (`WEEKLY_GROWTH_SETTINGS_FILE`), `predictive-growth-plan.json` (`PREDICTIVE_GROWTH_PLAN_FILE`), `pinned-profile-assets.json` (`PINNED_ASSET_PLAN_FILE`), `pinned-content-plan.json` (`PINNED_CONTENT_PLAN_FILE`), `profile-conversion-audit.json` (`PROFILE_AUDIT_FILE`), `conversion-tracking.json` (`CONVERSION_TRACKING_FILE`), `creator-benchmarks.json` (`CREATOR_BENCHMARK_FILE`).
- **Growth/metrics:** `metrics-gather-results.json` (`METRICS_GATHER_FILE`), `growth-stats-history.json` (`GROWTH_STATS_HISTORY_FILE`), `automatic-metrics-state.json` (`AUTO_METRICS_STATE_FILE`), `growth-weekly-report.json` (`GROWTH_WEEKLY_REPORT_FILE`), `growth-optimizer-plan.json` (`GROWTH_OPTIMIZER_FILE`), `instagram-growth-blueprint.json` (`INSTAGRAM_GROWTH_BLUEPRINT_FILE`), `growth-control-center.json` (`GROWTH_CONTROL_CENTER_FILE`), `comment-assistant.json` (`COMMENT_ASSISTANT_FILE`), `comment-gather-results.json` (`COMMENT_GATHER_RAW_FILE`).
- **YouTube sub-state:** `youtube-post-drafts.json` (`YOUTUBE_POST_DRAFTS_FILE`), `youtube-metadata-experiments.json`, `youtube-upload-pending.json` (`YOUTUBE_PENDING_UPLOAD_FILE`), `youtube-comment-queue.json` (`YOUTUBE_COMMENT_QUEUE_FILE`), `youtube-pinned-comment-verified.json`, `youtube_daily_queue_status.json` (`YOUTUBE_DAILY_STATUS_FILE`).
- **Scheduling/rotation/other:** `posting_schedule.json` (`SCHEDULE_FILE`), `promo-image-rotation.json` (`PROMO_ROTATION_STATE_FILE`), `background-video-usage.json` (`BACKGROUND_VIDEO_USAGE_FILE`), `chapter-path-state.json` (`CHAPTER_PATH_FILE`), `release-automation-state.json` (`RELEASE_AUTOMATION_STATE_FILE`), `patreon-draft-pending.json` (`PATREON_PENDING_DRAFT_FILE`), `clickup-sync.json` (`CLICKUP_SYNC_FILE`), `kpi-sync-log.json` (`KPI_SYNC_LOG_FILE`), `monetization-status.json` (`MONETIZATION_STATUS_FILE`), `app-regression-dashboard.json` (`APP_TEST_REPORT_FILE`).

### JSON files that should STAY as files (not DB candidates)
Config, templates, scripts, user-authored content: `.env.local`, `social_prompt_template.txt`, all `*-playwright.js` scripts, research briefs (Obsidian), generated post text (`*.txt`), images. These are not "state" — exclude from migration.

---

## Proposed New Tables (gaps)

Group the gaps into coherent tables (don't make 50 tables — consolidate):

1. **`media_jobs`** — story-hook, image-lab, chatgpt-chapter, browser-image-assist, thumbnail-tests, google-ai-image-usage. Columns: `job_id, kind, abbr, status, payload_json, result_json, created_at, finished_at`. Replaces STORY_HOOK_STATUS_FILE, IMAGE_LAB_FILE (queue), IMAGE_FEEDBACK_FILE, THUMBNAIL_TESTS_FILE, CHATGPT_CHAPTER_STATUS_FILE, BROWSER_IMAGE_ASSIST_FILE, GOOGLE_AI_IMAGE_USAGE_FILE.
2. **`experiments`** — content_experiments, youtube-metadata-experiments, pinned-content-plan. Columns: `experiment_id, kind, abbr, config_json, results_json, status, created_at`.
3. **`growth_state`** — growth-automation, automation-strategy, weekly-autopilot, weekly-growth-settings, predictive-growth-plan, instagram-growth-blueprint, growth-control-center, growth-optimizer-plan, profile-conversion-audit, conversion-tracking, creator-benchmarks, brand_brain, arc-campaigns, comment-assistant, comment-gather-results, metrics-gather-results, growth-weekly-report. Columns: `key TEXT PRIMARY KEY, payload_json, updated_at`. (Key-value, like `state_snapshots` — reuse `state_snapshots` instead of a new table where possible.)
4. **`youtube_substate`** — youtube-post-drafts, youtube-upload-pending, youtube-comment-queue, youtube-pinned-comment-verified, youtube_daily_queue_status. Columns: `key TEXT PRIMARY KEY, payload_json, updated_at` (or extend `youtube_posts`).
5. **`app_state_kv`** — posting_schedule, promo-image-rotation, background-video-usage, chapter-path-state, release-automation-state, patreon-draft-pending, clickup-sync, kpi-sync-log, monetization-status, app-regression-dashboard. Columns: `key TEXT PRIMARY KEY, payload_json, updated_at`. (Reuse `state_snapshots` for these — it already exists as a generic kv.)
6. **`image_feedback`** (optional separate) — if image-feedback needs querying beyond kv, give it `id, abbr, image_path, rating, note, created_at`.

> Reuse the existing `state_snapshots(key, payload_json, updated_at)` table for all generic key-value JSON state (growth_state, youtube_substate, app_state_kv) — only add purpose-built tables (`media_jobs`, `experiments`, `image_feedback`) where relational querying matters.

---

## Migration Strategy (zero-downtime, reversible)

For each migrated JSON file:
1. **Backfill:** on startup (or a one-time `migrate_json_to_db()` command), read the JSON file, `upsert` into the DB table. Wrap in `_LOCK`. If JSON missing/corrupt, skip (DB stays authoritative).
2. **Dual-write:** app functions that previously wrote JSON now write DB *and* (temporarily) JSON, so a rollback to old code still works. Keep for one release cycle.
3. **Flip reads:** change loaders to read DB first; fall back to JSON only if DB empty. (Already the pattern for `release_status`.)
4. **Retire JSON:** after a soak period with no JSON writes detected, stop dual-writing and delete the JSON files. `git rm` them; add a guard that ignores stale files.

**Never destructive:** migrations are additive (new tables/columns) with `CREATE TABLE IF NOT EXISTS` and `SCHEMA_VERSION` bump. Backfill is idempotent (upsert by key). Old JSON is kept until step 4.

---

## Phased Task List (APPROVED SCOPE — narrow Phase 1)

### Phase 0 — Audit the workflow-correctness slice (one task)
- Task: For each of the 11 Phase-1 items below, confirm (a) whether a DB table already exists in `automation_db.py`, (b) which `app.py` `*_FILE` constant holds it, (c) the current reader/writer and whether it already dual-reads DB-then-JSON. Produce a `DB_MIGRATION_MAP.md` slice listing each item → table/JSON/status. Commit.

### Phase 1 — Workflow-correctness state: SQLite read-first + dual-write (DO NOT delete JSON)
Target state (the items that cause real workflow bugs):
1. `approval inbox cleared/completed items` → `approval_cleared` table
2. `post records` → `post_records` table
3. `chapter ledger` → `chapter_ledger` table
4. `release status` → `release_status` table
5. `release automation jobs` → `release_automation_jobs` table
6. `active chapter paths` → `*_FILE` (chapter-path-state.json) — GAP, add minimal table or kv
7. `daily promo path` → `*_FILE` — GAP, add minimal table or kv
8. `release upload path` → `*_FILE` / release automation — GAP if no table
9. `full YouTube path` → `youtube_posts` + `*_FILE` (youtube_daily_queue_status.json) — GAP if no table
10. `variant path` → `*_FILE` — GAP, add minimal table or kv
11. `YouTube daily status` → `*_FILE` (youtube_daily_queue_status.json) — GAP, add minimal table or kv

For each item:
- If a table exists: ensure the loader reads **DB first, JSON fallback only if missing**; ensure the writer **dual-writes** (DB + JSON) during soak.
- If no table: add a minimal purpose-built table (for relational state) OR a `state_snapshots` kv row (for pointer/cache state); backfill from JSON on startup; same read-first + dual-write.
- Verify with a unit test per item: write via DB → read back equal; DB-missing → JSON fallback.
- Commit per item (or per small group).

**Goal of Phase 1:** SQLite is the primary source of truth for workflow state; JSON remains as a mirror for debugging. This directly fixes stale approvals, wrong chapter jumps, skipped YouTube chapters, and "already done but still showing" bugs. **No JSON files deleted in Phase 1.**

### Phase 2 — Media / experiment tables (after Phase 1 is stable + regression-tested)
Story hooks (`media_jobs`), image lab, image feedback, YouTube drafts, content experiments. Purpose-built tables (`media_jobs`, `experiments`, `image_feedback`) + kv for the rest. Same read-first + dual-write + soak pattern. Only after Phase 1 shows no stale approval/chapter-path regressions.

### Phase 3 — Retire JSON (only after soak)
- Assert DB is source-of-truth for migrated keys; stop dual-writing JSON.
- `git rm` retired JSON files; `.gitignore` them.
- Full regression green with JSON gone.

### Phase 4 — Regression & live-ops safety
- Extend `tools/regression_check.py` with `check_db_source_of_truth()` asserting each migrated key resolves from DB.
- Vault note documenting the migration.

---

## Non-goals (explicitly excluded)
- **Do NOT move research briefs, vault notes, creative planning docs, or user-authored files into SQLite.** SQLite holds operational state only; the creative/document vault stays as files.
- **Do NOT create dozens of new tables.** Purpose-built tables only for relational workflow state; use the existing generic `state_snapshots`/kv pattern for low-risk settings or dashboard caches.
- **Do NOT delete JSON in Phase 1.** Keep mirrors for the soak period.

---

## Tests / Validation
- Unit: for each migrated loader, a test that writes via DB and reads back the same value; and a test that DB-missing falls back to JSON (during transition).
- Integration: `python tools/regression_check.py` (app_smoke + function_profile + core_regression) green after Phase 3.
- Live-ops: keep the running server on old code until Phase 1–2 soak; migrate on a branch; merge only after regression green. **Do not kill the Hermes runtime; do not rewrite history on a dirty tree.**

## Risks / Tradeoffs / Open Questions
- **Live-ops safety:** the running app writes some of these JSON files frequently (e.g. story-hook status, growth stats). Dual-write must be atomic enough that a crash mid-migration doesn't lose state. Mitigation: DB upsert is atomic; JSON fallback covers gaps.
- **Two DB writers:** the app and any cron/background jobs both touch `automation_state.db` — `_LOCK` (RLock) serializes; confirm no second un-guarded connection. Cron jobs must import `automation_db`, not write JSON.
- **`state_snapshots` overuse:** stuffing everything into one kv table is pragmatic but loses queryability. Only do this for genuinely unstructured state; use purpose-built tables (`media_jobs`, `experiments`) where rows are queried/filtered.
- **Backfill idempotency:** key collisions (same job_id in JSON + DB) must upsert, not duplicate.
- **Open question:** should `research_briefs` (Obsidian) also move to DB? Currently excluded (user-authored, vault-synced) — keep as files unless you decide otherwise.
- **Open question:** `post-records.json` vs `post_records` table — confirm the DB is already authoritative and delete the JSON (it may currently be the legacy mirror).

## Files likely to change
- `automation_db.py` — new tables, backfill + kv helpers, `SCHEMA_VERSION` bump.
- `app.py` — rewire ~50 JSON loaders/writers to DB-with-JSON-fallback; call `migrate_json_to_db()` at startup.
- `tools/regression_check.py` — add `check_db_source_of_truth()`.
- New: `DB_MIGRATION_MAP.md` (audit artifact), vault note.
- `git rm` retired `*.json` state files (after Phase 3).
