"""Durable observational accounting for governed process and model lifecycles.

This module records facts supplied by already-governed boundaries. It has no
authority, activation, binding, receiver selection, or execution capability.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ACCOUNTING_SCHEMA_VERSION = 1
SUPPORTED_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})

PROCESS_EVENT_STATUSES = {
    "PROCESS_START_INTENT": "PENDING",
    "PROCESS_STARTED": "STARTED",
    "PROCESS_START_DENIED": "DENIED",
    "PROCESS_START_FAILED": "FAILED",
    "PROCESS_EXITED": "COMPLETED",
    "PROCESS_ORPHANED": "ORPHANED",
    "PROCESS_RECOVERED": "RECOVERED",
}
MODEL_EVENT_STATUSES = {
    "MODEL_INVOCATION_INTENT": "PENDING",
    "MODEL_INVOCATION_ENTERED": "ENTERED",
    "MODEL_INVOCATION_DENIED": "DENIED",
    "MODEL_INVOCATION_FAILED": "FAILED",
    "MODEL_INVOCATION_COMPLETED": "COMPLETED",
}
PROCESS_COUNT_FIELDS = {
    "process_start_intents": "PROCESS_START_INTENT",
    "process_started": "PROCESS_STARTED",
    "process_start_denied": "PROCESS_START_DENIED",
    "process_start_failed": "PROCESS_START_FAILED",
    "process_exited": "PROCESS_EXITED",
    "process_orphaned": "PROCESS_ORPHANED",
    "process_recovered": "PROCESS_RECOVERED",
}
MODEL_COUNT_FIELDS = {
    "model_invocation_intents": "MODEL_INVOCATION_INTENT",
    "model_invocation_entered": "MODEL_INVOCATION_ENTERED",
    "model_invocation_denied": "MODEL_INVOCATION_DENIED",
    "model_invocation_failed": "MODEL_INVOCATION_FAILED",
    "model_invocation_completed": "MODEL_INVOCATION_COMPLETED",
}


class ProductionAccountingError(RuntimeError):
    """Raised when durable accounting cannot safely accept or reconstruct facts."""


@dataclass(frozen=True)
class ProcessAccountingEvent:
    sequence: int
    event_id: str
    request_id: str
    receiver_id: str
    process_attempt_id: str
    event_type: str
    event_status: str
    correlation_id: str
    created_at: str
    execution_authority_id: str | None
    binding_id: str | None
    process_id: str | None
    process_token: str | None


@dataclass(frozen=True)
class ModelInvocationAccountingEvent:
    sequence: int
    event_id: str
    request_id: str
    receiver_id: str
    model_invocation_attempt_id: str
    event_type: str
    event_status: str
    correlation_id: str
    created_at: str
    model_binding_id: str
    invocation_authorization_id: str | None
    process_id: str | None


class ProductionAccountingLedger:
    """Versioned SQLite event ledger with deterministic, idempotent writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._verify()

    @classmethod
    def initialize(cls, path: str | Path) -> "ProductionAccountingLedger":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(target))) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS accounting_schema_version "
                "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO accounting_schema_version(singleton, version) VALUES(1, ?)",
                (ACCOUNTING_SCHEMA_VERSION,),
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS process_accounting_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                process_attempt_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_status TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                execution_authority_id TEXT,
                binding_id TEXT,
                process_id TEXT,
                process_token TEXT
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_invocation_accounting_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                model_invocation_attempt_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_status TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model_binding_id TEXT NOT NULL,
                invocation_authorization_id TEXT,
                process_id TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS process_events_request_idx "
                "ON process_accounting_events(request_id, sequence)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS model_events_request_idx "
                "ON model_invocation_accounting_events(request_id, sequence)"
            )
        return cls(target)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _verify(self) -> None:
        if not self.path.is_file():
            raise ProductionAccountingError("ACCOUNTING_STORE_MISSING")
        try:
            with closing(self._connect()) as connection, connection:
                row = connection.execute(
                    "SELECT version FROM accounting_schema_version WHERE singleton=1"
                ).fetchone()
                if row is None or row["version"] != ACCOUNTING_SCHEMA_VERSION:
                    raise ProductionAccountingError("ACCOUNTING_SCHEMA_MISMATCH")
                required = {"process_accounting_events", "model_invocation_accounting_events"}
                present = {
                    item["name"]
                    for item in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not required.issubset(present):
                    raise ProductionAccountingError("ACCOUNTING_SCHEMA_MISMATCH")
        except sqlite3.Error as exc:
            raise ProductionAccountingError("ACCOUNTING_STORE_INVALID") from exc

    def record_process_event(
        self,
        *,
        request_id: str,
        receiver_id: str,
        process_attempt_id: str,
        event_type: str,
        correlation_id: str,
        created_at: str,
        execution_authority_id: str | None = None,
        binding_id: str | None = None,
        process_id: str | None = None,
        process_token: str | None = None,
    ) -> ProcessAccountingEvent:
        self._validate_common(request_id, receiver_id, process_attempt_id, correlation_id, created_at)
        if event_type not in PROCESS_EVENT_STATUSES:
            raise ProductionAccountingError("UNSUPPORTED_PROCESS_EVENT")
        if event_type == "PROCESS_START_INTENT" and (
            not execution_authority_id or not binding_id
        ):
            raise ProductionAccountingError("PROCESS_GOVERNED_REFERENCES_REQUIRED")
        if event_type in {"PROCESS_STARTED", "PROCESS_EXITED", "PROCESS_ORPHANED", "PROCESS_RECOVERED"}:
            if not process_id or not process_token:
                raise ProductionAccountingError("PROCESS_IDENTITY_REQUIRED")
        material = {
            "domain": "process",
            "request_id": request_id,
            "receiver_id": receiver_id,
            "attempt_id": process_attempt_id,
            "event_type": event_type,
        }
        event_id = self._event_id(material)
        values = (
            event_id, request_id, receiver_id, process_attempt_id, event_type,
            PROCESS_EVENT_STATUSES[event_type], correlation_id, created_at,
            execution_authority_id, binding_id, process_id, process_token,
        )
        try:
            with closing(self._connect()) as connection, connection:
                self._validate_process_transition(connection, request_id, process_attempt_id, event_type)
                connection.execute(
                    """INSERT OR IGNORE INTO process_accounting_events
                    (event_id, request_id, receiver_id, process_attempt_id, event_type,
                     event_status, correlation_id, created_at, execution_authority_id,
                     binding_id, process_id, process_token)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                row = connection.execute(
                    "SELECT * FROM process_accounting_events WHERE event_id=?", (event_id,)
                ).fetchone()
                self._assert_row_matches(row, values, "process")
                self._validate_process_identity(connection, request_id, process_attempt_id)
        except sqlite3.Error as exc:
            raise ProductionAccountingError("PROCESS_ACCOUNTING_WRITE_FAILED") from exc
        return self._process_event(row)

    def record_model_event(
        self,
        *,
        request_id: str,
        receiver_id: str,
        model_invocation_attempt_id: str,
        event_type: str,
        correlation_id: str,
        created_at: str,
        model_binding_id: str,
        invocation_authorization_id: str | None = None,
        process_id: str | None = None,
    ) -> ModelInvocationAccountingEvent:
        self._validate_common(
            request_id, receiver_id, model_invocation_attempt_id, correlation_id, created_at
        )
        if not model_binding_id:
            raise ProductionAccountingError("MODEL_BINDING_ID_REQUIRED")
        if event_type not in MODEL_EVENT_STATUSES:
            raise ProductionAccountingError("UNSUPPORTED_MODEL_EVENT")
        if event_type == "MODEL_INVOCATION_INTENT" and not invocation_authorization_id:
            raise ProductionAccountingError("MODEL_INVOCATION_AUTHORIZATION_REQUIRED")
        material = {
            "domain": "model",
            "request_id": request_id,
            "receiver_id": receiver_id,
            "attempt_id": model_invocation_attempt_id,
            "event_type": event_type,
        }
        event_id = self._event_id(material)
        values = (
            event_id, request_id, receiver_id, model_invocation_attempt_id, event_type,
            MODEL_EVENT_STATUSES[event_type], correlation_id, created_at, model_binding_id,
            invocation_authorization_id, process_id,
        )
        try:
            with closing(self._connect()) as connection, connection:
                self._validate_model_transition(
                    connection, request_id, model_invocation_attempt_id, event_type
                )
                connection.execute(
                    """INSERT OR IGNORE INTO model_invocation_accounting_events
                    (event_id, request_id, receiver_id, model_invocation_attempt_id,
                     event_type, event_status, correlation_id, created_at, model_binding_id,
                     invocation_authorization_id, process_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                row = connection.execute(
                    "SELECT * FROM model_invocation_accounting_events WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                self._assert_row_matches(row, values, "model")
                self._validate_model_identity(connection, request_id, model_invocation_attempt_id)
        except sqlite3.Error as exc:
            raise ProductionAccountingError("MODEL_ACCOUNTING_WRITE_FAILED") from exc
        return self._model_event(row)

    def process_counts(self, request_id: str | None = None) -> dict[str, int]:
        return self._counts("process_accounting_events", PROCESS_EVENT_STATUSES, request_id)

    def model_invocation_counts(self, request_id: str | None = None) -> dict[str, int]:
        return self._counts(
            "model_invocation_accounting_events", MODEL_EVENT_STATUSES, request_id
        )

    def events_for_request(
        self, request_id: str
    ) -> tuple[list[ProcessAccountingEvent], list[ModelInvocationAccountingEvent]]:
        if not request_id:
            raise ProductionAccountingError("REQUEST_ID_REQUIRED")
        with closing(self._connect()) as connection, connection:
            process_rows = connection.execute(
                "SELECT * FROM process_accounting_events WHERE request_id=? ORDER BY sequence",
                (request_id,),
            ).fetchall()
            model_rows = connection.execute(
                "SELECT * FROM model_invocation_accounting_events WHERE request_id=? ORDER BY sequence",
                (request_id,),
            ).fetchall()
        process_events = [self._process_event(row) for row in process_rows]
        model_events = [self._model_event(row) for row in model_rows]
        self._validate_loaded_events(process_events, model_events)
        return process_events, model_events

    def canonical_counts(self, request_id: str | None = None) -> dict[str, int]:
        process = self.process_counts(request_id)
        model = self.model_invocation_counts(request_id)
        return {
            **{name: process[event_type] for name, event_type in PROCESS_COUNT_FIELDS.items()},
            **{name: model[event_type] for name, event_type in MODEL_COUNT_FIELDS.items()},
        }

    def unresolved_process_attempts(self) -> list[str]:
        return self._unresolved_attempts(
            "process_accounting_events", "process_attempt_id", "PROCESS_START_INTENT",
            {"PROCESS_START_DENIED", "PROCESS_START_FAILED", "PROCESS_EXITED", "PROCESS_RECOVERED"},
        )

    def unresolved_model_attempts(self) -> list[str]:
        return self._unresolved_attempts(
            "model_invocation_accounting_events", "model_invocation_attempt_id",
            "MODEL_INVOCATION_INTENT",
            {"MODEL_INVOCATION_DENIED", "MODEL_INVOCATION_FAILED", "MODEL_INVOCATION_COMPLETED"},
        )

    def _counts(
        self, table: str, event_types: dict[str, str], request_id: str | None
    ) -> dict[str, int]:
        where = " WHERE request_id=?" if request_id is not None else ""
        args: tuple[Any, ...] = (request_id,) if request_id is not None else ()
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"SELECT * FROM {table}{where} ORDER BY sequence",
                args,
            ).fetchall()
        if table == "process_accounting_events":
            process_events = [self._process_event(row) for row in rows]
            self._validate_loaded_events(process_events, [])
        else:
            model_events = [self._model_event(row) for row in rows]
            self._validate_loaded_events([], model_events)
        found = {event_type: 0 for event_type in event_types}
        for row in rows:
            found[row["event_type"]] += 1
        return {event_type: found.get(event_type, 0) for event_type in event_types}

    def _unresolved_attempts(
        self, table: str, attempt_column: str, intent: str, terminal: set[str]
    ) -> list[str]:
        placeholders = ",".join("?" for _ in terminal)
        query = (
            f"SELECT DISTINCT i.{attempt_column} FROM {table} i "
            f"WHERE i.event_type=? AND NOT EXISTS (SELECT 1 FROM {table} t "
            f"WHERE t.request_id=i.request_id AND t.{attempt_column}=i.{attempt_column} "
            f"AND t.event_type IN ({placeholders})) ORDER BY i.{attempt_column}"
        )
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, (intent, *sorted(terminal))).fetchall()
        return [row[attempt_column] for row in rows]

    @staticmethod
    def _validate_common(
        request_id: str,
        receiver_id: str,
        attempt_id: str,
        correlation_id: str,
        created_at: str,
    ) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (
            request_id, receiver_id, attempt_id, correlation_id, created_at
        )):
            raise ProductionAccountingError("MALFORMED_ACCOUNTING_EVENT")
        if receiver_id not in SUPPORTED_RECEIVERS:
            raise ProductionAccountingError("UNSUPPORTED_RECEIVER")

    @staticmethod
    def _event_id(material: dict[str, str]) -> str:
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _event_types(
        connection: sqlite3.Connection, table: str, request_id: str, attempt_column: str,
        attempt_id: str,
    ) -> set[str]:
        rows = connection.execute(
            f"SELECT event_type FROM {table} WHERE request_id=? AND {attempt_column}=?",
            (request_id, attempt_id),
        ).fetchall()
        return {row["event_type"] for row in rows}

    def _validate_process_transition(
        self, connection: sqlite3.Connection, request_id: str, attempt_id: str, event_type: str
    ) -> None:
        seen = self._event_types(
            connection, "process_accounting_events", request_id, "process_attempt_id", attempt_id
        )
        if event_type in seen:
            return
        if event_type in {"PROCESS_START_DENIED", "PROCESS_START_FAILED"}:
            if "PROCESS_START_INTENT" not in seen:
                raise ProductionAccountingError("PROCESS_INTENT_REQUIRED")
            if "PROCESS_STARTED" in seen:
                raise ProductionAccountingError("PROCESS_TERMINAL_CONFLICT")
        if event_type == "PROCESS_STARTED" and "PROCESS_START_INTENT" not in seen:
            raise ProductionAccountingError("PROCESS_INTENT_REQUIRED")
        if event_type == "PROCESS_STARTED" and seen.intersection(
            {"PROCESS_START_DENIED", "PROCESS_START_FAILED"}
        ):
            raise ProductionAccountingError("PROCESS_TERMINAL_CONFLICT")
        if event_type in {"PROCESS_EXITED", "PROCESS_ORPHANED", "PROCESS_RECOVERED"} and "PROCESS_STARTED" not in seen:
            raise ProductionAccountingError("PROCESS_STARTED_REQUIRED")
        if event_type == "PROCESS_RECOVERED" and "PROCESS_ORPHANED" not in seen:
            raise ProductionAccountingError("PROCESS_ORPHANED_REQUIRED")

    def _validate_model_transition(
        self, connection: sqlite3.Connection, request_id: str, attempt_id: str, event_type: str
    ) -> None:
        seen = self._event_types(
            connection, "model_invocation_accounting_events", request_id,
            "model_invocation_attempt_id", attempt_id,
        )
        if event_type in seen:
            return
        if event_type == "MODEL_INVOCATION_DENIED":
            if "MODEL_INVOCATION_INTENT" not in seen:
                raise ProductionAccountingError("MODEL_INTENT_REQUIRED")
            if "MODEL_INVOCATION_ENTERED" in seen:
                raise ProductionAccountingError("MODEL_TERMINAL_CONFLICT")
        if event_type == "MODEL_INVOCATION_ENTERED" and "MODEL_INVOCATION_INTENT" not in seen:
            raise ProductionAccountingError("MODEL_INTENT_REQUIRED")
        if event_type == "MODEL_INVOCATION_ENTERED" and "MODEL_INVOCATION_DENIED" in seen:
            raise ProductionAccountingError("MODEL_TERMINAL_CONFLICT")
        if event_type in {"MODEL_INVOCATION_FAILED", "MODEL_INVOCATION_COMPLETED"} and "MODEL_INVOCATION_ENTERED" not in seen:
            raise ProductionAccountingError("MODEL_ENTERED_REQUIRED")
        if event_type == "MODEL_INVOCATION_FAILED" and "MODEL_INVOCATION_COMPLETED" in seen:
            raise ProductionAccountingError("MODEL_TERMINAL_CONFLICT")
        if event_type == "MODEL_INVOCATION_COMPLETED" and "MODEL_INVOCATION_FAILED" in seen:
            raise ProductionAccountingError("MODEL_TERMINAL_CONFLICT")

    @staticmethod
    def _validate_process_identity(
        connection: sqlite3.Connection, request_id: str, attempt_id: str
    ) -> None:
        rows = connection.execute(
            "SELECT DISTINCT process_id, process_token FROM process_accounting_events "
            "WHERE request_id=? AND process_attempt_id=? AND process_id IS NOT NULL",
            (request_id, attempt_id),
        ).fetchall()
        if len(rows) > 1:
            raise ProductionAccountingError("PROCESS_IDENTITY_CONFLICT")

    @staticmethod
    def _validate_model_identity(
        connection: sqlite3.Connection, request_id: str, attempt_id: str
    ) -> None:
        rows = connection.execute(
            "SELECT DISTINCT receiver_id, model_binding_id "
            "FROM model_invocation_accounting_events "
            "WHERE request_id=? AND model_invocation_attempt_id=?",
            (request_id, attempt_id),
        ).fetchall()
        if len(rows) > 1:
            raise ProductionAccountingError("MODEL_IDENTITY_CONFLICT")
        process_rows = connection.execute(
            "SELECT DISTINCT process_id FROM model_invocation_accounting_events "
            "WHERE request_id=? AND model_invocation_attempt_id=? AND process_id IS NOT NULL",
            (request_id, attempt_id),
        ).fetchall()
        if len(process_rows) > 1:
            raise ProductionAccountingError("MODEL_IDENTITY_CONFLICT")

    @staticmethod
    def _assert_row_matches(row: sqlite3.Row | None, values: tuple[Any, ...], domain: str) -> None:
        if row is None:
            raise ProductionAccountingError("ACCOUNTING_EVENT_NOT_PERSISTED")
        columns = (
            ("event_id", "request_id", "receiver_id", "process_attempt_id", "event_type",
             "event_status", "correlation_id", "created_at", "execution_authority_id",
             "binding_id", "process_id", "process_token")
            if domain == "process"
            else ("event_id", "request_id", "receiver_id", "model_invocation_attempt_id",
                  "event_type", "event_status", "correlation_id", "created_at",
                  "model_binding_id", "invocation_authorization_id", "process_id")
        )
        persisted = tuple(row[column] for column in columns)
        created_at_index = columns.index("created_at")
        if (
            persisted[:created_at_index] + persisted[created_at_index + 1:]
            != values[:created_at_index] + values[created_at_index + 1:]
        ):
            raise ProductionAccountingError("ACCOUNTING_EVENT_CONFLICT")

    def _validate_loaded_events(
        self,
        process_events: Iterable[ProcessAccountingEvent],
        model_events: Iterable[ModelInvocationAccountingEvent],
    ) -> None:
        for event in process_events:
            expected = self._event_id({
                "domain": "process", "request_id": event.request_id,
                "receiver_id": event.receiver_id, "attempt_id": event.process_attempt_id,
                "event_type": event.event_type,
            })
            if (
                event.event_id != expected
                or event.event_type not in PROCESS_EVENT_STATUSES
                or event.event_status != PROCESS_EVENT_STATUSES[event.event_type]
                or event.receiver_id not in SUPPORTED_RECEIVERS
                or not all((event.request_id, event.process_attempt_id, event.correlation_id,
                            event.created_at))
            ):
                raise ProductionAccountingError("MALFORMED_ACCOUNTING_RECORD")
        for event in model_events:
            expected = self._event_id({
                "domain": "model", "request_id": event.request_id,
                "receiver_id": event.receiver_id,
                "attempt_id": event.model_invocation_attempt_id,
                "event_type": event.event_type,
            })
            if (
                event.event_id != expected
                or event.event_type not in MODEL_EVENT_STATUSES
                or event.event_status != MODEL_EVENT_STATUSES[event.event_type]
                or event.receiver_id not in SUPPORTED_RECEIVERS
                or not all((event.request_id, event.model_invocation_attempt_id,
                            event.correlation_id, event.created_at, event.model_binding_id))
            ):
                raise ProductionAccountingError("MALFORMED_ACCOUNTING_RECORD")

    @staticmethod
    def _process_event(row: sqlite3.Row) -> ProcessAccountingEvent:
        return ProcessAccountingEvent(
            **{name: row[name] for name in ProcessAccountingEvent.__dataclass_fields__}
        )

    @staticmethod
    def _model_event(row: sqlite3.Row) -> ModelInvocationAccountingEvent:
        return ModelInvocationAccountingEvent(
            **{name: row[name] for name in ModelInvocationAccountingEvent.__dataclass_fields__}
        )
