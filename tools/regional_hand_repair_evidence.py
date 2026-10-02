"""EA-4D.4F durable Regional Hand Repair pilot workload evidence.

This module implements the smallest durable evidence layer needed for
crash/recovery and duplicate prevention for the Regional Hand Repair pilot.

It does NOT duplicate Hermes authority truth. It may reference:
- pilot_request_id / repair_execution_id
- execution_authorization_id
- execution_attempt_id
- worker_route_id
- launch_attempt_id
- start_result_id
- projection_id

But those remain owned by their respective Hermes artifacts.

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    .hermes/handoffs/ea4d4f/step-1-workflow-manifest.md

Authority limits:
    CPU-only. No GPU, no ComfyUI client, no submission.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"

REPAIR_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS repair_runs (
    launch_attempt_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    repair_execution_id TEXT NOT NULL,
    task_input_sha256 TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    worker_version TEXT NOT NULL,
    runtime_binding_id TEXT NOT NULL,
    runtime_run_id TEXT,
    state TEXT NOT NULL,
    result_json TEXT,
    result_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

REPAIR_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS repair_events (
    event_id TEXT PRIMARY KEY,
    launch_attempt_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (launch_attempt_id, sequence_no)
);
"""

# Allowed monotonic workload states
ALLOWED_STATES = frozenset({
    "RECORDED",
    "SUBMITTING",
    "STARTED",
    "SUBMISSION_UNKNOWN",
    "FAILED",
    "OUTPUT_CAPTURED",
    "VERIFIED",
})

# Terminal states
TERMINAL_STATES = frozenset({
    "FAILED",
    "VERIFIED",
})

