# Phase-3 JSON Retirement Boundary

This marker records the permanent boundary of the Phase-3 root-JSON
retirement migration for the Automation Tool.

## Boundary commit
`f7a3b50` — "Phase 3: quarantine retired JSON mirrors"

After this commit:
- SQLite (`automation_state.db`) is the **sole live persistence layer** for the
  retired Group A root-JSON state (the `state_snapshots` table + the normalized
  `release_status` table).
- The 11 retired root JSON mirrors are quarantined under
  `_trash-json/2026-07-23-phase3-retirement/` (gitignored, reversible via the
  manifest) with recovery metadata (SHA-256, size, mtimes, DB state key, DB
  payload hash / relational export hash, reason, commit id).
- Large snapshot payloads (analytics-lab, youtube-comment-queue, release_status)
  are DB-backed and lazy-loaded; API responses return typed SQLite references
  (`{"file": null, "storage": "sqlite", "resource": ..., "state_key": ...}`)
  instead of dead filesystem paths.
- Runtime reads/writes to retired mirrors are actively blocked
  (`storage/retired_state.py` guards in `release_state.write_json_atomic`,
  `promo_copy.read_json_safe`, and `database_state_files()` /
  `bootstrap_state_database_from_json()`).
- Startup cannot silently re-register or re-import the retired keys.

## Migration chain (clean, reviewable)
- `23e159b` bootstrap + repository fixes
- `b829f36` reader/writer repoint + lazy-load + typed API responses
- `de20557` enforcement + tests
- `f7a3b50` quarantine retired JSON mirrors  ← BOUNDARY

## Final backup
`migration-backups/phase3-final-20260723T122008.sqlite`
(Taken after verification-marker cleanup; `quick_check=ok`, `foreign_key_check=ok`.)

Pre-repoint backups are also retained under `migration-backups/`
(`phase3-pre-repoint-*.sqlite`) and a soak backup (`phase3-soak-*.sqlite`).

## Verification markers removed
`_soak_marker`, `_soak_marker2`, `_cold_marker` were stripped from
`state_snapshots[youtubeCommentQueue]`, `state_snapshots[youtubeEndScreenState]`,
and `release_status[GLOBAL]` after the soak/cold-start checks served their
purpose. Production payloads carry no verification residue.

## Excluded (not part of Phase-3 acceptance)
- `tests/test_promo_copy.py` `build_platform_posts` (3 asserts): caption/campaign
  drift — unrelated post-copy generation.
- `tests/test_release_state.py`: harness defect (`chapter_ledger.json` path);
  `release_state` itself is already SQLite-only.

See `.hermes/plans/2026-07-23_140000-root-json-db-conversion.md` for the full
plan and decision log.
