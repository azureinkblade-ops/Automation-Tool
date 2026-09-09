"""Durable single-use production-activation authorization state."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


STORE_SCHEMA_VERSION = "1"
AUTH_STATES = frozenset({"ISSUED", "CLAIMED", "CONSUMED", "ABORTED", "EXPIRED", "DENIED"})
OUTSTANDING_STATES = frozenset({"ISSUED", "CLAIMED"})


class ProductionActivationAuthorizationStoreError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ProductionActivationAuthorizationStore:
    """SQLite state owner. Construction reopens; only the bootstrapper creates."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_STORE_MISSING")
        self._validate_schema()

    @classmethod
    def _initialize(cls, path: str | Path) -> "ProductionActivationAuthorizationStore":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(target), timeout=5.0)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS activation_auth_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS production_activation_authorizations (
                activation_authorization_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                nonce TEXT NOT NULL UNIQUE,
                artifact_hash TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                state TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS production_activation_authorization_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                activation_authorization_id TEXT,
                request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                detail TEXT NOT NULL
                )"""
            )
            connection.execute(
                "INSERT OR REPLACE INTO activation_auth_metadata(key, value) VALUES ('schema_version', ?)",
                (STORE_SCHEMA_VERSION,),
            )
        return cls(target)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_schema(self) -> None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT value FROM activation_auth_metadata WHERE key='schema_version'"
                ).fetchone()
                if row is None or row["value"] != STORE_SCHEMA_VERSION:
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_AUTH_STORE_SCHEMA_MISMATCH"
                    )
                required = {
                    "production_activation_authorizations",
                    "production_activation_authorization_events",
                }
                present = {
                    item["name"]
                    for item in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not required.issubset(present):
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_AUTH_STORE_SCHEMA_MISMATCH"
                    )
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_INVALID"
            ) from exc

    def persist_issued(self, artifact: Any, created_at: str) -> None:
        payload = artifact.to_dict()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                outstanding = connection.execute(
                    "SELECT 1 FROM production_activation_authorizations WHERE state IN ('ISSUED','CLAIMED') LIMIT 1"
                ).fetchone()
                if outstanding is not None:
                    raise ProductionActivationAuthorizationStoreError(
                        "CONFLICTING_OUTSTANDING_AUTH"
                    )
                connection.execute(
                    """INSERT INTO production_activation_authorizations
                    (activation_authorization_id, request_id, receiver_id, nonce,
                     artifact_hash, artifact_json, state, issued_at, expires_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'ISSUED', ?, ?, ?)""",
                    (
                        artifact.activation_authorization_id,
                        artifact.request_id,
                        artifact.receiver_id,
                        artifact.nonce,
                        artifact.artifact_hash,
                        encoded,
                        artifact.issued_at,
                        artifact.expires_at,
                        created_at,
                    ),
                )
                self._insert_event(
                    connection,
                    artifact.activation_authorization_id,
                    artifact.request_id,
                    artifact.receiver_id,
                    "ACTIVATION_AUTH_REQUESTED",
                    created_at,
                    "",
                )
                self._insert_event(
                    connection,
                    artifact.activation_authorization_id,
                    artifact.request_id,
                    artifact.receiver_id,
                    "ACTIVATION_AUTH_ISSUED",
                    created_at,
                    "",
                )
                connection.commit()
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.IntegrityError as exc:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY") from exc
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_STORE_WRITE_FAILED") from exc

    def record_denied(self, request: Any, created_at: str, reason: str) -> None:
        request_id = str(getattr(request, "request_id", "") or "UNKNOWN")
        receiver_id = str(getattr(request, "receiver_id", "") or "UNKNOWN")
        with closing(self._connect()) as connection, connection:
            self._insert_event(
                connection, None, request_id, receiver_id,
                "ACTIVATION_AUTH_REQUESTED", created_at, "",
            )
            self._insert_event(
                connection, None, request_id, receiver_id,
                "ACTIVATION_AUTH_DENIED", created_at, reason,
            )

    def claim(self, activation_authorization_id: str, now: str) -> str:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._load_row(connection, activation_authorization_id)
                if row["state"] != "ISSUED":
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY")
                if _parse_time(now) >= _parse_time(row["expires_at"]):
                    connection.execute(
                        "UPDATE production_activation_authorizations SET state='EXPIRED', updated_at=? WHERE activation_authorization_id=?",
                        (now, activation_authorization_id),
                    )
                    connection.commit()
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_EXPIRED")
                changed = connection.execute(
                    "UPDATE production_activation_authorizations SET state='CLAIMED', updated_at=? WHERE activation_authorization_id=? AND state='ISSUED'",
                    (now, activation_authorization_id),
                ).rowcount
                if changed != 1:
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY")
                self._insert_event_from_row(
                    connection, row, "ACTIVATION_AUTH_CLAIMED", now, ""
                )
                connection.commit()
                return "CLAIMED"
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_CLAIM_FAILED") from exc

    def consume(self, activation_authorization_id: str, now: str) -> str:
        return self._terminal_transition(
            activation_authorization_id,
            now,
            state="CONSUMED",
            event_type="ACTIVATION_AUTH_CONSUMED",
            failure="CONSUME_PERSISTENCE_FAILED",
        )

    def abort(self, activation_authorization_id: str, now: str) -> str:
        return self._terminal_transition(
            activation_authorization_id,
            now,
            state="ABORTED",
            event_type="ACTIVATION_AUTH_ABORTED",
            failure="ACTIVATION_AUTH_ABORT_FAILED",
        )

    def _terminal_transition(
        self,
        activation_authorization_id: str,
        now: str,
        *,
        state: str,
        event_type: str,
        failure: str,
    ) -> str:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._load_row(connection, activation_authorization_id)
                if row["state"] != "CLAIMED":
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY")
                changed = connection.execute(
                    "UPDATE production_activation_authorizations SET state=?, updated_at=? WHERE activation_authorization_id=? AND state='CLAIMED'",
                    (state, now, activation_authorization_id),
                ).rowcount
                if changed != 1:
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY")
                self._insert_event_from_row(connection, row, event_type, now, "")
                connection.commit()
                return state
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(failure) from exc

    def record_activation_event(
        self,
        artifact: Any,
        event_type: str,
        created_at: str,
    ) -> None:
        if event_type not in {"PRODUCTION_ACTIVATION_ENTERED", "PRODUCTION_ACTIVATION_EXITED"}:
            raise ProductionActivationAuthorizationStoreError("UNSUPPORTED_ACTIVATION_EVENT")
        with closing(self._connect()) as connection, connection:
            self._insert_event(
                connection,
                artifact.activation_authorization_id,
                artifact.request_id,
                artifact.receiver_id,
                event_type,
                created_at,
                "",
            )

    def state(self, activation_authorization_id: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT state FROM production_activation_authorizations WHERE activation_authorization_id=?",
                (activation_authorization_id,),
            ).fetchone()
        return None if row is None else str(row["state"])

    def load_artifact(self, activation_authorization_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = self._load_row(connection, activation_authorization_id)
        payload = json.loads(row["artifact_json"])
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if payload.get("artifact_hash") != row["artifact_hash"] or not encoded:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_STORE_TAMPERED")
        return payload

    def has_outstanding(self) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM production_activation_authorizations WHERE state IN ('ISSUED','CLAIMED') LIMIT 1"
            ).fetchone()
        return row is not None

    def expire_outstanding(self, now: str) -> int:
        """Durably expire stale rows during a new explicit issue action."""
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT * FROM production_activation_authorizations WHERE state='ISSUED'"
                ).fetchall()
                expired = 0
                for row in rows:
                    if _parse_time(now) < _parse_time(row["expires_at"]):
                        continue
                    changed = connection.execute(
                        "UPDATE production_activation_authorizations SET state='EXPIRED', updated_at=? WHERE activation_authorization_id=? AND state='ISSUED'",
                        (now, row["activation_authorization_id"]),
                    ).rowcount
                    expired += changed
                connection.commit()
                return expired
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_WRITE_FAILED"
            ) from exc

    def events_for_request(self, request_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM production_activation_authorization_events WHERE request_id=? ORDER BY sequence",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _load_row(connection: sqlite3.Connection, activation_authorization_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM production_activation_authorizations WHERE activation_authorization_id=?",
            (activation_authorization_id,),
        ).fetchone()
        if row is None:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_NOT_FOUND")
        return row

    def _insert_event_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        event_type: str,
        created_at: str,
        detail: str,
    ) -> None:
        self._insert_event(
            connection,
            row["activation_authorization_id"],
            row["request_id"],
            row["receiver_id"],
            event_type,
            created_at,
            detail,
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        activation_authorization_id: str | None,
        request_id: str,
        receiver_id: str,
        event_type: str,
        created_at: str,
        detail: str,
    ) -> None:
        material = {
            "activation_authorization_id": activation_authorization_id or "",
            "request_id": request_id,
            "receiver_id": receiver_id,
            "event_type": event_type,
            "detail": detail,
        }
        event_id = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """INSERT OR IGNORE INTO production_activation_authorization_events
            (event_id, activation_authorization_id, request_id, receiver_id,
             event_type, created_at, detail) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                activation_authorization_id,
                request_id,
                receiver_id,
                event_type,
                created_at,
                detail,
            ),
        )


class ProductionActivationAuthStoreBootstrapper:
    """Explicit store initializer; never called by import, factory, or runtime."""

    def bootstrap(
        self,
        path: str | Path,
        *,
        bootstrap_explicit: bool,
    ) -> ProductionActivationAuthorizationStore:
        if bootstrap_explicit is not True:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_BOOTSTRAP_NOT_EXPLICIT"
            )
        return ProductionActivationAuthorizationStore._initialize(path)


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("activation authorization time must be timezone-aware")
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProductionActivationAuthorizationStoreError("INVALID_ACTIVATION_AUTH_TIME") from exc