# State transitions: current -> allowed next
ALLOWED_TRANSITIONS: Dict[str, frozenset[str]] = {
    "RECORDED": frozenset({"SUBMITTING", "FAILED"}),
    "SUBMITTING": frozenset({"STARTED", "SUBMISSION_UNKNOWN", "FAILED"}),
    "STARTED": frozenset({"OUTPUT_CAPTURED", "FAILED"}),
    "SUBMISSION_UNKNOWN": frozenset({"STARTED", "FAILED"}),
    "OUTPUT_CAPTURED": frozenset({"VERIFIED", "FAILED"}),
    "VERIFIED": frozenset(),  # terminal
    "FAILED": frozenset(),  # terminal
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EvidenceStoreError(Exception):
    """Base class for evidence store errors."""


class DuplicateRequestError(EvidenceStoreError):
    """A request with the same idempotency key already exists."""


class InvalidStateTransitionError(EvidenceStoreError):
    """An invalid state transition was attempted."""


class RecordNotFoundError(EvidenceStoreError):
    """The requested record was not found."""


# ---------------------------------------------------------------------------
# Evidence store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairRunRecord:
    """A single repair run record."""
    launch_attempt_id: str
    idempotency_key: str
    repair_execution_id: str
    task_input_sha256: str
    worker_id: str
    worker_version: str
    runtime_binding_id: str
    runtime_run_id: Optional[str]
    state: str
    result_json: Optional[str]
    result_sha256: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RepairEventRecord:
    """A single repair event record."""
    event_id: str
    launch_attempt_id: str
    sequence_no: int
    event_type: str
    event_json: str
    previous_event_sha256: Optional[str]
    event_sha256: str
    created_at: str


class RegionalHandRepairEvidenceStore:
    """Durable evidence store for Regional Hand Repair pilot.

    This store records workload evidence only. It cannot grant authorization,
    route work, create a launch attempt, or project authority lifecycle state.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(REPAIR_RUNS_TABLE)
            self._conn.execute(REPAIR_EVENTS_TABLE)
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __enter__(self) -> RegionalHandRepairEvidenceStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def _now(self) -> str:
        """Return current UTC timestamp in canonical format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _compute_event_hash(
        self,
        launch_attempt_id: str,
        sequence_no: int,
        event_type: str,
        event_json: str,
        previous_event_sha256: Optional[str],
        created_at: str,
    ) -> str:
        """Compute deterministic hash for an event."""
        payload = {
            "launch_attempt_id": launch_attempt_id,
            "sequence_no": sequence_no,
            "event_type": event_type,
            "event_json": event_json,
            "previous_event_sha256": previous_event_sha256,
            "created_at": created_at,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _get_next_sequence_no(self, launch_attempt_id: str) -> int:
        """Get the next sequence number for a launch attempt."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM repair_events "
                "WHERE launch_attempt_id = ?",
                (launch_attempt_id,),
            )
            return cursor.fetchone()[0]

    def _get_last_event_hash(self, launch_attempt_id: str) -> Optional[str]:
        """Get the hash of the last event for a launch attempt."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT event_sha256 FROM repair_events "
                "WHERE launch_attempt_id = ? "
                "ORDER BY sequence_no DESC LIMIT 1",
                (launch_attempt_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def create_repair_run(
        self,
        *,
        launch_attempt_id: str,
        idempotency_key: str,
        repair_execution_id: str,
        task_input_sha256: str,
        worker_id: str,
        worker_version: str,
        runtime_binding_id: str,
    ) -> RepairRunRecord:
        """Create a new repair run record.

        Raises:
            DuplicateRequestError: if a record with the same idempotency key exists.
        """
        with self._lock:
            now = self._now()
            try:
                self._conn.execute(
                    """INSERT INTO repair_runs
                       (launch_attempt_id, idempotency_key, repair_execution_id,
                        task_input_sha256, worker_id, worker_version, runtime_binding_id,
                        state, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        launch_attempt_id,
                        idempotency_key,
                        repair_execution_id,
                        task_input_sha256,
                        worker_id,
                        worker_version,
                        runtime_binding_id,
                        "RECORDED",
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateRequestError(
                    f"repair run with idempotency key {idempotency_key!r} already exists"
                ) from exc

            return self.get_repair_run(launch_attempt_id)

    def get_repair_run(self, launch_attempt_id: str) -> Optional[RepairRunRecord]:
        """Get a repair run by launch attempt ID."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM repair_runs WHERE launch_attempt_id = ?",
                (launch_attempt_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return RepairRunRecord(
                launch_attempt_id=row[0],
                idempotency_key=row[1],
                repair_execution_id=row[2],
                task_input_sha256=row[3],
                worker_id=row[4],
                worker_version=row[5],
                runtime_binding_id=row[6],
                runtime_run_id=row[7],
                state=row[8],
                result_json=row[9],
                result_sha256=row[10],
                created_at=row[11],
                updated_at=row[12],
            )

    def get_repair_run_by_idempotency(self, idempotency_key: str) -> Optional[RepairRunRecord]:
        """Get a repair run by idempotency key."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM repair_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return RepairRunRecord(
                launch_attempt_id=row[0],
                idempotency_key=row[1],
                repair_execution_id=row[2],
                task_input_sha256=row[3],
                worker_id=row[4],
                worker_version=row[5],
                runtime_binding_id=row[6],
                runtime_run_id=row[7],
                state=row[8],
                result_json=row[9],
                result_sha256=row[10],
                created_at=row[11],
                updated_at=row[12],
            )

    def transition_state(
        self,
        launch_attempt_id: str,
        new_state: str,
        *,
        runtime_run_id: Optional[str] = None,
        result_json: Optional[str] = None,
        result_sha256: Optional[str] = None,
    ) -> RepairRunRecord:
        """Transition a repair run to a new state.

        Fields are only updated when explicitly provided (not None).

        Raises:
            RecordNotFoundError: if the run does not exist.
            InvalidStateTransitionError: if the transition is not allowed.
        """
        with self._lock:
            run = self.get_repair_run(launch_attempt_id)
            if run is None:
                raise RecordNotFoundError(
                    f"repair run {launch_attempt_id!r} not found"
                )

            if new_state not in ALLOWED_STATES:
                raise InvalidStateTransitionError(
                    f"unknown state: {new_state!r}"
                )

            allowed_next = ALLOWED_TRANSITIONS.get(run.state, frozenset())
            if new_state not in allowed_next:
                raise InvalidStateTransitionError(
                    f"cannot transition from {run.state!r} to {new_state!r}"
                )

            now = self._now()
            # Build update dynamically to avoid overwriting fields with None
            updates = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state, now]
            if runtime_run_id is not None:
                updates.append("runtime_run_id = ?")
                params.append(runtime_run_id)
            if result_json is not None:
                updates.append("result_json = ?")
                params.append(result_json)
            if result_sha256 is not None:
                updates.append("result_sha256 = ?")
                params.append(result_sha256)
            params.append(launch_attempt_id)
            self._conn.execute(
                f"UPDATE repair_runs SET {', '.join(updates)} WHERE launch_attempt_id = ?",
                params,
            )
            self._conn.commit()

            return self.get_repair_run(launch_attempt_id)

    def append_event(
        self,
        launch_attempt_id: str,
        event_type: str,
        event_json: str,
    ) -> RepairEventRecord:
        """Append an event to the event chain."""
        with self._lock:
            sequence_no = self._get_next_sequence_no(launch_attempt_id)
            previous_hash = self._get_last_event_hash(launch_attempt_id)
            now = self._now()
            event_hash = self._compute_event_hash(
                launch_attempt_id, sequence_no, event_type, event_json, previous_hash, now
            )
            event_id = f"evt-{launch_attempt_id[:16]}-{sequence_no:04d}"

            self._conn.execute(
                """INSERT INTO repair_events
                   (event_id, launch_attempt_id, sequence_no, event_type, event_json,
                    previous_event_sha256, event_sha256, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    launch_attempt_id,
                    sequence_no,
                    event_type,
                    event_json,
                    previous_hash,
                    event_hash,
                    now,
                ),
            )
            self._conn.commit()

            return RepairEventRecord(
                event_id=event_id,
                launch_attempt_id=launch_attempt_id,
                sequence_no=sequence_no,
                event_type=event_type,
                event_json=event_json,
                previous_event_sha256=previous_hash,
                event_sha256=event_hash,
                created_at=now,
            )

    def get_events(self, launch_attempt_id: str) -> List[RepairEventRecord]:
        """Get all events for a launch attempt."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM repair_events WHERE launch_attempt_id = ? ORDER BY sequence_no",
                (launch_attempt_id,),
            )
            return [
                RepairEventRecord(
                    event_id=row[0],
                    launch_attempt_id=row[1],
                    sequence_no=row[2],
                    event_type=row[3],
                    event_json=row[4],
                    previous_event_sha256=row[5],
                    event_sha256=row[6],
                    created_at=row[7],
                )
                for row in cursor.fetchall()
            ]

    def verify_event_chain(self, launch_attempt_id: str) -> bool:
        """Verify the integrity of the event chain."""
        with self._lock:
            events = self.get_events(launch_attempt_id)
            for i, event in enumerate(events):
                if i == 0:
                    if event.previous_event_sha256 is not None:
                        return False
                else:
                    if event.previous_event_sha256 != events[i - 1].event_sha256:
                        return False

                # Recompute hash
                expected_hash = self._compute_event_hash(
                    event.launch_attempt_id,
                    event.sequence_no,
                    event.event_type,
                    event.event_json,
                    event.previous_event_sha256,
                    event.created_at,
                )
                if expected_hash != event.event_sha256:
                    return False

            return True
