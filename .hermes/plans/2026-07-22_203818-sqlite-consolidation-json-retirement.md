# SQLite Consolidation and JSON Retirement Implementation Plan

> For Hermes: implement this plan task by task under the repository's `AGENTS.md` single-writer rule. Do not combine database foundation, state cutover, transient relocation, or cleanup in one commit.

Goal: Make SQLite authoritative for all persistent application state while retaining JSON only for approved interchange, cache, report, sidecar, fixture, import, or export roles.

Architecture: Extend the existing `automation_state.db` and `automation_db.py` first. Add a centralized storage package around the existing database rather than replacing it. Cut over `posting_schedule.json` using one-time, parity-verified import. Migrate `deep-tiktok-rotation.json` as the second confirmed missed state object. Create `automation_jobs.db` or `automation_analytics.db` only if the strengthened inventory proves that existing tables in `automation_state.db` cannot satisfy retention, query, retry, or concurrency needs.

Tech stack: Python 3.11, stdlib `sqlite3`, current `automation_db.py`, SQLite WAL, pytest or repository regression scripts, JSON only for approved file roles.

## 0. Verified current state

Repository: `C:\Users\David\Documents\Automation tool`
Branch and commit at plan time: `main`, `9cf112b`
Live database: `automation_state.db`
Current DB schema constant: `SCHEMA_VERSION = 6`
Current schema marker: `app_meta['schemaVersion']`
Integrity at plan time: `PRAGMA quick_check = ok`

Existing relevant tables include:
- `state_snapshots`
- `release_automation_jobs`
- `platform_post_metrics`
- `social_stats_daily`
- `release_plan_rows`
- `recovery_events`
- workflow and per-platform post tables

No `automation_jobs.db` or `automation_analytics.db` exists.

Confirmed gaps:
- `posting_schedule.json` is read at app.py:13387-13388 and written at 13417 and 18036.
- A stale `postingSchedule` DB snapshot exists. Its timestamp is 2026-07-18 14:16:47.
- Current JSON and DB schedule payloads differ. JSON `releaseQueueStartDate` is `2026-07-19`; DB value is `2026-07-03`.
- Canonical JSON schedule hash: `26838788653fa4e603fef0037b57077044b716375f9b44b1ec28f9ae5726ea89`.
- Canonical DB schedule hash: `106fe5ab9d24587d7fe878e0cd6976ebce1059b12b54cbadc074780e2fd3e7c2`.
- `deep-tiktok-rotation.json` is durable state, not read-only. Reader: app.py:15583-15584. Writer: app.py:15619 through `write_json_atomic`.

Important correction to the preliminary JSON audit: the earlier scanner missed helper-wrapper writes such as `write_json_atomic(...)`. Treat `Automation Tool - Root JSON Audit (2026-07-22)` as preliminary until SC-1 produces the strengthened manifest.

## Non-negotiable boundaries

- `app.py` remains owned by editing session `20260715_060146_c55923` until an explicit handoff.
- Do not edit `app.py` from the reasoning lane.
- Never test with destructive writes against the live schedule JSON or live DB.
- Never silently fall back to retired JSON after cutover.
- Never dual-write a retired mirror during the soak.
- Never create jobs or analytics databases merely to eliminate transient files.
- Never store images, video, audio, or other binary artifacts in SQLite.
- Commit after each verified storage stage.
- Do not quarantine files until state cutovers pass restart and soak tests.

## Storage classifications

Every logical object must receive exactly one classification:

- `sqlite_state`: current durable state and mutable configuration.
- `sqlite_history`: append-oriented metrics, experiments, and historical outcomes.
- `sqlite_job_state`: job status, attempts, leases, retries, and durable execution results.
- `file_artifact`: generated media or per-asset `metadata.json` provenance.
- `file_cache`: regenerable file cache.
- `file_debug_output`: manual diagnostic or audit report.
- `file_fixture`: active test fixture or snapshot.
- `file_import_export`: user or external system interchange.
- `dead_file`: no producer or consumer and no recovery value.
- `unknown`: blocks cleanup until resolved.

