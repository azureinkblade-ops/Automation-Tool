# SC-8: Database Health, Backup & Recovery

SC-8 makes the Phase-3 single-source-of-truth durable: SQLite is protected by
an automated health gate, rotating online backups, and a documented, reversible
recovery path. **All tooling lives in `tools/` and `storage/` — `app.py` is not
modified** (keeps the Phase-C `app.py` lane ownership clean).

## Tools (all read/restore-safe, no app.py edits)

| Tool | Purpose |
|------|---------|
| `tools/db_health_gate.py` | CI gate: DB health + `integrity_check` + Phase-3 retirement enforcement. Exit 0/1/2. `--enforce-no-mirrors`, `--json`, `--root`. |
| `tools/db_backup_rotate.py` | Rotating online backup via the SQLite backup API. Manifest + retention (`--keep N`, `--max-age-days D`). |
| `tools/db_restore.py` | Safe, reversible restore: refuses if server `:8765` live or live DB unopenable; auto-snapshots current DB first; restores via in-place backup API; re-runs health. |

Backups live in `migration-backups/rotating/` (manifest `manifest.json`).
Pre-restore safety snapshots go to `migration-backups/pre-restore/`.

## Scheduling (recommended)

Run `db_health_gate.py --enforce-no-mirrors` and `db_backup_rotate.py` on a
schedule (cron / Hermes cron job). Suggested cadence:
- Health gate: every 15–30 min (alert on non-zero exit).
- Rotating backup: hourly, `keep=20`, `max-age-days=30`.

A Hermes cron job can own these (no app.py touch). See "Wiring" below.

## Failure response

| Symptom | Action |
|---------|--------|
| `db_health_gate` exits 1 | Inspect output. If `retired mirrors present`, investigate which retired root JSON reappeared (code path re-introduced a write) before fixing. If integrity/health fails, proceed to restore. |
| `integrity_check != ok` | Do NOT write. Restore from the most recent good backup (below). |
| App cannot start / data missing | Restore from backup (below). |
| Accidental bad write | Restore from the pre-write rotating backup; the `pre-restore` snapshot makes any restore itself reversible. |

## Restore procedure (recovery runbook)

1. **Stop the app server** (port `:8765`). The restore tool refuses if it is live.
   Other readers (e.g. a Hermes/Codex worker holding a connection) are tolerated
   by the in-place backup restore, but for maximum safety stop them too.
   NEVER blanket-kill Python — identify the holding process by PID and stop only
   that one.
2. **List available backups**:
   `python tools/db_restore.py --list`
3. **Restore** (auto-snapshots the current live DB first, so it is reversible):
   `python tools/db_restore.py --source migration-backups/rotating/<file>.sqlite`
   - Refuses if `:8765` is live or the live DB cannot be opened (held by another
     process). Refuses if the chosen backup fails `integrity_check`.
   - Writes the backup's content into `automation_state.db` in place (no file
     rename; avoids Windows WAL sidecar issues).
   - Re-runs the health gate; prints `RESTORE OK (reversible via the
     pre-restore snapshot)`.
4. **Verify**: `python tools/db_health_gate.py --enforce-no-mirrors` → must pass.
5. **Restart the app server.**

## Reversibility

Every restore first writes `migration-backups/pre-restore/pre-restore-<ts>.sqlite`
(the pre-restore state). If a restore proves wrong, restore *from that snapshot*.
The rotating backups themselves are pruned by count + age, so promote a backup
you must keep longer by copying it out of `migration-backups/rotating/`.

## Wiring to a scheduled job (optional)

A Hermes cron job can run, e.g.:
```
python tools/db_health_gate.py --enforce-no-mirrors && python tools/db_backup_rotate.py --keep 20 --max-age-days 30
```
This keeps the SQLite source of truth verified and backed up without human
intervention and without touching `app.py`.

## Tests

`tests/test_db_backup_restore.py` covers (all on isolated temp DBs):
- backup rotation + retention pruning (count + age),
- health gate pass/fail/JSON,
- restore round-trip (mutate → restore → reverted + health ok),
- restore refusal when the chosen backup fails integrity,
- Phase-3 no-mirror enforcement via the health gate.
