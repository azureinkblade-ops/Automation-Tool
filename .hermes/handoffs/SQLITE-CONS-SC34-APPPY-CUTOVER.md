---
type: handoff
from: reasoning/strategy session
to: editing lane (app.py owner)
subject: SC-3 / SC-4 app.py call-site rewiring (posting schedule + deep-tiktok rotation to SQLite)
status: complete
prerequisite_commit: 9cf112b
completed_commit: 2dc6f05 (2026-07-23)
---

# SC-3 / SC-4 app.py cutover handoff

The repositories, migration tools, and behavioral tests for SC-1 through SC-4
are complete and verified (39/39 tests pass) WITHOUT modifying app.py. This
handoff covers the only remaining step for SC-3 and SC-4: rewiring the live
app.py call sites from JSON files to the new SQLite repositories.

## What is already done (no app.py edit needed)
- `storage/schedule_repository.py` — posting schedule in `state_snapshots.postingSchedule` + version.
- `storage/feature_state_repository.py` — deep-tiktok rotation in `state_snapshots.deepTikTokRotation` + version.
- `tools/migrate_posting_schedule.py`, `tools/migrate_deep_tiktok_rotation.py` — one-time JSON→DB import (idempotent, backs up DB + JSON + stale row).
- `storage/database.py` (`initialize_databases`, `verify_database_health`, `backup_database_sqlite`) and `storage/migrations.py` (checksummed ledger).
- Tests: `tests/test_storage_*.py` (39 passing).

## SC-3 app.py edits (posting_schedule.json)
Replace file I/O in:
- `ensure_schedule_file()` reads at app.py:13387-13388 (SCHEDULE_FILE.read_text).
- writes at app.py:13417 and app.py:18036.
- blob registration at app.py:3076 (("postingSchedule", SCHEDULE_FILE)).

New behavior:
1. At startup, run `storage.database.initialize_databases(root)` once (idempotent; safe to call every boot).
2. `ensure_schedule_file()` should load via `sr.load(root)`; if missing, create default via `sr.create_default()` and `sr.save(root, ...)`.
3. On schedule mutation, replace `SCHEDULE_FILE.write_text(...)` with `sr.save(root, payload)`.
4. The JSON file becomes a dead mirror; do NOT delete in this step (SC-7 retires it after restart soak). Keep a runtime guard so a stale JSON on disk is ignored once the DB row exists.

## SC-4 app.py edits (deep-tiktok-rotation.json)
Replace:
- read at app.py:15583-15584 (`DEEP_TIKTOK_ROTATION_FILE.exists()` + `read_json_safe`).
- write at app.py:15619 (`write_json_atomic`).

New behavior:
1. `load_deep_tiktok_rotation()` returns `fsr.load(root).payload` after applying the existing chapter-ledger merge (that merge stays in app.py; only the JSON read/write moves to the repo).
2. `save_deep_tiktok_rotation(data)` calls `fsr.save(root, data)` instead of `write_json_atomic`.
3. Remove the `fresh_state` file-existence check; freshness is now "DB row missing" (repo returns default payload with version 0 when absent).

## Verification before declaring done
- Run `tests/run_sc1_tests.py` -> 39 passing (no regression). [DONE]
- Start the app once; confirm `sr.load(root)` returns the migrated schedule and the app behaves (no 500s on schedule endpoints). [DONE: /api/schedule 200, HTTP 200 on :8765]
- Confirm no new `posting_schedule.json` / `deep-tiktok-rotation.json` writes occur (grep app.py for those constants after edit). [DONE: only fallback-helper writes remain; live mtimes unchanged]

## Verification evidence (2026-07-23, commit 2dc6f05)
- `import app` OK; `ensure_schedule_file()` returns SQLite data (releaseQueueStartDate 2026-07-19, 4 novels).
- `load/save_deep_tiktok_rotation` round-trips via SQLite (cycle 6->7->6).
- Legacy JSON mtimes unchanged after live-path calls.
- Live server restart: HTTP 200; `/api/schedule` serves SQLite data; JSON files untouched.
- 39/39 storage tests pass.
- Legacy JSON files are now dead mirrors; SC-7 quarantine pending after soak.

## Rollback
The migration tools wrote backups under `migration-backups/<ts>/`. To roll back,
restore `automation_state.db` from the latest backup and re-enable the JSON path.
Because the cutover is flag-free but additive (DB is the new source, JSON left
untouched), rollback is: revert this commit + restore DB backup.

## Notes
- Do NOT run the migration tools against the live DB as part of this commit unless
  David approves the cutover. The tools are ready; execution is a separate, explicit step.
- Keep edits isolated to these call sites. No formatting or unrelated cleanup.