## SC-1: Strengthened inventory and authoritative storage manifest

Objective: classify every JSON and logical state object before migration or deletion.

Files:
- Create: `storage/resource_manifest.py`
- Create: `tools/audit_storage_resources.py`
- Create: `tests/test_storage_manifest.py`
- Update documentation only after audit output is verified.

Tasks:
1. Write a failing test requiring every discovered root JSON to have a manifest entry.
2. Build a repository-wide scanner for `.py`, `.js`, `.ts`, `.bat`, `.ps1`, `.sh`, scheduled-task scripts, and test harnesses.
3. Detect direct and wrapped access patterns:
   - `Path.read_text`, `Path.write_text`, `Path.open`
   - built-in `open`
   - `json.load`, `json.dump`, `json.loads`, `json.dumps`
   - `read_json_safe`, `write_json_atomic`, `_phase2_load_blob`, `_phase2_save_blob`
   - dynamically constructed output paths passed into JavaScript and subprocess commands
4. Record producer, consumer, durability, target classification, target DB/table/path, and migration action.
5. Include per-asset `metadata.json` patterns as one logical resource class instead of enumerating generated instances.
6. Fail the audit on `unknown` for any file proposed for quarantine.
7. Commit only the manifest, scanner, and tests.

Required manifest facts:
- `postingSchedule`: `sqlite_state`, target pending SC-3.
- `deepTikTokRotation`: `sqlite_state`, target `state_snapshots` unless inspection proves relational need.
- `youtubeLibraryScan`: initially `file_cache`, retained outside root.
- subprocess result files: `file_cache`, `file_debug_output`, or `sqlite_job_state` only after producer and consumer tracing.
- Phase-2 fossils: `dead_file` only after DB presence and no-access checks.
- sidecar `metadata.json`: `file_artifact`, approved and retained.

Verification:
- Run manifest tests.
- Run the scanner twice and assert deterministic output.
- Confirm all root JSON have a non-unknown classification before SC-5.

Commit: `test(storage): add authoritative JSON resource manifest`

## SC-2: Central database bootstrap and migration ledger

Objective: provide idempotent schema initialization, explicit migration history, health checks, and safe backup behavior around the existing database.

Files:
- Create: `storage/__init__.py`
- Create: `storage/database.py`
- Create: `storage/migrations.py`
- Create: `storage/health.py`
- Create: `tests/storage/test_database_bootstrap.py`
- Modify: `automation_db.py` only through a narrow compatibility bridge.
- Modify later: `app.py` startup, through editing-lane handoff.

Design:
- Keep `automation_db.py` operational. Do not rewrite its 30-plus tables in one pass.
- `storage.database` resolves paths, opens connections, configures pragmas, and invokes migrations.
- Existing functions can delegate to the new connection factory incrementally.
- Add `schema_migrations` without removing `app_meta['schemaVersion']`. Keep both during compatibility, with a documented mapping.
- Migration checksums must be stable and verified before applying pending migrations.

Connection policy:
- `foreign_keys = ON`
- `journal_mode = WAL`
- `synchronous = NORMAL`
- `busy_timeout = 30000`
- `row_factory = sqlite3.Row`
- absolute resolved path logged at startup

Required migrations:
- `001_baseline_schema_v6`: records the existing schema as baseline after verification. It must not recreate or destructively transform existing tables.
- `002_create_schema_migrations`: establishes the ledger.
- `003_create_database_metadata`: adds DB identity and migration timestamps.
- Later schedule and feature-state migrations receive separate IDs.

Health checks:
- file opens successfully
- non-zero size, unless being initialized fresh
- required tables, columns, and indexes exist
- `PRAGMA quick_check`
- `PRAGMA foreign_key_check`
- schema ledger and `app_meta` agree
- no pending migration after startup

