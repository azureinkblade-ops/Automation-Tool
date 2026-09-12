# EA-4D.4F-R12E-R6F Start-Store Schema Compatibility Remediation Complete

Date: 2026-08-28

## Final State

**EA-4D.4F-R12E-R6F: PASS / COMMITTED**

- R11 design: UNCHANGED / FROZEN.
- R12A: COMPLETE / COMMITTED.
- R12B: COMPLETE / COMMITTED.
- R12C: COMPLETE / COMMITTED.
- R12D: COMPLETE / COMMITTED.
- R12E-R6: FAIL / TERMINAL (unchanged).
- R12E-R6F: PASS / COMMITTED.
- Live Codex starts during R6F: 0.
- Push: NO.

## Terminal R6 Failure (Preserved)

- Invocation ID: `2878095abb0b500f5dc684eca7c8afe61f2f5e51d70442a7ce1c0c08477e5fe5`
- PID: 9432
- Definitive starts: 1 (permanent)
- Exit code: 2
- Failure boundary: POST-LAUNCH START-STORE SCHEMA COMPATIBILITY
- Original SQLite error: `sqlite3.OperationalError: no such column: runtime_binding_id`
- The v2 start-store schema lacked the v3 `runtime_binding_id` column needed by `ExecutionStartResult` persistence

## Root Cause

The frozen schema lineage is:
- `v2 = legitimate predecessor schema` (lacks runtime_binding/evidence columns)
- `v3 = EA-4D.4A current StartResult schema` (adds 5 runtime-binding/evidence fields)

The lifecycle defect was not that v2 itself is malformed. The defect was that production bootstrap behavior allowed current callers to encounter v2 without ensuring migration to v3. Specifically:
- New stores could be bootstrapped through an older schema path
- Callers had to remember an explicit `migrate_to_v3()`
- Valid v3 reopening behavior did not match current lifecycle needs
- Late failure occurred only when StartResult persistence attempted to use the v3 column set

## Remediation

### Production Code Changes

`tools/hermes_core/sqlite_execution_start_store.py`:
1. **Singleton-enforced schema_version table**: Changed from `(version INTEGER)` to `(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER)` to prevent concurrent bootstrap races
2. **Idempotent bootstrap**: `_bootstrap_latest_schema()` now uses `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` + checks current version before migrating
3. **Lenient schema version reads**: `_schema_version()` accepts both old (version-only) and new (singleton-enforced) shapes
4. **Helper function**: `_advance_schema_version()` handles both schema shapes for version advancement
5. **Migration idempotency**: `_migrate_v2_to_v3()` returns early if already at v3 (handles concurrent migration races)
6. **Concurrency safety**: `_initialize()` catches `sqlite3.OperationalError` during bootstrap (another thread may have bootstrapped first)

### Test Changes

`tests/hermes_core/test_start_store_schema_compatibility.py` (new):
- `test_fresh_database_is_complete_current_schema` — fresh store reaches v3
- `test_fresh_persistence_restart_and_replay` — persistence + restart + replay
- `test_exact_empty_v2_shape_auto_migrates_and_persists` — v2 → v3 migration
- `test_v1_auto_migrates_to_current_and_persists` — v1 → v2 → v3 migration
- `test_populated_v2_refuses_without_mutation` — populated v2 refuses (fail-closed)
- `test_current_version_with_old_result_shape_fails_closed` — malformed v3 rejected
- `test_current_version_with_wrong_column_contract_fails_closed` — wrong column type rejected
- `test_post_open_shape_tamper_is_typed_before_insert` — tamper caught before persistence
- `test_fresh_post_launch_reconciliation_crosses_r6_failure_boundary` — post-launch simulation
- `test_partial_existing_database_without_version_fails_closed` — no version table rejected

`tests/hermes_core/test_execution_start_result_persistence.py` (modified):
- Updated to verify v3 schema fields

`tests/hermes_core/test_execution_start_store_migration.py` (modified):
- Updated to handle both old and new schema_version shapes

## Verification Evidence

| Gate | Count |
|---|---|
| R6F focused | **10 passed** |
| StartResult persistence | **39 passed** |
| Start-store migration | **11 passed** |
| Full Hermes Core | **1,335 passed, 104 subtests** |

## Schema Lifecycle Behavior Proof

### Fresh database
Production bootstrap results in `CURRENT_SCHEMA_VERSION=3` and complete v3 `execution_start_results` shape. `runtime_binding_id` and every other frozen v3 runtime/evidence field exists.

### Existing v1
Supported migration: `v1 → v2 → v3`. Final state is valid v3.

### Existing v2
Supported migration: `v2 → v3`. Final state is valid v3.

### Existing valid v3
Reopen without destructive migration. Validate schema shape. Proceed normally.

### Malformed claimed-v3
If version says v3 but physical schema is missing required fields: `FAIL CLOSED`. No late `sqlite3.OperationalError`.

## Post-Launch Non-Live Simulation

The authorized deterministic non-live simulation of the boundary that failed after Codex returned a valid result establishes:

`VALIDATED CODEX-LIKE RESULT`
`-> POST-LAUNCH RECONCILIATION`
`-> EXECUTION START RESULT PERSISTENCE`
`-> SUCCESS`

on a correctly created/migrated current database.

## Capability Audit

- LIVE_CODEX_STARTS_DURING_R6F=0
- GENERIC_SHELL=NO
- ARBITRARY_EXECUTABLE=NO
- KILO=NO
- BROWSER=NO
- MCP=NO
- NETWORK_EXPANSION=NO
- SCHEDULER=NO
- GPU=NO
- COMFYUI=NO
- STUDIO_BIBLE_IMAGE_PIPELINE=NO
- RHR=NO

## Live Accounting (Permanent)

Original R12E:
- `AUTHORIZED=1`
- `DEFINITIVE_STARTS=1`
- `REMAINING=0`

R12E-R6F:
- `LIVE_STARTS=0`

## Governance Disposition

```
EA-4D.4F-R12E-R6F: PASS / COMMITTED
START-STORE FRESH CREATION: V3 QUALIFIED
V1 -> V3 MIGRATION: PASS
V2 -> V3 MIGRATION: PASS
VALID V3 REOPEN: PASS
MALFORMED V3: FAIL-CLOSED
EXECUTION_START_RESULTS.RUNTIME_BINDING_ID: VERIFIED
POST-LAUNCH PERSISTENCE SIMULATION: PASS
R6 TERMINAL STATUS: UNCHANGED
R6 RETRY: NOT AUTHORIZED
LIVE CODEX STARTS DURING R6F: 0
PUSH: NO
```
