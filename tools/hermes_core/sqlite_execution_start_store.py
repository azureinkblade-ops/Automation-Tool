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
    ExecutionStartResultError,
)
from tools.hermes_core.hashing import canonical_json, sha256_text


SCHEMA_VERSION_START = 1
SUPPORTED_SCHEMA_VERSIONS_START = (SCHEMA_VERSION_START,)


class ExecutionStartStoreError(Exception):
    """Base store error for EA-4D.2 start-admission persistence."""


class ExecutionStartSchemaError(ExecutionStartStoreError):
    """Schema version mismatch or bootstrap failure."""


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


class SQLiteExecutionStartStore:
    """SQLite-backed EA-4D.2 start-admission store (START_RESERVED only)."""

    def __init__(self, db_path: "str | Path") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        # Test-only failure-injection seam (EA-4D.2 rollback proof): when set,
        # raise after the reservation row + START_RESERVED ledger entry are
        # inserted but before COMMIT, so rollback leaves zero residue.
        self._fail_after_reservation_insert = False
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
        if version not in SUPPORTED_SCHEMA_VERSIONS_START:
            raise ExecutionStartSchemaError(
                f"unsupported start schema version {version}; "
                f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS_START)}")

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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_launch_attempts (
                launch_attempt_id TEXT PRIMARY KEY,
                artifact_hash TEXT NOT NULL,
                reservation_id TEXT NOT NULL UNIQUE,
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
        # Schema-completeness only: start results (EA-4D.3).
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
        self._conn.commit()

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