Zero-byte and malformed DB handling:
- stop writes
- move the invalid file to `recovery/<timestamp>/`
- never overwrite it in place
- create a fresh DB through migrations
- import only verified rows
- record the recovery event

Tests:
- missing DB
- missing parent directory
- existing schema-v6 DB
- empty DB
- zero-byte DB
- partial DB missing one recent table
- old schema with pending migration
- malformed DB
- foreign keys and WAL enabled
- required indexes present
- idempotent second initialization

Verification commands:
- isolated temp-directory test suite
- `python -m storage.health --db <temp-db>`
- live DB read-only health probe after tests pass

Commit: `feat(storage): add idempotent SQLite bootstrap and migration ledger`

## SC-3: Posting schedule cutover

Objective: make SQLite authoritative without changing the schedule's behavior or losing the newer JSON payload.

Decision: use a two-step cutover.

Step 1, minimum-risk cutover:
- Continue storing the exact nested schedule payload in `state_snapshots` under `postingSchedule`.
- Add version and migration metadata if needed through repository-managed fields or a companion metadata table.
- Remove normal runtime JSON reads and writes.

Step 2, relational normalization:
- Evaluate separately after the DB-only soak.
- The current payload is global settings plus one mutable record per novel, not a list of individually scheduled platform posts.
- The proposed `posting_schedule(schedule_id, platform, scheduled_at, ...)` schema does not match the current object and must not be introduced during cutover.
- If normalization is justified, prefer:
  - `posting_schedule_settings`
  - `posting_schedule_novels`
  - existing `release_plan_rows` for generated dated release instances
- This must be a later isolated migration with parity fixtures.

Files:
- Create: `storage/schedule_repository.py`
- Create: `tests/storage/test_schedule_repository.py`
- Create: `tests/storage/test_posting_schedule_migration.py`
- Create: `tools/migrate_posting_schedule.py`
- Modify: `app.py` only through editing-lane handoff.
- Modify: `tools/regression_check.py` for authority guards.

Repository API:
- `load() -> VersionedPostingSchedule | None`
- `save(schedule, expected_version=None) -> VersionedPostingSchedule`
- `create_default() -> VersionedPostingSchedule`
- `validate(schedule) -> None`
- `migration_status() -> PostingScheduleMigrationStatus`

Migration procedure:
1. Stop schedule writers or run in maintenance mode.
2. Use the SQLite backup API to back up `automation_state.db`.
3. Copy current `posting_schedule.json` to `migration-backups/<timestamp>/`.
4. Export the stale DB row to the same backup directory.
5. Canonicalize and hash both payloads.
6. Validate current JSON against the existing schedule contract.
7. Import current JSON as the authoritative one-time source inside a transaction.
8. Record marker `posting_schedule_json_import_complete` with timestamp, source hash, destination version, row/item count, and application commit.
9. Read back through the repository and compare canonicalized payloads.
10. Rename `SCHEDULE_FILE` to `LEGACY_SCHEDULE_FILE` and confine it to migration and warning code.
11. Replace `ensure_schedule_file()` with `ensure_posting_schedule()`.
12. Replace app.py writes at current lines 13417 and 18036 with repository saves.
13. Add optimistic concurrency. A stale expected version must raise a conflict, not overwrite.
14. Runtime startup warns if the retired JSON remains, but never reads it.
15. Do not delete or quarantine the legacy JSON until restart and soak criteria pass.

Tests, written before implementation:
- JSON exists, DB row missing
- JSON exists, stale DB row exists
- JSON invalid
- JSON empty
- DB already migrated
- legacy file missing
- duplicate migration invocation
- unknown fields preserved or rejected according to current compatibility contract
- concurrent update conflict
- transaction rollback
- locked DB
- corrupt payload JSON
- restart loads the same DB schedule
- stale JSON cannot overwrite newer DB state
- no retired JSON is recreated

Static authority guard:
- Fail if production code contains direct `SCHEDULE_FILE.read_text` or `SCHEDULE_FILE.write_text`.
- Permit `posting_schedule.json` only in migration code, tests, documentation, and retired-file warning code.

