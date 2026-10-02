"""Durable workload evidence for the regional hand-repair pilot.

This store is separate from governance and execution authority. It records
only workload submission and verification evidence and cannot authorize work.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional


class RepairEvidenceError(RuntimeError):
    pass


class RepairEvidenceConflictError(RepairEvidenceError):
    pass


class RepairEvidenceTransitionError(RepairEvidenceError):
    pass


@dataclass(frozen=True)
class RepairRun:
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
class EventChainReport:
    ok: bool
    checked: int
    failures: tuple[str, ...]


_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS repair_events (
  event_id TEXT PRIMARY KEY,
  launch_attempt_id TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  previous_event_sha256 TEXT,
  event_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (launch_attempt_id, sequence_no),
  FOREIGN KEY (launch_attempt_id) REFERENCES repair_runs(launch_attempt_id)
);
"""

_ALLOWED_TRANSITIONS = {
    "RECORDED": {"SUBMITTING"},
    "SUBMITTING": {"STARTED", "SUBMISSION_UNKNOWN", "FAILED"},
    "STARTED": {"OUTPUT_CAPTURED", "FAILED"},
    "OUTPUT_CAPTURED": {"VERIFIED", "FAILED"},
    "SUBMISSION_UNKNOWN": {"STARTED", "FAILED"},
    "VERIFIED": set(),
    "FAILED": set(),
}


def default_repair_evidence_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RepairEvidenceError("LOCALAPPDATA is required for the default store")
    return Path(local) / "Hermes" / "regional_hand_repair.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Mapping) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


class RegionalHandRepairEvidenceStore:
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        clock: Callable[[], str] = _now,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_repair_evidence_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), isolation_level=None, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @staticmethod
    def _row(row: sqlite3.Row | None) -> RepairRun | None:
        return RepairRun(**dict(row)) if row is not None else None

    def get_by_key(self, idempotency_key: str) -> RepairRun | None:
        with self._connect() as conn:
            return self._row(
                conn.execute(
                    "SELECT * FROM repair_runs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
            )

    def record(
        self,
        *,
        launch_attempt_id: str,
        idempotency_key: str,
        repair_execution_id: str,
        task_input_sha256: str,
        worker_id: str,
        worker_version: str,
        runtime_binding_id: str,
    ) -> RepairRun:
        lineage = (
            launch_attempt_id,
            repair_execution_id,
            task_input_sha256,
            worker_id,
            worker_version,
            runtime_binding_id,
        )
        now = self._clock()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM repair_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                stored = (
                    row["launch_attempt_id"],
                    row["repair_execution_id"],
                    row["task_input_sha256"],
                    row["worker_id"],
                    row["worker_version"],
                    row["runtime_binding_id"],
                )
                if stored != lineage:
                    raise RepairEvidenceConflictError(
                        "idempotency key already maps to different repair lineage"
                    )
                conn.execute("COMMIT")
                return self._row(row)  # type: ignore[return-value]
            conn.execute(
                "INSERT INTO repair_runs VALUES (?, ?, ?, ?, ?, ?, ?, NULL, "
                "'RECORDED', NULL, NULL, ?, ?)",
                (*lineage[:1], idempotency_key, *lineage[1:], now, now),
            )
            self._append_event(conn, launch_attempt_id, "RECORDED", {"state": "RECORDED"}, now)
            conn.execute("COMMIT")
            return self.get_by_key(idempotency_key)  # type: ignore[return-value]
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def transition(
        self,
        idempotency_key: str,
        new_state: str,
        *,
        runtime_run_id: str | None = None,
        result: Mapping | None = None,
    ) -> RepairRun:
        if new_state not in _ALLOWED_TRANSITIONS:
            raise RepairEvidenceTransitionError(f"unknown repair state: {new_state}")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM repair_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise RepairEvidenceTransitionError("repair run is not recorded")
            old_state = row["state"]
            if old_state == new_state:
                conn.execute("COMMIT")
                return self._row(row)  # type: ignore[return-value]
            if new_state not in _ALLOWED_TRANSITIONS[old_state]:
                raise RepairEvidenceTransitionError(
                    f"invalid repair state transition {old_state} -> {new_state}"
                )
            result_json = _canonical_json(result) if result is not None else row["result_json"]
            result_sha256 = _sha256(result_json) if result_json is not None else row["result_sha256"]
            run_id = runtime_run_id if runtime_run_id is not None else row["runtime_run_id"]
            now = self._clock()
            conn.execute(
                "UPDATE repair_runs SET runtime_run_id = ?, state = ?, result_json = ?, "
                "result_sha256 = ?, updated_at = ? WHERE idempotency_key = ?",
                (run_id, new_state, result_json, result_sha256, now, idempotency_key),
            )
            event = {"state": new_state, "runtime_run_id": run_id, "result_sha256": result_sha256}
            self._append_event(conn, row["launch_attempt_id"], new_state, event, now)
            conn.execute("COMMIT")
            return self.get_by_key(idempotency_key)  # type: ignore[return-value]
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _append_event(
        self,
        conn: sqlite3.Connection,
        launch_attempt_id: str,
        event_type: str,
        event: Mapping,
        created_at: str,
    ) -> None:
        row = conn.execute(
            "SELECT sequence_no, event_sha256 FROM repair_events "
            "WHERE launch_attempt_id = ? ORDER BY sequence_no DESC LIMIT 1",
            (launch_attempt_id,),
        ).fetchone()
        sequence_no = (int(row["sequence_no"]) + 1) if row else 1
        previous = row["event_sha256"] if row else None
        event_json = _canonical_json(event)
        preimage = _canonical_json(
            {
                "launch_attempt_id": launch_attempt_id,
                "sequence_no": sequence_no,
                "event_type": event_type,
                "event_json": event_json,
                "previous_event_sha256": previous,
                "created_at": created_at,
            }
        )
        event_sha256 = _sha256(preimage)
        event_id = _sha256(f"{launch_attempt_id}:{sequence_no}:{event_sha256}")
        conn.execute(
            "INSERT INTO repair_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, launch_attempt_id, sequence_no, event_type, event_json,
             previous, event_sha256, created_at),
        )

    def verify_event_chain(self, launch_attempt_id: str) -> EventChainReport:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM repair_events WHERE launch_attempt_id = ? "
                "ORDER BY sequence_no",
                (launch_attempt_id,),
            ).fetchall()
        failures: list[str] = []
        previous = None
        for expected, row in enumerate(rows, start=1):
            if row["sequence_no"] != expected:
                failures.append(f"sequence gap at {row['sequence_no']}")
            if row["previous_event_sha256"] != previous:
                failures.append(f"chain break at {row['sequence_no']}")
            preimage = _canonical_json(
                {
                    "launch_attempt_id": row["launch_attempt_id"],
                    "sequence_no": row["sequence_no"],
                    "event_type": row["event_type"],
                    "event_json": row["event_json"],
                    "previous_event_sha256": row["previous_event_sha256"],
                    "created_at": row["created_at"],
                }
            )
            if _sha256(preimage) != row["event_sha256"]:
                failures.append(f"event hash mismatch at {row['sequence_no']}")
            previous = row["event_sha256"]
        return EventChainReport(not failures, len(rows), tuple(failures))
