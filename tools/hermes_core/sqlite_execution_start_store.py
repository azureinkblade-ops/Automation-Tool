"""EA-4D.2: Execution-start persistence + exclusive start admission (STORE ONLY).

This module is the durable layer for the EA-4D execution-start boundary, scoped
to EXACTLY the frozen design's EA-4D.2 slice:

    ROUTE_SELECTED
        |
        v
    START_RESERVED
        |
        X STOP            (no launch attempt orchestration / invocation)

It does NOT:
* perform any worker invocation, subprocess, process creation, or network call;
* orchestrate or persist a launch *attempt* as part of a workflow -- launch-attempt
  persistence is defined here ONLY for schema completeness and is never reached
  by any EA-4D.2 code path (the store exposes no method that writes it);
* implement a runtime-binding resolver (EA-4D.3) or any external adapter;
* transition into EXECUTING (that is a later EA-4D slice after positive ack).

The store is a SEPARATE SQLite database from the EA-4C execution-authority
store, so the EA-4C.2 schema and the 672-test baseline are byte-for-byte
unchanged. Mutual exclusion for concurrent start coordinators is provided by
SQLite ``BEGIN IMMEDIATE`` + ``UNIQUE(route_id)`` on the reservations table.

Exactly-once admission invariant (EA-4D design section 22):

    for one WorkerRouteDecision:  at most 1 durable ExecutionStartReservation
    expected uniqueness:          UNIQUE(route_id)
    same-context replay:          returns the existing reservation
    changed launcher ownership:   ExecutionStartConflictError (no transfer)

Rollback seam: on any error after BEGIN IMMEDIATE (including an injected
failure), the whole transaction is rolled back, leaving ZERO reservation row
and ZERO START_RESERVED ledger entry.

Raw sqlite errors are normalized at the public boundary; they never escape as
sqlite3.* types.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from tools.hermes_core.execution_start import (
    ExecutionStartConflictError,
    ExecutionStartExpiredError,
    ExecutionStartIntegrityError,
    ExecutionStartReservation,
    ExecutionStartReservationStatus,
    ExecutionStartResult,
    ExecutionStartResultConflictError,
    ExecutionStartResultError,
    ExecutionLaunchAttempt,
    ExecutionLaunchAttemptStatus,
)
from tools.hermes_core.hashing import canonical_json, sha256_text


SCHEMA_VERSION_START = 2
SCHEMA_VERSION_LATEST = 3
SCHEMA_VERSION_LEGACY = 1
SUPPORTED_SCHEMA_VERSIONS_START = (SCHEMA_VERSION_START, SCHEMA_VERSION_LATEST)
MIGRATABLE_FROM_SCHEMA_VERSIONS_START = (SCHEMA_VERSION_LEGACY, SCHEMA_VERSION_START)

# Frozen, known-good v2 execution_start_results column set. Used by the
# v2->v3 migration to verify the on-disk shape before touching anything.
# v2 lacked the EA-4D.4A lineage/evidence columns; v3 adds them (NOT NULL).
V2_RESULT_COLUMNS = (
    "start_result_id", "artifact_hash", "launch_attempt_id", "launch_attempt_hash",
    "reservation_id", "reservation_hash", "route_id", "route_hash", "task_id",
    "worker_id", "worker_version", "outcome", "recorded_at", "runtime_run_id",
    "error_code", "error_summary", "canonical_json", "payload_sha256",
)

# Frozen v3 execution_start_results DDL. Adds the five EA-4D.4A NOT NULL columns
# (runtime_binding_*, idempotency_key, runtime_evidence_hash) so every persisted
# v3 result carries the complete frozen lineage/evidence needed to reproduce and
# verify its canonical result artifact hash.
V3_RESULT_TABLE_DDL = """
CREATE TABLE execution_start_results_v3 (
    start_result_id TEXT PRIMARY KEY,
    artifact_hash TEXT NOT NULL,
    launch_attempt_id TEXT NOT NULL UNIQUE,
    launch_attempt_hash TEXT NOT NULL,
    reservation_id TEXT NOT NULL,
    reservation_hash TEXT NOT NULL,
    route_id TEXT NOT NULL,
    route_hash TEXT NOT NULL,
    task_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    worker_version TEXT NOT NULL,
    outcome TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    runtime_run_id TEXT,
    error_code TEXT,
    error_summary TEXT,
    canonical_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    runtime_binding_id TEXT NOT NULL,
    runtime_binding_version TEXT NOT NULL,
    runtime_binding_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    runtime_evidence_hash TEXT NOT NULL
)
"""


# Frozen, known-good v1 execution_launch_attempts column set. Used by the
# v1->v2 migration to verify the on-disk shape before altering anything.
# v1 lacked reservation_hash; v2 adds it (NOT NULL).
V1_LAUNCH_ATTEMPT_COLUMNS = (
    "launch_attempt_id", "artifact_hash", "reservation_id", "route_id",
    "route_hash", "attempt_id", "attempt_hash", "authorization_id",
    "authorization_hash", "task_id", "worker_id", "worker_class",
    "worker_version", "operation", "input_hash", "runtime_binding_id",
    "runtime_binding_version", "runtime_binding_hash", "idempotency_key",
    "recorded_at", "must_start_by", "launcher_actor_id", "launcher_actor_type",
    "launcher_actor_context", "status", "canonical_json", "payload_sha256",
)


class ExecutionStartStoreError(Exception):
    """Base store error for EA-4D.2 start-admission persistence."""


class ExecutionStartSchemaError(ExecutionStartStoreError):
    """Schema version mismatch or bootstrap failure."""


class ExecutionStartMigrationError(ExecutionStartSchemaError):
    """v1 -> v2 migration refused (e.g. populated legacy rows with no
    verifiable reservation hash). Fail-closed; never synthesizes a value."""


# --------------------------------------------------------------------------- #
# Ledger entries (hash-linked, read-only here)
# --------------------------------------------------------------------------- #


class ExecutionStartLedgerEntry:
    """Minimal hash-linked ledger entry for EA-4D.2 start events."""

    def __init__(
        self,
        sequence_no: int,
        event_type: str,
        artifact_type: str,
        artifact_id: str,
        artifact_hash: str,
        entry_sha256: str,
        previous_entry_sha256: Optional[str],
        timestamp: str,
    ) -> None:
        self.sequence_no = sequence_no
        self.event_type = event_type
        self.artifact_type = artifact_type
        self.artifact_id = artifact_id
        self.artifact_hash = artifact_hash
        self.entry_sha256 = entry_sha256
        self.previous_entry_sha256 = previous_entry_sha256
        self.timestamp = timestamp


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

class _ExecutionLaunchAttemptLineageView:
    """Verified, read-only lineage view of a durable launch attempt.

    NOT a domain ExecutionLaunchAttempt. It reconstructs the minimal lineage
    fields the EA-4D.4A service needs, after verifying that the stored
    canonical payload hashes to the stored artifact_hash. A corrupted stored
    payload fails closed before any lineage field is trusted.
    """

    def __init__(self, d: dict, artifact_hash: str) -> None:
        from tools.hermes_core.hashing import sha256_payload
        if sha256_payload(d) != artifact_hash:
            raise ExecutionStartIntegrityError(
                "launch-attempt lineage canonical payload does not match "
                "stored artifact_hash; refusing to expose lineage")
        self._d = d
        self.artifact_hash = artifact_hash
        # launch_attempt_hash is the verified hash of this launch attempt's
        # canonical payload (see frozen EA-4D.4B micro-freeze #1 bridge).
        self.launch_attempt_hash = artifact_hash
        self.launch_attempt_id = d["launch_attempt_id"]
        self.route_id = d["route_id"]
        self.route_hash = d["route_hash"]
        self.task_id = d["task_id"]
        self.worker_id = d["worker_id"]
        self.worker_version = d["worker_version"]
        self.runtime_binding_id = d["runtime_binding_id"]
        self.runtime_binding_version = d["runtime_binding_version"]
        self.runtime_binding_hash = d["runtime_binding_hash"]
        self.idempotency_key = d["idempotency_key"]
        self.reservation_id = d["reservation_id"]
        # Authority-lineage fields already bound in the verified canonical_json
        # (EA-4D.4B Option A: expose, do not create new authority). These are
        # surfaced read-only after hash verification; no new persistence.
        self.authorization_id = d["authorization_id"]
        self.authorization_hash = d["authorization_hash"]
        self.attempt_id = d["attempt_id"]
        self.attempt_hash = d["attempt_hash"]
        self.reservation_hash = d["reservation_hash"]

    def verify_hash(self) -> bool:
        from tools.hermes_core.hashing import sha256_payload
        return sha256_payload(self._d) == self.artifact_hash


class _ExecutionStartReservationLineageView:
    """Verified, read-only lineage view of a durable reservation.

    NOT a domain ExecutionStartReservation. Verifies the stored canonical
    payload before exposing reservation_id/artifact_hash.
    """

    def __init__(self, d: dict, artifact_hash: str) -> None:
        from tools.hermes_core.hashing import sha256_payload
        if sha256_payload(d) != artifact_hash:
            raise ExecutionStartIntegrityError(
                "reservation lineage canonical payload does not match stored "
                "artifact_hash; refusing to expose lineage")
        self._d = d
        self.artifact_hash = artifact_hash
        self.reservation_id = d["reservation_id"]

    def verify_hash(self) -> bool:
        from tools.hermes_core.hashing import sha256_payload
        return sha256_payload(self._d) == self.artifact_hash


def _result_material_identity(result: "ExecutionStartResult") -> str:
    """Material result identity (frozen EA-4D.4).

    Binds the immutable semantic identity of a persisted result, EXCLUDING
    nonidentity metadata (error_summary, recorded_at, persisted_at). Two results
    with identical material identity but different error_summary are the SAME
    result (idempotent replay); a differing field here is a CONFLICT.
    """
    from tools.hermes_core.hashing import sha256_payload
    return sha256_payload({
        "schema": "ea4d4-result-material-identity-v1",
        "launch_attempt_id": result.launch_attempt_id,
        "launch_attempt_hash": result.launch_attempt_hash,
        "reservation_id": result.reservation_id,
        "reservation_hash": result.reservation_hash,
        "route_id": result.route_id,
        "route_hash": result.route_hash,
        "task_id": result.task_id,
        "worker_id": result.worker_id,
        "worker_version": result.worker_version,
        "runtime_binding_id": result.runtime_binding_id,
        "runtime_binding_version": result.runtime_binding_version,
        "runtime_binding_hash": result.runtime_binding_hash,
        "idempotency_key": result.idempotency_key,
        "result_outcome": result.outcome.value if hasattr(result.outcome, "value")
                            else result.outcome,
        "runtime_run_id": result.runtime_run_id or "",
        "runtime_evidence_hash": result.runtime_evidence_hash,
        "error_code": result.error_code or "",
    })


class SQLiteExecutionStartStore:
    """SQLite-backed EA-4D.2 start-admission store (START_RESERVED only)."""

    def __init__(self, db_path: "str | Path") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        # Test-only failure-injection seam (EA-4D.2 rollback proof): when set,
        # raise after the reservation row + START_RESERVED ledger entry are
        # inserted but before COMMIT, so rollback leaves zero residue.
        self._fail_after_reservation_insert = False
        # Test-only failure-injection seam (EA-4D.3B migration proof): when set,
        # raise at the start of _migrate_v1_to_v2 so the v1 database is left
        # recognizable (rolled back, version still 1).
        self._fail_during_migration = False
        # Test-only failure-injection seam (EA-4D.3B migration proof): when set,
        # raise AFTER the structural/data migration but BEFORE the schema-version
        # row is advanced to v2, proving transactional atomicity of the mutation.
        self._fail_after_launch_attempt_schema_migration = False
        # Test-only failure-injection seam (EA-4D.4A v3 migration proof): when
        # set, refuse the v2->v3 migration before any structural change.
        self._fail_before_v3_rename = False
        # Test-only failure-injection seam (EA-4D.4A v3 migration proof): when
        # set, raise AFTER the replacement table is created but BEFORE the
        # destructive DROP/RENAME, proving transactional rollback of in-flight
        # DDL inside BEGIN IMMEDIATE.
        self._fail_after_v3_create = False
        self._initialize()

    # -- schema --------------------------------------------------------------
    def _initialize(self) -> None:
        cur = self._conn
        cur.execute(
            "CREATE TABLE IF NOT EXISTS start_schema_version (version INTEGER)"
        )
        cur.execute(
            "INSERT OR IGNORE INTO start_schema_version (version) "
            "SELECT ? WHERE NOT EXISTS (SELECT 1 FROM start_schema_version)",
            (SCHEMA_VERSION_START,),
        )
        stored = cur.execute(
            "SELECT version FROM start_schema_version LIMIT 1"
        ).fetchone()
        if stored is None:
            raise ExecutionStartSchemaError(
                "start schema version row missing after bootstrap")
        version = int(stored["version"])
        if version == SCHEMA_VERSION_START:
            # Fresh-or-already-v2 database: ensure the v2 table set exists.
            self._ensure_v2_tables(cur)
            self._conn.commit()
            return
        if version in MIGRATABLE_FROM_SCHEMA_VERSIONS_START:
            # Legacy v1 database: migrate to v2 atomically. The whole migration
            # (shape check, ALTER/population/rebuild, version advance) runs in a
            # single transaction; any injected failure or error rolls back
            # completely, leaving a recognizable v1 database.
            self._run_atomic(lambda: self._migrate_v1_to_v2(cur))
            return
        raise ExecutionStartSchemaError(
            f"unsupported start schema version {version}; "
            f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS_START)}")

    # -- v2 schema -----------------------------------------------------------
    def _ensure_v2_tables(self, cur) -> None:
        """Create the v2 Start DB table set (reservation_hash persisted)."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_start_reservations (
                reservation_id TEXT PRIMARY KEY,
                artifact_hash TEXT NOT NULL,
                route_id TEXT NOT NULL UNIQUE,
                route_hash TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                attempt_hash TEXT NOT NULL,
                authorization_id TEXT NOT NULL,
                authorization_hash TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                claim_hash TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                decision_hash TEXT NOT NULL,
                task_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                worker_class TEXT,
                worker_version TEXT NOT NULL,
                operation TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                reserved_at TEXT NOT NULL,
                must_start_by TEXT NOT NULL,
                launcher_actor_id TEXT NOT NULL,
                launcher_actor_type TEXT NOT NULL,
                launcher_actor_context TEXT,
                status TEXT NOT NULL,
                canonical_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )
        # Schema-completeness only: the launch-attempt table exists, but NO
        # EA-4D.2 code path writes to it. EA-4D.3 owns launch orchestration.
        # v2 adds reservation_hash (NOT NULL) to the launch-attempt table.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_launch_attempts (
                launch_attempt_id TEXT PRIMARY KEY,
                artifact_hash TEXT NOT NULL,
                reservation_id TEXT NOT NULL UNIQUE,
                reservation_hash TEXT NOT NULL,
                route_id TEXT NOT NULL,
                route_hash TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                attempt_hash TEXT NOT NULL,
                authorization_id TEXT NOT NULL,
                authorization_hash TEXT NOT NULL,
                task_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                worker_class TEXT,
                worker_version TEXT NOT NULL,
                operation TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                runtime_binding_id TEXT NOT NULL,
                runtime_binding_version TEXT NOT NULL,
                runtime_binding_hash TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                must_start_by TEXT NOT NULL,
                launcher_actor_id TEXT NOT NULL,
                launcher_actor_type TEXT NOT NULL,
                launcher_actor_context TEXT,
                status TEXT NOT NULL,
                canonical_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_start_results (
                start_result_id TEXT PRIMARY KEY,
                artifact_hash TEXT NOT NULL,
                launch_attempt_id TEXT NOT NULL,
                launch_attempt_hash TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                reservation_hash TEXT NOT NULL,
                route_id TEXT NOT NULL,
                route_hash TEXT NOT NULL,
                task_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                worker_version TEXT NOT NULL,
                outcome TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                runtime_run_id TEXT,
                error_code TEXT,
                error_summary TEXT,
                canonical_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_start_ledger (
                sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_entry_sha256 TEXT,
                entry_sha256 TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )

    # -- v2 -> v3 result-schema migration (EA-4D.4A) ---------------------------
    def migrate_to_v3(self) -> None:
        """Explicitly migrate the Start DB result schema from v2 to v3.

        EA-4D.4A frozen rule: the v2->v3 result migration is EMPTY-ONLY and
        FAIL-CLOSED. Because execution_start_results has never had a production
        INSERT path (verified during design inspection), any populated v2 result
        table would represent unreconstructable historical evidence (the v3
        shape requires runtime_evidence_hash and runtime_binding lineage that
        cannot be losslessly recovered). A populated v2 result table therefore
        triggers a typed refusal; the old table, its row, and the schema version
        are left untouched.

        The version check, exact-shape verification, and the populated-table
        COUNT(*) refusal ALL execute inside one BEGIN IMMEDIATE transaction
        (via _run_atomic), so a concurrent writer cannot insert a v2 result
        between the COUNT(*) check and the structural migration. The typed
        exception escapes _run_atomic, which rolls back the transaction.
        """
        if self._fail_before_v3_rename:
            # Test-only seam: refuse before any structural change.
            raise ExecutionStartMigrationError("injected v3 refusal")
        self._run_atomic(self._migrate_v2_to_v3)

    def _migrate_v2_to_v3(self) -> None:
        """Migration body; runs inside _run_atomic (BEGIN IMMEDIATE)."""
        cur = self._conn
        version = int(cur.execute(
            "SELECT version FROM start_schema_version LIMIT 1").fetchone()["version"])
        if version != SCHEMA_VERSION_START:
            raise ExecutionStartSchemaError(
                f"v3 migration requires schema version {SCHEMA_VERSION_START}; "
                f"got {version}")
        # Exact v2 result-table shape verification.
        cols = [r["name"] for r in cur.execute(
            "PRAGMA table_info(execution_start_results)").fetchall()]
        if cols != list(V2_RESULT_COLUMNS):
            raise ExecutionStartMigrationError(
                "execution_start_results is not in the known v2 shape")
        # Populated-table check INSIDE the transaction (no TOCTOU window).
        count = cur.execute(
            "SELECT COUNT(*) AS c FROM execution_start_results").fetchone()["c"]
        if count != 0:
            # Populated v2 result table: unreconstructable; fail closed.
            raise ExecutionStartMigrationError(
                "populated v2 execution_start_results cannot be losslessly "
                "migrated to v3; refusing (no synthetic evidence)")
        cur.execute(V3_RESULT_TABLE_DDL)
        if self._fail_after_v3_create:
            # Test-only seam: prove in-flight DDL inside BEGIN IMMEDIATE rolls
            # back after the replacement table exists but before destructive
            # replacement. _run_atomic's rollback restores the v2 table.
            raise ExecutionStartMigrationError("injected post-create failure")
        cur.execute("DROP TABLE execution_start_results")
        cur.execute(
            "ALTER TABLE execution_start_results_v3 "
            "RENAME TO execution_start_results")
        # Version advancement LAST (within the same transaction).
        cur.execute(
            "UPDATE start_schema_version SET version = ?",
            (SCHEMA_VERSION_LATEST,))

    # -- result persistence (EA-4D.4A) -------------------------------------
    def persist_execution_start_result(self, result: "ExecutionStartResult") -> None:
        """Idempotently persist one immutable ExecutionStartResult.

        Replay semantics: same launch_attempt_id + same canonical evidence ->
        the same row (INSERT OR IGNORE then read-back). A conflicting result for
        the same launch_attempt_id (different outcome/run identity/error code)
        raises ExecutionStartResultConflictError and is never overwritten.
        """
        cur = self._conn
        exists = cur.execute(
            "SELECT 1 FROM execution_start_results WHERE launch_attempt_id = ?",
            (result.launch_attempt_id,)).fetchone()
        if exists:
            existing = self.get_execution_start_result(result.launch_attempt_id)
            if existing is None:
                raise ExecutionStartResultConflictError(
                    f"conflicting ExecutionStartResult for "
                    f"launch_attempt_id={result.launch_attempt_id!r}")
            # Replay vs conflict uses MATERIAL RESULT IDENTITY, which explicitly
            # EXCLUDES nonidentity metadata (error_summary, recorded_at,
            # persisted_at). Same material identity + differing summary -> the
            # already-persisted immutable row is returned (idempotent); the
            # stored error_summary is NOT overwritten. Different material
            # identity (outcome/run identity/error code) -> CONFLICT, fail closed.
            if _result_material_identity(existing) != _result_material_identity(result):
                raise ExecutionStartResultConflictError(
                    f"conflicting ExecutionStartResult for "
                    f"launch_attempt_id={result.launch_attempt_id!r}")
            return  # idempotent replay (same material identity)
        cur.execute(
            """
            INSERT INTO execution_start_results (
                start_result_id, artifact_hash, launch_attempt_id,
                launch_attempt_hash, reservation_id, reservation_hash, route_id,
                route_hash, task_id, worker_id, worker_version, outcome,
                recorded_at, runtime_run_id, error_code, error_summary,
                canonical_json, payload_sha256, runtime_binding_id,
                runtime_binding_version, runtime_binding_hash, idempotency_key,
                runtime_evidence_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.start_result_id, result.artifact_hash,
                result.launch_attempt_id, result.launch_attempt_hash,
                result.reservation_id, result.reservation_hash, result.route_id,
                result.route_hash, result.task_id, result.worker_id,
                result.worker_version, result.outcome.value, result.recorded_at,
                result.runtime_run_id, result.error_code, result.error_summary,
                result.canonical_json(), result.artifact_hash,
                result.runtime_binding_id, result.runtime_binding_version,
                result.runtime_binding_hash, result.idempotency_key,
                result.runtime_evidence_hash,
            ),
        )
        self._conn.commit()

    def get_execution_start_result(
        self, launch_attempt_id: str
    ) -> Optional["ExecutionStartResult"]:
        """Return the persisted result for a launch attempt, or None."""
        row = self._conn.execute(
            "SELECT * FROM execution_start_results WHERE launch_attempt_id = ?",
            (launch_attempt_id,)).fetchone()
        if row is None:
            return None
        from tools.hermes_core.execution_start import ExecutionStartOutcome
        return ExecutionStartResult(
            start_result_id=row["start_result_id"],
            start_result_version="1",
            artifact_hash=row["artifact_hash"],
            launch_attempt_id=row["launch_attempt_id"],
            launch_attempt_hash=row["launch_attempt_hash"],
            reservation_id=row["reservation_id"],
            reservation_hash=row["reservation_hash"],
            route_id=row["route_id"],
            route_hash=row["route_hash"],
            task_id=row["task_id"],
            worker_id=row["worker_id"],
            worker_version=row["worker_version"],
            runtime_binding_id=row["runtime_binding_id"],
            runtime_binding_version=row["runtime_binding_version"],
            runtime_binding_hash=row["runtime_binding_hash"],
            idempotency_key=row["idempotency_key"],
            outcome=ExecutionStartOutcome(row["outcome"]),
            recorded_at=row["recorded_at"],
            runtime_run_id=row["runtime_run_id"],
            error_code=row["error_code"],
            error_summary=row["error_summary"],
            runtime_evidence_hash=row["runtime_evidence_hash"],
        )

    # -- lineage resolution (read-only, for 4A verification) ----------------
    def get_execution_launch_attempt(
        self, launch_attempt_id: str
    ) -> Optional["_ExecutionLaunchAttemptLineageView"]:
        """Return verified durable launch-attempt lineage, or None."""
        row = self._conn.execute(
            "SELECT canonical_json, artifact_hash FROM execution_launch_attempts "
            "WHERE launch_attempt_id = ?", (launch_attempt_id,)).fetchone()
        if row is None:
            return None
        import json
        return _ExecutionLaunchAttemptLineageView(json.loads(row["canonical_json"]), row["artifact_hash"])

    def get_execution_start_reservation(
        self, reservation_id: str
    ) -> Optional["_ExecutionStartReservationLineageView"]:
        """Return verified durable reservation lineage, or None."""
        row = self._conn.execute(
            "SELECT canonical_json, artifact_hash FROM execution_start_reservations "
            "WHERE reservation_id = ?", (reservation_id,)).fetchone()
        if row is None:
            return None
        import json
        return _ExecutionStartReservationLineageView(json.loads(row["canonical_json"]), row["artifact_hash"])
    def _migrate_v1_to_v2(self, cur) -> None:
        """Atomically migrate a legacy v1 Start DB to v2.

        v2 adds ``reservation_hash`` (NOT NULL) to ``execution_launch_attempts``.
        The migration refuses (fail-closed) if it cannot prove the shape, or
        if populated legacy launch-attempt rows exist whose ``reservation_hash``
        cannot be reconstructed from a verifiable durable ExecutionStartReservation.
        No default/synthetic value is ever written. On any failure the caller's
        transaction is rolled back, leaving a recognizable v1 database.
        """
        if self._fail_during_migration:
            raise ExecutionStartMigrationError("injected migration failure")
        # 1. Verify the actual on-disk launch-attempt shape matches the known
        #    v1 definition (must NOT yet contain reservation_hash).
        cols = [
            r["name"] for r in cur.execute(
                "PRAGMA table_info(execution_launch_attempts)").fetchall()
        ]
        if cols != list(V1_LAUNCH_ATTEMPT_COLUMNS):
            raise ExecutionStartMigrationError(
                f"execution_launch_attempts on-disk shape does not match known "
                f"v1 definition; refusing to migrate. got={cols}")
        if "reservation_hash" in cols:
            raise ExecutionStartMigrationError(
                "execution_launch_attempts already has reservation_hash; "
                "unexpected v1 state")
        # 2. Count legacy launch-attempt rows.
        row_count = cur.execute(
            "SELECT COUNT(*) AS n FROM execution_launch_attempts"
        ).fetchone()["n"]
        # 3. Add the column. For an empty table SQLite permits NOT NULL with no
        #    default; for a populated table we add it nullable first, then
        #    populate from verified reservations and rebuild as NOT NULL.
        if row_count == 0:
            cur.execute(
                "ALTER TABLE execution_launch_attempts "
                "ADD COLUMN reservation_hash TEXT NOT NULL"
            )
        else:
            cur.execute(
                "ALTER TABLE execution_launch_attempts "
                "ADD COLUMN reservation_hash TEXT"
            )
            self._populate_legacy_reservation_hashes(cur, row_count)
            self._rebuild_launch_attempts_not_null(cur)
        # 3b. Post-mutation / pre-version-advance rollback seam. If armed, fail
        # here AFTER the structural + data migration has occurred but BEFORE the
        # schema-version row is advanced to v2. A crash at this point must roll
        # back every mutation, leaving a recognizable v1 database.
        if self._fail_after_launch_attempt_schema_migration:
            raise ExecutionStartMigrationError(
                "injected post-mutation failure (rollback proof)")
        # 4. Advance the schema version LAST (within the same transaction), so a
        #    crash before this point leaves a recognizable v1 database.
        cur.execute(
            "UPDATE start_schema_version SET version = ?",
            (SCHEMA_VERSION_START,),
        )

    def _populate_legacy_reservation_hashes(self, cur, row_count: int) -> None:
        """Reconstruct reservation_hash for each populated legacy launch-attempt
        row from a verified durable ExecutionStartReservation. Fail closed if
        any row cannot be proven."""
        rows = cur.execute(
            "SELECT launch_attempt_id, reservation_id FROM "
            "execution_launch_attempts"
        ).fetchall()
        if len(rows) != row_count:
            raise ExecutionStartMigrationError(
                "launch-attempt row count shifted during migration")
        for row in rows:
            reservation_id = row["reservation_id"]
            res_row = cur.execute(
                "SELECT * FROM execution_start_reservations WHERE "
                "reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if res_row is None:
                raise ExecutionStartMigrationError(
                    f"launch attempt {row['launch_attempt_id']} references "
                    f"reservation {reservation_id} which is absent; cannot "
                    f"reconstruct reservation_hash (fail closed)")
            reservation = self._row_to_reservation(res_row)
            # _row_to_reservation already verified the reservation hash/linkage.
            cur.execute(
                "UPDATE execution_launch_attempts SET reservation_hash = ? "
                "WHERE launch_attempt_id = ?",
                (reservation.artifact_hash, row["launch_attempt_id"]),
            )

    def _rebuild_launch_attempts_not_null(self, cur) -> None:
        """Rebuild execution_launch_attempts so reservation_hash is NOT NULL,
        after populated rows have valid hashes. Any still-NULL row fails closed.
        """
        null_rows = cur.execute(
            "SELECT COUNT(*) AS n FROM execution_launch_attempts "
            "WHERE reservation_hash IS NULL"
        ).fetchone()["n"]
        if null_rows:
            raise ExecutionStartMigrationError(
                f"{null_rows} launch-attempt row(s) still lack a verifiable "
                f"reservation_hash after reconstruction; fail closed")
        cur.execute(
            "CREATE TABLE execution_launch_attempts_v2 AS "
            "SELECT * FROM execution_launch_attempts"
        )
        cur.execute("DROP TABLE execution_launch_attempts")
        cur.execute(
            "ALTER TABLE execution_launch_attempts_v2 "
            "RENAME TO execution_launch_attempts"
        )

    # -- helpers -------------------------------------------------------------
    def _run_atomic(self, fn) -> None:
        """Own one SQLite transaction (no nested commits)."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            fn()
            if self._fail_after_reservation_insert:
                raise ExecutionStartIntegrityError(
                    "injected failure after reservation persistence (rollback test)")
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _append_ledger(self, reservation: ExecutionStartReservation, now: str,
                       payload_sha256: str) -> str:
        prev = self._conn.execute(
            "SELECT entry_sha256 FROM execution_start_ledger "
            "ORDER BY sequence_no DESC LIMIT 1"
        ).fetchone()
        previous = prev["entry_sha256"] if prev else None
        payload = {
            "event_type": "START_RESERVED",
            "artifact_type": "ExecutionStartReservation",
            "artifact_id": reservation.reservation_id,
            "artifact_hash": reservation.artifact_hash,
            "payload_sha256": payload_sha256,
            "previous_entry_sha256": previous,
            "timestamp": now,
        }
        entry_sha = sha256_text(canonical_json(payload))
        self._conn.execute(
            "INSERT INTO execution_start_ledger "
            "(event_id, event_type, artifact_type, artifact_id, artifact_hash, "
            "payload_sha256, previous_entry_sha256, entry_sha256, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reservation.reservation_id,
                "START_RESERVED",
                "ExecutionStartReservation",
                reservation.reservation_id,
                reservation.artifact_hash,
                payload_sha256,
                previous,
                entry_sha,
                now,
            ),
        )
        return entry_sha

    @staticmethod
    def _row_to_reservation(row: sqlite3.Row) -> ExecutionStartReservation:
        """Reconstruct + verify a durable ExecutionStartReservation on read.

        The reconstructed artifact's own ``verify_hash()`` is checked, and the
        recomputed payload/linkage hash is compared against the stored physical
        ``payload_sha256``. Any divergence fails closed (tamper-evident).
        """
        try:
            status = ExecutionStartReservationStatus(row["status"])
        except ValueError:
            raise ExecutionStartIntegrityError(
                f"reservation {row['reservation_id']} has an invalid stored "
                f"status {row['status']!r}; refusing to return tampered artifact")
        artifact = ExecutionStartReservation(
            reservation_id=row["reservation_id"],
            artifact_version="1",  # canonical schema version literal
            artifact_hash=row["artifact_hash"],
            route_id=row["route_id"],
            route_hash=row["route_hash"],
            attempt_id=row["attempt_id"],
            attempt_hash=row["attempt_hash"],
            authorization_id=row["authorization_id"],
            authorization_hash=row["authorization_hash"],
            claim_id=row["claim_id"],
            claim_hash=row["claim_hash"],
            request_id=row["request_id"],
            request_hash=row["request_hash"],
            decision_id=row["decision_id"],
            decision_hash=row["decision_hash"],
            task_id=row["task_id"],
            worker_id=row["worker_id"],
            worker_class=row["worker_class"],
            worker_version=row["worker_version"],
            operation=row["operation"],
            input_hash=row["input_hash"],
            reserved_at=row["reserved_at"],
            must_start_by=row["must_start_by"],
            launcher_actor_id=row["launcher_actor_id"],
            launcher_actor_type=row["launcher_actor_type"],
            launcher_actor_context=row["launcher_actor_context"],
            status=status,
        )
        if not artifact.verify_hash():
            raise ExecutionStartIntegrityError(
                f"reservation {artifact.reservation_id} failed hash verification "
                f"on read; refusing to return tampered artifact")
        canonical = canonical_json(artifact.to_canonical_dict())
        if sha256_text(canonical) != row["payload_sha256"]:
            raise ExecutionStartIntegrityError(
                f"reservation {artifact.reservation_id} payload/linkage hash "
                f"mismatch on read; refusing to return tampered artifact")
        return artifact

    # -- admission ----------------------------------------------------------
    def reserve_start(self, reservation: ExecutionStartReservation,
                      now: str, must_start_by: str) -> ExecutionStartReservation:
        """Exclusively admit one durable START_RESERVED reservation for a route.

        Admission order:
            validate artifact hash + required lineage
            -> deadline recheck (now <= must_start_by), else fail-closed
            -> BEGIN IMMEDIATE
            -> if a reservation already exists for the route:
                 if replay-significant fields match: return existing (replay)
                 else: raise ExecutionStartConflictError (changed launcher)
            -> else INSERT reservation + START_RESERVED ledger event
            -> COMMIT (unless the rollback seam is armed)

        This is the EA-4D.2 STOP point. The method never creates a launch
        attempt and never invokes a worker.
        """
        if not isinstance(reservation, ExecutionStartReservation):
            raise ExecutionStartStoreError(
                f"reserve_start requires ExecutionStartReservation, got {type(reservation)!r}")
        if not reservation.verify_hash():
            raise ExecutionStartIntegrityError(
                f"reservation {reservation.reservation_id} failed hash verification; "
                f"refusing to persist")
        if reservation.status != ExecutionStartReservationStatus.RESERVED:
            raise ExecutionStartIntegrityError(
                f"EA-4D.2 only admits RESERVED reservations; got {reservation.status}")
        # Low-level boundary: the caller must not supply two independent semantic
        # versions of the same values. The store owns the authoritative binding.
        if reservation.reserved_at != now:
            raise ExecutionStartIntegrityError(
                f"reservation.reserved_at ({reservation.reserved_at}) != now "
                f"({now}); caller must bind reserved_at to the captured clock")
        if reservation.must_start_by != must_start_by:
            raise ExecutionStartIntegrityError(
                f"reservation.must_start_by ({reservation.must_start_by}) != "
                f"must_start_by ({must_start_by}); caller must bind the same deadline")
        # Hard start deadline: inclusive boundary (now <= must_start_by).
        if not _deadline_ok(now, must_start_by):
            raise ExecutionStartExpiredError(
                f"start admission denied: now={now} > must_start_by={must_start_by}")

        canonical = canonical_json(reservation.to_canonical_dict())
        payload_sha256 = sha256_text(canonical)

        result: dict = {}

        def _work() -> None:
            existing = self._conn.execute(
                "SELECT * FROM execution_start_reservations WHERE route_id = ?",
                (reservation.route_id,),
            ).fetchone()
            if existing is not None:
                existing_res = self._row_to_reservation(existing)
                if _replay_significant_equal(reservation, existing_res):
                    # Same-context replay: return the durable reservation.
                    result["reservation"] = existing_res
                    return
                # Changed launcher ownership: conflict, no silent transfer.
                raise ExecutionStartConflictError(
                    f"route {reservation.route_id} already reserved by "
                    f"launcher {existing_res.launcher_actor_id}; "
                    f"divergent launcher {reservation.launcher_actor_id} conflicts")
            self._conn.execute(
                "INSERT INTO execution_start_reservations "
                "(reservation_id, artifact_hash, route_id, route_hash, attempt_id, "
                "attempt_hash, authorization_id, authorization_hash, claim_id, "
                "claim_hash, request_id, request_hash, decision_id, decision_hash, "
                "task_id, worker_id, worker_class, worker_version, operation, "
                "input_hash, reserved_at, must_start_by, launcher_actor_id, "
                "launcher_actor_type, launcher_actor_context, status, canonical_json, "
                "payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reservation.reservation_id,
                    reservation.artifact_hash,
                    reservation.route_id,
                    reservation.route_hash,
                    reservation.attempt_id,
                    reservation.attempt_hash,
                    reservation.authorization_id,
                    reservation.authorization_hash,
                    reservation.claim_id,
                    reservation.claim_hash,
                    reservation.request_id,
                    reservation.request_hash,
                    reservation.decision_id,
                    reservation.decision_hash,
                    reservation.task_id,
                    reservation.worker_id,
                    reservation.worker_class,
                    reservation.worker_version,
                    reservation.operation,
                    reservation.input_hash,
                    reservation.reserved_at,
                    reservation.must_start_by,
                    reservation.launcher_actor_id,
                    reservation.launcher_actor_type,
                    reservation.launcher_actor_context,
                    reservation.status.value,
                    canonical,
                    payload_sha256,
                ),
            )
            self._append_ledger(reservation, now, payload_sha256)
            result["reservation"] = reservation

        try:
            self._run_atomic(_work)
        except ExecutionStartConflictError:
            raise
        except sqlite3.IntegrityError as exc:
            # Lost the INSERT race (UNIQUE(route_id)): another coordinator won.
            # Re-read the durable winner and return it as a replay.
            if "UNIQUE" not in str(exc):
                raise ExecutionStartIntegrityError(
                    f"unexpected integrity error: {exc}") from exc
            winner = self.get_reservation_for_route(reservation.route_id)
            if winner is None:
                raise ExecutionStartIntegrityError(
                    "lost INSERT race but no winner found") from exc
            return winner
        return result["reservation"]

    # -- reads ---------------------------------------------------------------
    def get_reservation(self, reservation_id: str) -> Optional[ExecutionStartReservation]:
        """Read a durable reservation by its own id (always verifies integrity)."""
        row = self._conn.execute(
            "SELECT * FROM execution_start_reservations WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_reservation(row)

    def get_reservation_for_route(self, route_id: str) -> Optional[ExecutionStartReservation]:
        row = self._conn.execute(
            "SELECT * FROM execution_start_reservations WHERE route_id = ?",
            (route_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_reservation(row)

    def get_reservations_for_route(self, route_id: str) -> List[ExecutionStartReservation]:
        rows = self._conn.execute(
            "SELECT * FROM execution_start_reservations WHERE route_id = ?",
            (route_id,),
        ).fetchall()
        return [self._row_to_reservation(r) for r in rows]

    def get_start_ledger_events(self, event_type: Optional[str] = None) -> List[ExecutionStartLedgerEntry]:
        if event_type is None:
            rows = self._conn.execute(
                "SELECT sequence_no, event_type, artifact_type, artifact_id, "
                "artifact_hash, entry_sha256, previous_entry_sha256, timestamp "
                "FROM execution_start_ledger ORDER BY sequence_no ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT sequence_no, event_type, artifact_type, artifact_id, "
                "artifact_hash, entry_sha256, previous_entry_sha256, timestamp "
                "FROM execution_start_ledger WHERE event_type = ? "
                "ORDER BY sequence_no ASC",
                (event_type,),
            ).fetchall()
        return [
            ExecutionStartLedgerEntry(
                sequence_no=r["sequence_no"],
                event_type=r["event_type"],
                artifact_type=r["artifact_type"],
                artifact_id=r["artifact_id"],
                artifact_hash=r["artifact_hash"],
                entry_sha256=r["entry_sha256"],
                previous_entry_sha256=r["previous_entry_sha256"],
                timestamp=r["timestamp"],
            )
            for r in rows
        ]

    def has_launch_attempt(self, reservation_id: str) -> bool:
        """Read-only probe that the launch-attempt table exists but is empty."""
        row = self._conn.execute(
            "SELECT 1 FROM execution_launch_attempts WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        return row is not None

    def get_launch_attempt(
        self, reservation_id: str,
    ) -> Optional[ExecutionLaunchAttempt]:
        """Read a durable ExecutionLaunchAttempt by reservation_id.

        Always verifies integrity on read: reconstructed artifact
        ``verify_hash()`` and recomputed ``payload_sha256`` are checked.
        Tampering any persisted column fails closed.
        """
        row = self._conn.execute(
            "SELECT * FROM execution_launch_attempts WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_launch_attempt(row)

    def record_reservation(
        self,
        *,
        reservation: ExecutionStartReservation,
        now: str,
    ) -> ExecutionStartReservation:
        """Persist one durable ExecutionStartReservation (EA-4D.2 admission).

        Mirrors the record_launch_attempt discipline: verifies the reservation
        hash, stores canonical_json + payload_sha256, and enforces exactly-once
        admission via UNIQUE(route_id). Same-context replay returns the durable
        reservation; a divergent launcher ownership conflicts (no silent
        transfer).
        """
        if not isinstance(reservation, ExecutionStartReservation):
            raise ExecutionStartStoreError(
                f"record_reservation requires ExecutionStartReservation, "
                f"got {type(reservation)!r}")
        if not reservation.verify_hash():
            raise ExecutionStartIntegrityError(
                f"reservation {reservation.reservation_id} failed hash "
                f"verification; refusing to persist")
        canonical = canonical_json(reservation.to_canonical_dict())
        payload_sha256 = sha256_text(canonical)

        result: dict = {}

        def _work() -> None:
            existing = self._conn.execute(
                "SELECT * FROM execution_start_reservations WHERE route_id = ?",
                (reservation.route_id,)).fetchone()
            if existing is not None:
                existing_res = self._row_to_reservation(existing)
                if (existing_res.reservation_id == reservation.reservation_id
                        and existing_res.route_id == reservation.route_id
                        and existing_res.artifact_hash == reservation.artifact_hash):
                    result["reservation"] = existing_res
                    return
                raise ExecutionStartConflictError(
                    f"route {reservation.route_id} already reserved by "
                    f"launcher {existing_res.launcher_actor_id}; "
                    f"divergent launcher conflicts")
            self._conn.execute(
                "INSERT INTO execution_start_reservations "
                "(reservation_id, artifact_hash, route_id, route_hash, attempt_id, "
                "attempt_hash, authorization_id, authorization_hash, claim_id, "
                "claim_hash, request_id, request_hash, decision_id, decision_hash, "
                "task_id, worker_id, worker_class, worker_version, operation, "
                "input_hash, reserved_at, must_start_by, launcher_actor_id, "
                "launcher_actor_type, launcher_actor_context, status, canonical_json, "
                "payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reservation.reservation_id,
                    reservation.artifact_hash,
                    reservation.route_id,
                    reservation.route_hash,
                    reservation.attempt_id,
                    reservation.attempt_hash,
                    reservation.authorization_id,
                    reservation.authorization_hash,
                    reservation.claim_id,
                    reservation.claim_hash,
                    reservation.request_id,
                    reservation.request_hash,
                    reservation.decision_id,
                    reservation.decision_hash,
                    reservation.task_id,
                    reservation.worker_id,
                    reservation.worker_class,
                    reservation.worker_version,
                    reservation.operation,
                    reservation.input_hash,
                    reservation.reserved_at,
                    reservation.must_start_by,
                    reservation.launcher_actor_id,
                    reservation.launcher_actor_type,
                    reservation.launcher_actor_context,
                    reservation.status.value,
                    canonical,
                    payload_sha256,
                ),
            )
            result["reservation"] = reservation

        self._run_atomic(_work)
        return result["reservation"]

    def record_launch_attempt(
        self,
        *,
        attempt: ExecutionLaunchAttempt,
        now: str,
    ) -> ExecutionLaunchAttempt:
        """Persist one durable ExecutionLaunchAttempt and one
        LAUNCH_ATTEMPT_RECORDED ledger event inside a single atomic
        transaction.

        The store does NOT:
          * resolve a runtime binding,
          * read the clock,
          * invoke an adapter or worker,
          * infer a runtime result.

        Entry precondition: the caller has already verified lineage,
        resolved the binding, captured the clock, and rechecked the
        deadline (EA-4D.3B admission ordering, sections 1-9).
        """
        if not isinstance(attempt, ExecutionLaunchAttempt):  # type: ignore[attr-defined]  # noqa: F821
            raise ExecutionStartStoreError(
                f"record_launch_attempt requires ExecutionLaunchAttempt, "
                f"got {type(attempt)!r}")
        if not attempt.verify_hash():
            raise ExecutionStartIntegrityError(
                f"launch attempt {attempt.launch_attempt_id} failed hash "
                f"verification; refusing to persist")
        canonical = canonical_json(attempt.to_canonical_dict())  # type: ignore[attr-defined]  # noqa: F821
        payload_sha256 = sha256_text(canonical)

        result: dict = {}

        def _work() -> None:
            try:
                self._conn.execute(
                    "INSERT INTO execution_launch_attempts "
                    "(launch_attempt_id, artifact_hash, reservation_id, "
                    "reservation_hash, route_id, route_hash, attempt_id, "
                    "attempt_hash, authorization_id, authorization_hash, task_id, worker_id, "
                    "worker_class, worker_version, operation, input_hash, "
                    "runtime_binding_id, runtime_binding_version, "
                    "runtime_binding_hash, idempotency_key, recorded_at, "
                    "must_start_by, launcher_actor_id, launcher_actor_type, "
                    "launcher_actor_context, status, canonical_json, "
                    "payload_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt.launch_attempt_id,
                        attempt.artifact_hash,
                        attempt.reservation_id,
                        attempt.reservation_hash,
                        attempt.route_id,
                        attempt.route_hash,
                        attempt.attempt_id,
                        attempt.attempt_hash,
                        attempt.authorization_id,
                        attempt.authorization_hash,
                        attempt.task_id,
                        attempt.worker_id,
                        attempt.worker_class,
                        attempt.worker_version,
                        attempt.operation,
                        attempt.input_hash,
                        attempt.runtime_binding_id,
                        attempt.runtime_binding_version,
                        attempt.runtime_binding_hash,
                        attempt.idempotency_key,
                        attempt.recorded_at,
                        attempt.must_start_by,
                        attempt.launcher_actor_id,
                        attempt.launcher_actor_type,
                        attempt.launcher_actor_context,
                        attempt.status.value,
                        canonical,
                        payload_sha256,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "UNIQUE" in str(exc) and "reservation_id" in str(exc):
                    raise ExecutionStartConflictError(
                        f"launch attempt already exists for reservation "
                        f"{attempt.reservation_id}; no second admission") from exc
                raise ExecutionStartIntegrityError(
                    f"unexpected integrity error persisting launch attempt: "
                    f"{exc}") from exc
            self._append_launch_attempt_ledger(attempt, now, payload_sha256)
            result["attempt"] = attempt

        try:
            self._run_atomic(_work)
        except ExecutionStartConflictError:
            raise
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc) and "reservation_id" in str(exc):
                raise ExecutionStartConflictError(
                    f"lost INSERT race (UNIQUE reservation_id) for "
                    f"{attempt.reservation_id}; re-reading durable winner") from exc
            raise ExecutionStartIntegrityError(
                f"unexpected integrity error: {exc}") from exc
        return result["attempt"]

    def _append_launch_attempt_ledger(
        self,
        attempt: ExecutionLaunchAttempt,  # type: ignore[attr-defined]  # noqa: F821
        now: str,
        payload_sha256: str,
    ) -> str:
        prev = self._conn.execute(
            "SELECT entry_sha256 FROM execution_start_ledger "
            "ORDER BY sequence_no DESC LIMIT 1",
        ).fetchone()
        previous = prev["entry_sha256"] if prev else None
        payload = {
            "event_type": "LAUNCH_ATTEMPT_RECORDED",
            "artifact_type": "ExecutionLaunchAttempt",
            "artifact_id": attempt.launch_attempt_id,
            "artifact_hash": attempt.artifact_hash,
            "payload_sha256": payload_sha256,
            "previous_entry_sha256": previous,
            "timestamp": now,
        }
        entry_sha = sha256_text(canonical_json(payload))
        self._conn.execute(
            "INSERT INTO execution_start_ledger "
            "(event_id, event_type, artifact_type, artifact_id, artifact_hash, "
            "payload_sha256, previous_entry_sha256, entry_sha256, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt.launch_attempt_id,
                "LAUNCH_ATTEMPT_RECORDED",
                "ExecutionLaunchAttempt",
                attempt.launch_attempt_id,
                attempt.artifact_hash,
                payload_sha256,
                previous,
                entry_sha,
                now,
            ),
        )
        return entry_sha

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------- #
# Module-local helpers
# --------------------------------------------------------------------------- #


def _deadline_ok(now: str, must_start_by: str) -> bool:
    """Inclusive boundary: now <= must_start_by (EA-4D hard start deadline)."""
    from datetime import datetime

    def _p(s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

    return _p(now) <= _p(must_start_by)


def _replay_significant_equal(a: ExecutionStartReservation,
                              b: ExecutionStartReservation) -> bool:
    """Replay-significant equality (EA-4D design section 23)."""
    return (
        a.route_id == b.route_id
        and a.route_hash == b.route_hash
        and a.attempt_id == b.attempt_id
        and a.attempt_hash == b.attempt_hash
        and a.authorization_id == b.authorization_id
        and a.authorization_hash == b.authorization_hash
        and a.worker_id == b.worker_id
        and a.worker_class == b.worker_class
        and a.worker_version == b.worker_version
        and a.operation == b.operation
        and a.input_hash == b.input_hash
        and a.launcher_actor_id == b.launcher_actor_id
        and a.launcher_actor_type == b.launcher_actor_type
        and a.launcher_actor_context == b.launcher_actor_context
    )


def _row_to_launch_attempt(row: sqlite3.Row) -> ExecutionLaunchAttempt:
    """Reconstruct + verify a durable ExecutionLaunchAttempt on read.

    The reconstructed artifact's own ``verify_hash()`` is checked, and the
    recomputed canonical payload hash is compared against the stored physical
    ``payload_sha256``. Any divergence fails closed (tamper-evident).
    """
    try:
        status = ExecutionLaunchAttemptStatus(row["status"])
    except ValueError:
        raise ExecutionStartIntegrityError(
            f"launch attempt row for reservation {row['reservation_id']} "
            f"has an invalid stored status {row['status']!r}; refusing to "
            f"return tampered artifact")
    artifact = ExecutionLaunchAttempt(
        launch_attempt_id=row["launch_attempt_id"],
        launch_attempt_version="1",
        artifact_hash=row["artifact_hash"],
        reservation_id=row["reservation_id"],
        reservation_hash=row["reservation_hash"],
        route_id=row["route_id"],
        route_hash=row["route_hash"],
        attempt_id=row["attempt_id"],
        attempt_hash=row["attempt_hash"],
        authorization_id=row["authorization_id"],
        authorization_hash=row["authorization_hash"],
        task_id=row["task_id"],
        worker_id=row["worker_id"],
        worker_class=row["worker_class"],
        worker_version=row["worker_version"],
        operation=row["operation"],
        input_hash=row["input_hash"],
        runtime_binding_id=row["runtime_binding_id"],
        runtime_binding_version=row["runtime_binding_version"],
        runtime_binding_hash=row["runtime_binding_hash"],
        idempotency_key=row["idempotency_key"],
        recorded_at=row["recorded_at"],
        must_start_by=row["must_start_by"],
        launcher_actor_id=row["launcher_actor_id"],
        launcher_actor_type=row["launcher_actor_type"],
        launcher_actor_context=row["launcher_actor_context"],
        status=status,
    )
    if not artifact.verify_hash():
        raise ExecutionStartIntegrityError(
            f"launch attempt {artifact.launch_attempt_id} failed hash "
            f"verification on read; refusing to return tampered artifact")
    canonical = canonical_json(artifact.to_canonical_dict())
    if sha256_text(canonical) != row["payload_sha256"]:
        raise ExecutionStartIntegrityError(
            f"launch attempt {artifact.launch_attempt_id} payload/linkage hash "
            f"mismatch on read; refusing to return tampered artifact")
    return artifact