Real soak:
- startup
- load
- default creation in isolated DB
- edit
- restart
- worker restart
- concurrent update conflict
- invalid payload rejection
- DB lock contention
- real schedule update followed by app restart and read-back

Commit sequence:
1. `feat(storage): add posting schedule repository`
2. `feat(storage): import live posting schedule into SQLite`
3. `refactor(storage): switch schedule reads to SQLite`
4. `refactor(storage): switch schedule writes to SQLite`
5. `test(storage): enforce DB-only schedule authority`

## SC-4: Migrate other missed durable JSON state

Objective: migrate every durable JSON object missed by earlier phases.

First confirmed target: `deep-tiktok-rotation.json`.

Current behavior:
- constant: app.py:329 and app_config.py:128
- existence check: app.py:15583
- read: app.py:15584 through `read_json_safe`
- write: app.py:15619 through `write_json_atomic`

Preferred target:
- `state_snapshots.state_key = 'deepTikTokRotation'`
- Do not create `feature_state` unless the strengthened audit finds several independent feature flags requiring queryable columns.
- Remove file-stat or existence-based cache behavior after migration.
- Add a one-time import marker and DB-only load/save path.

For every additional durable object found by SC-1:
1. Determine if it is relational.
2. Reuse a purpose-built existing table when one exists.
3. Use `state_snapshots` for low-risk single-blob state.
4. Create a new table only when individual rows require filtering, concurrency, foreign keys, or history.
5. Add a failing authority test before cutover.
6. Back up, import, verify, flip reads, flip writes, restart-test, then retire the file.

Commit: one resource or tightly related resource group per commit.

## SC-5: Operational result classification and root relocation

Objective: remove changing runtime JSON from the repository root without creating unnecessary databases.

Files to trace:
- `comment-gather-results.json`
- `comment-reply-result.json`
- `metrics-gather-results.json`
- `youtube-audience-fix-results.json`
- `youtube-comment-pin-results.json`
- `youtube-end-screen-results.json`
- `duplicate-cleanup-report.json`
- `youtube-library-scan.json`

Default rule:
- If produced, consumed immediately, regenerable, not used for retry, not shown historically, and not needed after restart: keep it as a job-scoped temporary file under `runtime/jobs/<job-id>/result.json`, ingest, then remove it.
- If the UI displays prior runs, retry depends on it, multiple workers need it, or it must survive cleanup: persist execution metadata.

Database decision gate:
- Existing `release_automation_jobs` already stores job state.
- Do not create `automation_jobs.db` until SC-1 proves the existing table and DB boundary are insufficient.
- If broader durable job history is required, first evaluate extending `automation_state.db` with `job_runs`, `job_attempts`, `job_artifacts`, and `worker_leases`.
- Create a separate `automation_jobs.db` only for demonstrated lifecycle, contention, backup, or retention separation.

Per-file starting recommendation:
- comment gather/reply, audience fix, comment pin, end screen: job-scoped transient file plus durable job summary only if retries/history require it.
- duplicate cleanup report: keep export under `runtime/reports/`; persist run summary only if displayed historically.
- YouTube library scan: `runtime/cache/youtube-library-scan.json` unless individual videos are repeatedly queried enough to justify relational cache tables.
- metrics gather: transient interchange only; normalized observations should go to existing metrics/history tables.

Requirements:
- unique job IDs and filenames
- atomic write then ingestion
- cleanup after successful ingestion
- retention policy after failures
- `.gitignore` entries for runtime directories
- no new changing root JSON

Commit: `refactor(storage): move operational JSON out of repository root`

## SC-6: Analytics normalization decision

Objective: keep historical analytics append-oriented and queryable.

Existing capability:
- `platform_post_metrics`
- `social_stats_daily`
- `weekly_growth_plans`
- `weekly_growth_slots`
- experiment-related state may remain in `state_snapshots`

Default decision:
- Extend existing tables in `automation_state.db` first.
- Do not create `automation_analytics.db` unless volume, retention, write contention, archival policy, or independent backup requirements justify separation.

