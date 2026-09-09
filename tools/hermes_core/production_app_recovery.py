"""Durable, explicit recovery for governed application lifecycle ownership.

This module records only the identities needed to clean stale lifecycle state.
It never starts a process, issues authority, activates production, or retries a
request. Process inspection and termination are injected collaborators.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any


RECOVERY_SCHEMA_VERSION = 1
SUPPORTED_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})
RECOVERY_PHASES = frozenset(
    {
        "ADMISSION_ACQUIRED",
        "BINDING_OWNED",
        "INVOCATION_AUTH_PERSISTED",
        "REQUEST_ENTERED",
        "PROCESS_REGISTERED",
        "PROCESS_STARTED",
        "TEARDOWN_PENDING",
        "CLEAN",
        "RECOVERY_REQUIRED",
        "RECOVERY_FAILED",
    }
)


class ProductionRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductionRecoveryRecord:
    request_id: str
    receiver_id: str
    host_instance_id: str
    admission_owner_id: str
    binding_id: str | None
    enablement_id: str | None
    invocation_authorization_id: str | None
    process_id: str | None
    process_token: str | None
    process_state: str
    lifecycle_phase: str
    cleanup_state: str


@dataclass(frozen=True)
class ProductionRecoveryResult:
    decision: str
    reason: str
    request_id: str
    binding_teardown_count: int = 0
    process_termination_count: int = 0


class ProductionRecoveryStore:
    """SQLite recovery journal; separate from process/model accounting."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._verify()

    @classmethod
    def initialize(cls, path: str | Path) -> "ProductionRecoveryStore":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(target))) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS recovery_schema_version "
                "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO recovery_schema_version(singleton, version) VALUES(1, ?)",
                (RECOVERY_SCHEMA_VERSION,),
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS production_recovery_state (
                request_id TEXT PRIMARY KEY,
                receiver_id TEXT NOT NULL,
                host_instance_id TEXT NOT NULL,
                admission_owner_id TEXT NOT NULL,
                binding_id TEXT,
                enablement_id TEXT,
                invocation_authorization_id TEXT,
                process_id TEXT,
                process_token TEXT,
                process_state TEXT NOT NULL,
                lifecycle_phase TEXT NOT NULL,
                cleanup_state TEXT NOT NULL
                )"""
            )
        return cls(target)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _verify(self) -> None:
        if not self.path.is_file():
            raise ProductionRecoveryError("RECOVERY_STORE_MISSING")
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT version FROM recovery_schema_version WHERE singleton=1"
            ).fetchone()
            if row is None or row["version"] != RECOVERY_SCHEMA_VERSION:
                raise ProductionRecoveryError("RECOVERY_SCHEMA_MISMATCH")

    def begin(self, request_id: str, receiver_id: str, host_instance_id: str) -> None:
        if receiver_id not in SUPPORTED_RECEIVERS:
            raise ProductionRecoveryError("UNSUPPORTED_RECEIVER")
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT cleanup_state FROM production_recovery_state WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                raise ProductionRecoveryError("RECOVERY_RECORD_CONFLICT")
            connection.execute(
                """INSERT INTO production_recovery_state VALUES
                (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 'NOT_REGISTERED',
                 'ADMISSION_ACQUIRED', 'PENDING')""",
                (request_id, receiver_id, host_instance_id, request_id),
            )

    def transition(self, request_id: str, phase: str, **fields: Any) -> None:
        if phase not in RECOVERY_PHASES:
            raise ProductionRecoveryError("INVALID_RECOVERY_PHASE")
        allowed = {
            "binding_id",
            "enablement_id",
            "invocation_authorization_id",
            "process_id",
            "process_token",
            "process_state",
            "cleanup_state",
        }
        if not set(fields).issubset(allowed):
            raise ProductionRecoveryError("INVALID_RECOVERY_FIELD")
        assignments = ["lifecycle_phase=?"]
        values: list[Any] = [phase]
        for name, value in fields.items():
            assignments.append(f"{name}=?")
            values.append(value)
        values.append(request_id)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                f"UPDATE production_recovery_state SET {', '.join(assignments)} "
                "WHERE request_id=?",
                values,
            )
            if cursor.rowcount != 1:
                raise ProductionRecoveryError("RECOVERY_RECORD_MISSING")

    def mark_clean(self, request_id: str) -> None:
        self.transition(request_id, "CLEAN", cleanup_state="CLEAN")

    def mark_failed(self, request_id: str) -> None:
        self.transition(request_id, "RECOVERY_FAILED", cleanup_state="FAILED")

    def load(self, request_id: str) -> ProductionRecoveryRecord | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM production_recovery_state WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def has_unresolved(self) -> bool:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT 1 FROM production_recovery_state "
                "WHERE cleanup_state != 'CLEAN' LIMIT 1"
            ).fetchone()
        return row is not None

    @staticmethod
    def _record(row: sqlite3.Row) -> ProductionRecoveryRecord:
        return ProductionRecoveryRecord(
            **{name: row[name] for name in ProductionRecoveryRecord.__dataclass_fields__}
        )


class ProductionAppRecoveryOwner:
    """Explicitly reconcile one exact stale lifecycle record."""

    def __init__(
        self,
        store: ProductionRecoveryStore,
        admission_controller: Any,
        binding_controller: Any,
        liveness_inspector: Any,
        process_controller: Any,
        accounting_ledger: Any = None,
        accounting_clock: Any = None,
    ) -> None:
        self._store = store
        self._admission = admission_controller
        self._bindings = binding_controller
        self._liveness = liveness_inspector
        self._processes = process_controller
        self._accounting = accounting_ledger
        self._accounting_clock = accounting_clock

    def reconcile(self, request_id: str) -> ProductionRecoveryResult:
        record = self._store.load(request_id)
        if record is None:
            return self._deny(request_id, "RECOVERY_RECORD_MISSING")
        if record.cleanup_state == "CLEAN":
            return self._allow(request_id, "ALREADY_CLEAN")
        if record.cleanup_state == "FAILED":
            return self._deny(request_id, "RECOVERY_PREVIOUSLY_FAILED")
        if record.receiver_id not in SUPPORTED_RECEIVERS:
            return self._fail(record, "UNSUPPORTED_RECEIVER")
        if self._liveness is None:
            return self._fail(record, "RECOVERY_LIVENESS_UNAVAILABLE")
        if self._liveness.is_host_active(record.host_instance_id):
            return self._deny(request_id, "ACTIVE_LIFECYCLE_OWNER")

        admission_owner = self._admission.owner_request_id
        if admission_owner not in (None, record.admission_owner_id):
            return self._fail(record, "ADMISSION_OWNER_MISMATCH")

        terminated = 0
        torn_down = 0
        if record.process_state == "STARTED":
            self._record_process_accounting(record, "PROCESS_ORPHANED")
            process_result = self._recover_process(record)
            if process_result == "FAILED":
                return self._fail(record, "PROCESS_OWNERSHIP_MISMATCH")
            if process_result == "TERMINATION_FAILED":
                return self._fail(record, "PROCESS_TERMINATION_FAILED")
            terminated = 1 if process_result == "TERMINATED" else 0

        binding_result = self._recover_binding(record)
        if binding_result == "MISMATCH":
            return self._fail(record, "BINDING_IDENTITY_MISMATCH", terminated=terminated)
        if binding_result == "FAILED":
            return self._fail(record, "BINDING_TEARDOWN_FAILED", terminated=terminated)
        torn_down = 1 if binding_result == "TORN_DOWN" else 0

        if (
            admission_owner == record.admission_owner_id
            and not self._admission.release(admission_owner)
        ):
            return self._fail(record, "ADMISSION_RELEASE_FAILED", terminated=terminated)

        self._store.mark_clean(request_id)
        if record.process_state == "STARTED":
            self._record_process_accounting(record, "PROCESS_RECOVERED")
        return ProductionRecoveryResult(
            decision="ALLOW",
            reason="RECOVERED",
            request_id=request_id,
            binding_teardown_count=torn_down,
            process_termination_count=terminated,
        )

    def _record_process_accounting(
        self, record: ProductionRecoveryRecord, event_type: str
    ) -> None:
        if self._accounting is None:
            return
        try:
            if self._accounting_clock is None:
                return
            self._accounting.record_process_event(
                request_id=record.request_id,
                receiver_id=record.receiver_id,
                process_attempt_id=record.process_token or "",
                event_type=event_type,
                correlation_id=record.request_id,
                created_at=self._accounting_clock.now_iso(),
                binding_id=record.binding_id,
                process_id=record.process_id,
                process_token=record.process_token,
            )
        except Exception:
            # Recovery is already post-boundary; accounting cannot skip cleanup.
            return

    def _recover_process(self, record: ProductionRecoveryRecord) -> str:
        if not record.process_id or not record.process_token:
            return "FAILED"
        state = self._liveness.inspect_process(record.process_id, record.process_token)
        if state == "DEAD":
            return "ALREADY_DEAD"
        if state != "ALIVE":
            return "FAILED"
        if self._processes is None:
            return "TERMINATION_FAILED"
        if not self._processes.terminate(record.process_id, record.process_token):
            return "TERMINATION_FAILED"
        return "TERMINATED"

    def _recover_binding(self, record: ProductionRecoveryRecord) -> str:
        if record.binding_id is None:
            return "NONE"
        binding = self._bindings.get_binding_for_receiver(record.receiver_id)
        if binding is None:
            return "ALREADY_CLEAN"
        if (
            binding.binding_id != record.binding_id
            or binding.enablement_id != record.enablement_id
        ):
            return "MISMATCH"
        return "TORN_DOWN" if self._bindings.teardown(binding) else "FAILED"

    def _fail(
        self,
        record: ProductionRecoveryRecord,
        reason: str,
        *,
        terminated: int = 0,
    ) -> ProductionRecoveryResult:
        self._store.mark_failed(record.request_id)
        return ProductionRecoveryResult(
            decision="DENY",
            reason=reason,
            request_id=record.request_id,
            process_termination_count=terminated,
        )

    @staticmethod
    def _allow(request_id: str, reason: str) -> ProductionRecoveryResult:
        return ProductionRecoveryResult("ALLOW", reason, request_id)

    @staticmethod
    def _deny(request_id: str, reason: str) -> ProductionRecoveryResult:
        return ProductionRecoveryResult("DENY", reason, request_id)