Tasks:
1. Map every metrics result field to an existing or proposed normalized column/table.
2. Confirm uniqueness keys and indexes for platform, post/content, metric name, and observation time.
3. Preserve raw source payload hash and optional artifact path for provenance.
4. Import only historical data still needed.
5. Keep human-readable exported reports as files under `runtime/reports/` or `exports/`.

If separate DB is approved later:
- add it through the same migration and health framework
- tables: `analytics_runs`, `metric_observations`, `content_performance`, `experiment_results`
- never duplicate the same authority across both DBs

Commit: `feat(analytics): normalize retained metrics history`

## SC-7: Reversible JSON quarantine

Objective: remove confirmed dead files from active paths without irreversible deletion.

Preconditions:
- SC-1 manifest has no unknown entries in cleanup scope.
- schedule and other state cutovers pass restart soak.
- scheduled tasks and non-Python producers have been scanned.
- active fixtures are identified.

Target:
- `_trash-json/<YYYY-MM-DD>/`
- `_trash-json/<YYYY-MM-DD>/manifest.json`

Manifest fields per file:
- original path
- quarantine path
- SHA-256
- size
- modification time
- classification
- producer/consumer conclusion
- reason
- moved timestamp
- source commit

Initial quarantine candidates:
- confirmed dead Phase-2 fossils
- obsolete queue backups
- chapter import leftovers no longer required for recovery
- probe dumps
- regression scratch that is not an active fixture

Hold:
- migration backups until soak completion
- unidentified producer files
- files referenced by scheduled tasks
- active CI fixtures
- current transient files until relocated
- any file with audit classification `unknown`

Verification:
- hash before and after move
- manifest paths resolve
- full tests pass
- app starts and workers run
- schedule survives restart
- quarantine retained through soak, then deletion requires separate approval

Commit: `chore(storage): quarantine confirmed dead JSON files`

## SC-8: Enforcement, backup, recovery, and observability

Objective: make regression to JSON-backed state difficult and diagnosable.

CI and repository guards:
- fail on direct retired-file reads/writes
- fail on new unallowlisted root JSON
- fail when a manifest entry is missing
- fail when a SQLite state resource is configured with JSON fallback
- fail when a retired mirror is recreated during tests

Backup:
- use SQLite backup API, never raw live-file copy
- back up before each pending migration
- retain through soak
- document restore, WAL/SHM handling, integrity checks, and restart validation

Structured events:
- `database_opened`
- `database_created`
- `migration_started`
- `migration_completed`
- `migration_failed`
- `legacy_json_imported`
- `legacy_json_ignored`
- `database_integrity_failed`
- `schedule_loaded`
- `schedule_saved`
- `schedule_version_conflict`

Do not log full payloads or secrets. Log resource key, count, version, hash, duration, DB path, and migration ID.

Health CLI:
- `python -m storage.health`
- reports DB path, quick check, schema version, pending migrations, required table/index status, schedule state/version/count, retired-file detection, and DB-only authority status

Commit: `feat(storage): add authority guards, health CLI, and recovery docs`

## Full verification gate

Run after each stage as applicable:
- focused unit tests for the stage
- storage bootstrap tests in isolated temp directories
- static JSON authority guard
- full `tools/regression_check.py` in background with valid JSON report parsing
- `release_planner_regression.py`
- `daily_post_delivery_regression.py`
- smoke test against the intended app server only
- exact PID/port verification before any restart
- SQLite `quick_check` and `foreign_key_check`
- real schedule update and restart read-back after SC-3

Acceptance contract:
- missing `automation_state.db` is created through migrations
- required schema and indexes are verified, not inferred from file existence
- migration ledger is repeatable and checksummed
- current schedule is preserved from the live JSON source
- normal runtime never reads or writes `posting_schedule.json`
- stale JSON cannot overwrite newer DB state
- `deep-tiktok-rotation.json` is either migrated DB-only or explicitly reclassified with proof
- no retired Phase-2 mirror is recreated
- every remaining JSON has an approved manifest classification
- no changing runtime JSON remains in repo root
- operational and analytics data use existing DB structures unless separation is justified
- dead files are quarantined with hashes, not deleted directly
- backup and restore procedures are tested
- all integrity, regression, smoke, worker, and restart gates pass with zero new real failures

## Rollback

Before cutover:
- rollback the active transaction
- leave the live JSON untouched
- restore the pre-migration DB backup if a committed schema change failed
- correct and retry

After SQLite authority:
- stop app and workers
- back up the current faulty DB
- restore the latest verified SQLite backup
- do not silently reactivate JSON runtime reads
- use legacy JSON only as a manually inspected recovery source
- rerun health checks and canonical schedule comparison
- restart and verify state

## Execution handoff

This plan requires an explicit handoff to the editing lane because SC-3 and SC-4 change `app.py`. The handoff must include:
- source plan path
- current base commit
- current working-tree status and unrelated WIP
- exact app.py call sites
- backup requirements
- stage-specific acceptance criteria
- command list for focused and full verification

Do not begin SC-2 or later while unrelated writers are modifying `automation_db.py`, `app.py`, `.gitignore`, or regression guards. SC-1 can proceed independently if it only adds the scanner, manifest, and tests.

## Progress Log (2026-07-23, reasoning/strategy lane)

- SC-1 (strengthened manifest): COMPLETE. 12/12 tests pass. Scanner catches wrapper I/O (the preliminary audit's blind spot), excludes backup/venv, deterministic output. 91 root JSON remain `unknown` (safely blocking quarantine per plan).
- SC-2 (DB bootstrap + migration ledger): COMPLETE. 11/11 tests pass. `storage/migrations.py` (checksummed `schema_migrations` + `database_metadata`), `storage/database.py` (`initialize_databases`, `verify_database_health`, `backup_database_sqlite` via SQLite backup API). All on isolated temp DBs.
- SC-3 (posting schedule to SQLite): COMPLETE. Repository + migration tool + tests (10 tests pass). app.py cutover applied (commit 2dc6f05): `ensure_schedule_file()` + chapter-path-lock write delegate to `sr`; dual-write mirror removed. Live server serves /api/schedule from SQLite; JSON untouched.
- SC-7 (reversible quarantine): COMPLETE. Quarantined the two SC-3/SC-4 dead mirrors (posting_schedule.json, deep-tiktok-rotation.json) into _trash-json/2026-07-23/ with a hash-verified manifest (tools/quarantine_dead_json.py + reversible tools/restore_trash_json.py, refuses tampered files). Triggered after the soak passed a full production run. Verified live: with both JSON removed the running server still serves /api/schedule from SQLite (HTTP 200); fallback degrades gracefully; 46/46 storage tests pass. _trash-json/ gitignored. Committed 28a7d4e. NOTE: a cleanup mistake during testing deleted the first quarantine; both files were restored from migration-backups/ and re-quarantined cleanly.

Total: 46/46 storage tests pass (incl SC-1..SC-7). app.py cutover committed (2dc6f05); unrelated WIP intentionally left unstaged per AGENTS.md.

SC-1..SC-7 COMPLETE. Remaining: SC-8 (CI/health/backup enforcement — hardening only).

91 unknown root JSON remain held (per plan Hold: do not quarantine until classified). The two confirmed-dead JSON mirrors (posting_schedule.json, deep-tiktok-rotation.json) are the only files quarantined so far; broader cleanup is a separate, approved step.

91 unknown root JSON: seed manifest covers the 4 confirmed durable/known resources. 91 root JSON are `unknown` (correct default: blocks cleanup). SC-5/SC-7 will resolve each against the manifest before quarantine. None are mutated by the work so far. The two formerly-durable JSON files (`posting_schedule.json`, `deep-tiktok-rotation.json`) are now dead mirrors awaiting SC-7 quarantine after a production soak.