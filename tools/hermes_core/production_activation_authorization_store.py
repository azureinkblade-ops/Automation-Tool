"""Durable single-use production-activation authorization state."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


STORE_SCHEMA_VERSION = "2"
AUTH_STATES = frozenset(
    {"ISSUED", "CLAIMED", "CONSUMED", "ABORTED", "EXPIRED", "DENIED", "CANCELLED", "REVOKED"}
)
OUTSTANDING_STATES = frozenset({"ISSUED", "CLAIMED"})
ANCHOR_SCHEMA_ID = "hermes.production-activation-auth-store-anchor/v1"


class ProductionActivationAuthorizationStoreError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ProductionActivationAuthorizationStore:
    """SQLite state owner. Construction reopens; only the bootstrapper creates."""

    def __init__(self, path: str | Path, anchor_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.anchor_path = Path(anchor_path) if anchor_path is not None else _default_anchor_path(self.path)
        if not self.path.is_file():
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_STORE_MISSING")
        self._validate_schema()

    @classmethod
    def _initialize(
        cls,
        path: str | Path,
        anchor_path: str | Path | None = None,
    ) -> "ProductionActivationAuthorizationStore":
        target = Path(path)
        anchor = Path(anchor_path) if anchor_path is not None else _default_anchor_path(target)
        if target.exists() or anchor.exists():
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_ALREADY_EXISTS"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        anchor.parent.mkdir(parents=True, exist_ok=True)
        store_id = f"activation-store-{uuid.uuid4()}"
        installation_id = f"activation-installation-{uuid.uuid4()}"
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
                """CREATE TABLE IF NOT EXISTS activation_auth_store_lineage (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                store_id TEXT NOT NULL,
                store_epoch INTEGER NOT NULL,
                installation_id TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS production_activation_ceremonies (
                ceremony_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                activation_authorization_id TEXT,
                operator_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                activation_store_id TEXT NOT NULL,
                activation_store_epoch INTEGER NOT NULL,
                executor_binding_id TEXT NOT NULL,
                capability_scope_json TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS production_activation_ceremony_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                ceremony_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                activation_authorization_id TEXT,
                operator_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                activation_store_id TEXT NOT NULL,
                activation_store_epoch INTEGER NOT NULL,
                executor_binding_id TEXT NOT NULL,
                capability_scope_hash TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                detail_code TEXT NOT NULL
                )"""
            )
            connection.execute("DELETE FROM activation_auth_store_lineage")
            connection.execute(
                "INSERT INTO activation_auth_store_lineage VALUES(1, ?, 1, ?)",
                (store_id, installation_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO activation_auth_metadata(key, value) VALUES ('schema_version', ?)",
                (STORE_SCHEMA_VERSION,),
            )
        _write_anchor(anchor, target, store_id, 1, installation_id)
        return cls(target, anchor)

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
                    "activation_auth_store_lineage",
                    "production_activation_ceremonies",
                    "production_activation_ceremony_events",
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
                self._validate_lineage(connection)
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_INVALID"
            ) from exc

    def lineage(self) -> tuple[str, int]:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            row = connection.execute(
                "SELECT store_id, store_epoch FROM activation_auth_store_lineage WHERE singleton=1"
            ).fetchone()
        return str(row["store_id"]), int(row["store_epoch"])

    def _validate_lineage(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT store_id, store_epoch, installation_id FROM activation_auth_store_lineage WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_STORE_ID_MISSING")
        anchor = _read_anchor(self.anchor_path)
        expected = _anchor_fields(
            self.path,
            str(row["store_id"]),
            int(row["store_epoch"]),
            str(row["installation_id"]),
        )
        if anchor != {**expected, "anchor_hash": _anchor_hash(expected)}:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_STORE_ANCHOR_MISMATCH")
        if int(row["store_epoch"]) < 1:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_STORE_EPOCH_MISMATCH")

    def rotate_epoch(self, *, rotate_explicit: bool, now: str) -> int:
        """Invalidate prior artifacts and advance the externally anchored store epoch."""
        if rotate_explicit is not True:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_STORE_ROTATION_NOT_EXPLICIT"
            )
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                row = connection.execute(
                    "SELECT store_id, store_epoch, installation_id "
                    "FROM activation_auth_store_lineage WHERE singleton=1"
                ).fetchone()
                if row is None:
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_STORE_ID_MISSING"
                    )
                outstanding = connection.execute(
                    "SELECT * FROM production_activation_authorizations "
                    "WHERE state IN ('ISSUED','CLAIMED')"
                ).fetchall()
                for authorization in outstanding:
                    connection.execute(
                        "UPDATE production_activation_authorizations "
                        "SET state='ABORTED', updated_at=? "
                        "WHERE activation_authorization_id=? AND state IN ('ISSUED','CLAIMED')",
                        (now, authorization["activation_authorization_id"]),
                    )
                    self._insert_event_from_row(
                        connection,
                        authorization,
                        "ACTIVATION_AUTH_ABORTED",
                        now,
                        "STORE_EPOCH_ROTATED",
                    )
                    self._insert_ceremony_event_from_row(
                        connection,
                        authorization,
                        "ACTIVATION_AUTH_ABORTED",
                        now,
                        "STORE_EPOCH_ROTATED",
                    )
                    self._set_ceremony_state(connection, authorization, "FAILED", now)
                next_epoch = int(row["store_epoch"]) + 1
                connection.execute(
                    "UPDATE activation_auth_store_lineage SET store_epoch=? WHERE singleton=1",
                    (next_epoch,),
                )
                connection.commit()
            _write_anchor(
                self.anchor_path,
                self.path,
                str(row["store_id"]),
                next_epoch,
                str(row["installation_id"]),
            )
            return next_epoch
        except ProductionActivationAuthorizationStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_STORE_ROTATION_FAILED"
            ) from exc

    def restore_from_backup(
        self,
        backup_path: str | Path,
        *,
        restore_explicit: bool,
        now: str,
    ) -> int:
        """Restore historical authorization rows while preserving local lineage."""
        if restore_explicit is not True:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_STORE_RESTORE_NOT_EXPLICIT"
            )
        source_path = Path(backup_path)
        if not source_path.is_file() or source_path.resolve() == self.path.resolve():
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_STORE_RESTORE_SOURCE_INVALID"
            )
        try:
            with closing(sqlite3.connect(str(source_path), timeout=5.0)) as source:
                source.row_factory = sqlite3.Row
                source_rows = source.execute(
                    "SELECT * FROM production_activation_authorizations"
                ).fetchall()
                source_events = source.execute(
                    "SELECT event_id, activation_authorization_id, request_id, receiver_id, "
                    "event_type, created_at, detail "
                    "FROM production_activation_authorization_events ORDER BY sequence"
                ).fetchall()
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                lineage = connection.execute(
                    "SELECT store_id, store_epoch, installation_id "
                    "FROM activation_auth_store_lineage WHERE singleton=1"
                ).fetchone()
                if lineage is None:
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_STORE_ID_MISSING"
                    )
                next_epoch = int(lineage["store_epoch"]) + 1
                connection.execute("DELETE FROM production_activation_ceremony_events")
                connection.execute("DELETE FROM production_activation_ceremonies")
                connection.execute("DELETE FROM production_activation_authorization_events")
                connection.execute("DELETE FROM production_activation_authorizations")
                for source_row in source_rows:
                    state = str(source_row["state"])
                    if state in OUTSTANDING_STATES:
                        state = "ABORTED"
                    connection.execute(
                        """INSERT INTO production_activation_authorizations
                        (activation_authorization_id, request_id, receiver_id, nonce,
                         artifact_hash, artifact_json, state, issued_at, expires_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            source_row["activation_authorization_id"], source_row["request_id"],
                            source_row["receiver_id"], source_row["nonce"],
                            source_row["artifact_hash"], source_row["artifact_json"], state,
                            source_row["issued_at"], source_row["expires_at"], now,
                        ),
                    )
                for event in source_events:
                    connection.execute(
                        """INSERT OR IGNORE INTO production_activation_authorization_events
                        (event_id, activation_authorization_id, request_id, receiver_id,
                         event_type, created_at, detail) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        tuple(event),
                    )
                for source_row in source_rows:
                    if str(source_row["state"]) in OUTSTANDING_STATES:
                        self._insert_event(
                            connection,
                            source_row["activation_authorization_id"],
                            source_row["request_id"],
                            source_row["receiver_id"],
                            "ACTIVATION_AUTH_RESTORE_TERMINALIZED",
                            now,
                            "LEGACY_ACTIVATION_AUTHORIZATION_RETIRED",
                        )
                connection.execute(
                    "UPDATE activation_auth_store_lineage SET store_epoch=? WHERE singleton=1",
                    (next_epoch,),
                )
                connection.commit()
            _write_anchor(
                self.anchor_path,
                self.path,
                str(lineage["store_id"]),
                next_epoch,
                str(lineage["installation_id"]),
            )
            return next_epoch
        except ProductionActivationAuthorizationStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_STORE_RESTORE_FAILED"
            ) from exc

    def persist_issued(self, artifact: Any, created_at: str) -> None:
        payload = artifact.to_dict()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
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
                self._insert_ceremony_event(
                    connection, artifact, "ACTIVATION_AUTH_ISSUED", created_at, ""
                )
                connection.execute(
                    "UPDATE production_activation_ceremonies SET activation_authorization_id=?, state='ISSUED', updated_at=? WHERE ceremony_id=? AND state='BINDING_RESERVED'",
                    (artifact.activation_authorization_id, created_at, artifact.ceremony_id),
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
            self._validate_lineage(connection)
            self._insert_event(
                connection, None, request_id, receiver_id,
                "ACTIVATION_AUTH_REQUESTED", created_at, "",
            )
            self._insert_event(
                connection, None, request_id, receiver_id,
                "ACTIVATION_AUTH_DENIED", created_at, reason,
            )
            if getattr(request, "ceremony_id", None):
                self._insert_ceremony_event(
                    connection, request, "ACTIVATION_AUTH_DENIED", created_at, reason
                )
                connection.execute(
                    "UPDATE production_activation_ceremonies SET state='FAILED', updated_at=? WHERE ceremony_id=?",
                    (created_at, request.ceremony_id),
                )

    def begin_ceremony(self, request: Any, created_at: str) -> None:
        scope_json = json.dumps(list(request.capability_scope), separators=(",", ":"))
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                connection.execute(
                    """INSERT INTO production_activation_ceremonies
                    (ceremony_id, request_id, activation_authorization_id, operator_id,
                     receiver_id, activation_store_id, activation_store_epoch,
                     executor_binding_id, capability_scope_json, state, created_at, updated_at)
                    VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?)""",
                    (
                        request.ceremony_id, request.request_id, request.operator_id,
                        request.receiver_id, request.activation_store_id,
                        request.activation_store_epoch, request.executor_binding_id,
                        scope_json, created_at, created_at,
                    ),
                )
                self._insert_ceremony_event(
                    connection, request, "CEREMONY_REQUESTED", created_at, ""
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ProductionActivationAuthorizationStoreError("CEREMONY_ID_REPLAY") from exc
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "CEREMONY_AUDIT_PERSISTENCE_FAILURE"
            ) from exc

    def record_ceremony_event(
        self,
        artifact_or_request: Any,
        event_type: str,
        created_at: str,
        detail_code: str = "",
        *,
        state: str | None = None,
    ) -> None:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                self._insert_ceremony_event(
                    connection, artifact_or_request, event_type, created_at, detail_code
                )
                if state is not None:
                    connection.execute(
                        "UPDATE production_activation_ceremonies SET state=?, updated_at=? WHERE ceremony_id=?",
                        (state, created_at, artifact_or_request.ceremony_id),
                    )
                connection.commit()
        except ProductionActivationAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "CEREMONY_AUDIT_PERSISTENCE_FAILURE"
            ) from exc

    def claim(self, activation_authorization_id: str, now: str) -> str:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
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
                self._insert_ceremony_event_from_row(
                    connection, row, "ACTIVATION_AUTH_CLAIMED", now, ""
                )
                self._set_ceremony_state(connection, row, "CLAIMED", now)
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

    def cancel(self, activation_authorization_id: str, now: str, reason: str) -> str:
        return self._state_transition(
            activation_authorization_id,
            now,
            expected_state="ISSUED",
            state="CANCELLED",
            event_type="ACTIVATION_AUTH_CANCELLED",
            failure="ACTIVATION_AUTH_CANCEL_FAILED",
            detail=reason,
        )

    def revoke(self, activation_authorization_id: str, now: str, reason: str) -> str:
        return self._state_transition(
            activation_authorization_id,
            now,
            expected_state="CLAIMED",
            state="REVOKED",
            event_type="ACTIVATION_AUTH_REVOKED",
            failure="ACTIVATION_AUTH_REVOKE_FAILED",
            detail=reason,
        )

    def abort(
        self,
        activation_authorization_id: str,
        now: str,
        *,
        recovery_request_id: str | None = None,
        recovery_receiver_id: str | None = None,
    ) -> str:
        recovery_fields = (recovery_request_id, recovery_receiver_id)
        if any(value is not None for value in recovery_fields):
            if not all(isinstance(value, str) and value for value in recovery_fields):
                raise ProductionActivationAuthorizationStoreError(
                    "ACTIVATION_AUTH_RECOVERY_IDENTITY_MISSING"
                )
            return self._recover_uncertain_consume(
                activation_authorization_id,
                now,
                request_id=recovery_request_id,
                receiver_id=recovery_receiver_id,
            )
        return self._terminal_transition(
            activation_authorization_id,
            now,
            state="ABORTED",
            event_type="ACTIVATION_AUTH_ABORTED",
            failure="ACTIVATION_AUTH_ABORT_FAILED",
        )

    def _recover_uncertain_consume(
        self,
        activation_authorization_id: str,
        now: str,
        *,
        request_id: str,
        receiver_id: str,
    ) -> str:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                row = self._load_row(connection, activation_authorization_id)
                self._validate_recovery_identity(
                    row,
                    activation_authorization_id=activation_authorization_id,
                    request_id=request_id,
                    receiver_id=receiver_id,
                )
                state = str(row["state"])
                if state in {"CONSUMED", "ABORTED", "CANCELLED", "REVOKED"}:
                    return state
                if state != "CLAIMED":
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_AUTH_RECOVERY_STATE_INVALID"
                    )
                changed = connection.execute(
                    "UPDATE production_activation_authorizations "
                    "SET state='ABORTED', updated_at=? "
                    "WHERE activation_authorization_id=? AND state='CLAIMED'",
                    (now, activation_authorization_id),
                ).rowcount
                if changed != 1:
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_AUTH_RECOVERY_STATE_INVALID"
                    )
                self._insert_event_from_row(
                    connection,
                    row,
                    "ACTIVATION_AUTH_RECOVERY_ABORTED",
                    now,
                    "ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN",
                )
                connection.commit()
                return "ABORTED"
        except ProductionActivationAuthorizationStoreError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_RECOVERY_MALFORMED"
            ) from exc
        except sqlite3.Error as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_ABORT_FAILED"
            ) from exc

    @staticmethod
    def _validate_recovery_identity(
        row: sqlite3.Row,
        *,
        activation_authorization_id: str,
        request_id: str,
        receiver_id: str,
    ) -> None:
        payload = json.loads(row["artifact_json"])
        if not isinstance(payload, dict):
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_RECOVERY_MALFORMED"
            )
        artifact_hash = payload.get("artifact_hash")
        canonical_fields = {
            key: value
            for key, value in payload.items()
            if key not in {"activation_authorization_id", "artifact_hash"}
        }
        computed_hash = hashlib.sha256(
            json.dumps(
                canonical_fields,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        checks = (
            row["activation_authorization_id"] == activation_authorization_id,
            row["request_id"] == request_id,
            row["receiver_id"] == receiver_id,
            payload.get("activation_authorization_id") == activation_authorization_id,
            payload.get("request_id") == request_id,
            payload.get("receiver_id") == receiver_id,
            artifact_hash == row["artifact_hash"] == computed_hash,
            activation_authorization_id
            == f"production-activation-auth-{computed_hash[:16]}",
        )
        if not all(checks):
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_RECOVERY_IDENTITY_MISMATCH"
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
        return self._state_transition(
            activation_authorization_id,
            now,
            expected_state="CLAIMED",
            state=state,
            event_type=event_type,
            failure=failure,
            detail="",
        )

    def _state_transition(
        self,
        activation_authorization_id: str,
        now: str,
        *,
        expected_state: str,
        state: str,
        event_type: str,
        failure: str,
        detail: str,
    ) -> str:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
                row = self._load_row(connection, activation_authorization_id)
                if row["state"] != expected_state:
                    if row["state"] == state:
                        prior = connection.execute(
                            "SELECT detail FROM production_activation_authorization_events "
                            "WHERE activation_authorization_id=? AND event_type=? "
                            "ORDER BY sequence DESC LIMIT 1",
                            (activation_authorization_id, event_type),
                        ).fetchone()
                        if prior is not None and prior["detail"] == detail:
                            return state
                    if event_type == "ACTIVATION_AUTH_CANCELLED":
                        reason = "CANCELLATION_NOT_ALLOWED_IN_STATE"
                    elif event_type == "ACTIVATION_AUTH_REVOKED":
                        reason = (
                            "REVOCATION_NOT_ALLOWED_IN_STATE"
                            if row["state"] == "ISSUED"
                            else "REVOCATION_TOO_LATE"
                        )
                    else:
                        reason = "ACTIVATION_AUTH_REPLAY"
                    raise ProductionActivationAuthorizationStoreError(reason)
                changed = connection.execute(
                    "UPDATE production_activation_authorizations SET state=?, updated_at=? WHERE activation_authorization_id=? AND state=?",
                    (state, now, activation_authorization_id, expected_state),
                ).rowcount
                if changed != 1:
                    raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_REPLAY")
                self._insert_event_from_row(connection, row, event_type, now, detail)
                self._insert_ceremony_event_from_row(
                    connection, row, event_type, now, detail
                )
                self._set_ceremony_state(connection, row, state, now)
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
            self._validate_lineage(connection)
            self._insert_event(
                connection,
                artifact.activation_authorization_id,
                artifact.request_id,
                artifact.receiver_id,
                event_type,
                created_at,
                "",
            )
            self._insert_ceremony_event(
                connection, artifact, event_type, created_at, ""
            )

    def state(self, activation_authorization_id: str) -> str | None:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            row = connection.execute(
                "SELECT state FROM production_activation_authorizations WHERE activation_authorization_id=?",
                (activation_authorization_id,),
            ).fetchone()
        return None if row is None else str(row["state"])

    def load_artifact(self, activation_authorization_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            row = self._load_row(connection, activation_authorization_id)
        payload = json.loads(row["artifact_json"])
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if payload.get("artifact_hash") != row["artifact_hash"] or not encoded:
            raise ProductionActivationAuthorizationStoreError("ACTIVATION_AUTH_STORE_TAMPERED")
        return payload

    def has_outstanding(self) -> bool:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            row = connection.execute(
                "SELECT 1 FROM production_activation_authorizations WHERE state IN ('ISSUED','CLAIMED') LIMIT 1"
            ).fetchone()
        return row is not None

    def expire_outstanding(self, now: str) -> int:
        """Durably expire stale rows during a new explicit issue action."""
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_lineage(connection)
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
            self._validate_lineage(connection)
            rows = connection.execute(
                "SELECT * FROM production_activation_authorization_events WHERE request_id=? ORDER BY sequence",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def ceremony_events(self, ceremony_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            rows = connection.execute(
                "SELECT * FROM production_activation_ceremony_events WHERE ceremony_id=? ORDER BY sequence",
                (ceremony_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def ceremony_state(self, ceremony_id: str) -> str | None:
        with closing(self._connect()) as connection:
            self._validate_lineage(connection)
            row = connection.execute(
                "SELECT state FROM production_activation_ceremonies WHERE ceremony_id=?",
                (ceremony_id,),
            ).fetchone()
        return None if row is None else str(row["state"])

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

    def _insert_ceremony_event_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        event_type: str,
        created_at: str,
        detail: str,
    ) -> None:
        payload = json.loads(row["artifact_json"])
        self._insert_ceremony_event(
            connection, _MappingArtifact(payload), event_type, created_at, detail
        )

    @staticmethod
    def _set_ceremony_state(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        state: str,
        updated_at: str,
    ) -> None:
        payload = json.loads(row["artifact_json"])
        connection.execute(
            "UPDATE production_activation_ceremonies SET state=?, updated_at=? WHERE ceremony_id=?",
            (state, updated_at, payload["ceremony_id"]),
        )

    @staticmethod
    def _insert_ceremony_event(
        connection: sqlite3.Connection,
        artifact: Any,
        event_type: str,
        created_at: str,
        detail_code: str,
    ) -> None:
        scope = tuple(getattr(artifact, "capability_scope", ()))
        material = {
            "ceremony_id": artifact.ceremony_id,
            "event_type": event_type,
            "detail_code": detail_code,
            "activation_authorization_id": getattr(
                artifact, "activation_authorization_id", ""
            ),
        }
        event_id = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """INSERT OR IGNORE INTO production_activation_ceremony_events
            (event_id, ceremony_id, request_id, activation_authorization_id,
             operator_id, receiver_id, activation_store_id, activation_store_epoch,
             executor_binding_id, capability_scope_hash, event_type, created_at, detail_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                artifact.ceremony_id,
                artifact.request_id,
                getattr(artifact, "activation_authorization_id", None),
                artifact.operator_id,
                artifact.receiver_id,
                artifact.activation_store_id,
                artifact.activation_store_epoch,
                artifact.executor_binding_id,
                hashlib.sha256(
                    json.dumps(scope, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                event_type,
                created_at,
                detail_code,
            ),
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
        anchor_path: str | Path | None = None,
    ) -> ProductionActivationAuthorizationStore:
        if bootstrap_explicit is not True:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_BOOTSTRAP_NOT_EXPLICIT"
            )
        return ProductionActivationAuthorizationStore._initialize(path, anchor_path)

    def migrate_v1(
        self,
        path: str | Path,
        *,
        migration_explicit: bool,
        anchor_path: str | Path | None = None,
        now: str,
    ) -> ProductionActivationAuthorizationStore:
        if migration_explicit is not True:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_MIGRATION_NOT_EXPLICIT"
            )
        target = Path(path)
        anchor = Path(anchor_path) if anchor_path is not None else _default_anchor_path(target)
        if not target.is_file() or anchor.exists():
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_MIGRATION_SOURCE_INVALID"
            )
        store_id = f"activation-store-{uuid.uuid4()}"
        installation_id = f"activation-installation-{uuid.uuid4()}"
        try:
            with closing(sqlite3.connect(str(target), timeout=5.0)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                schema = connection.execute(
                    "SELECT value FROM activation_auth_metadata WHERE key='schema_version'"
                ).fetchone()
                if schema is None or schema["value"] != "1":
                    raise ProductionActivationAuthorizationStoreError(
                        "ACTIVATION_AUTH_STORE_SCHEMA_MISMATCH"
                    )
                _create_v2_tables(connection)
                legacy_rows = connection.execute(
                    "SELECT * FROM production_activation_authorizations "
                    "WHERE state IN ('ISSUED','CLAIMED')"
                ).fetchall()
                connection.execute(
                    "UPDATE production_activation_authorizations "
                    "SET state='ABORTED', updated_at=? WHERE state IN ('ISSUED','CLAIMED')",
                    (now,),
                )
                for row in legacy_rows:
                    ProductionActivationAuthorizationStore._insert_event(
                        connection,
                        row["activation_authorization_id"], row["request_id"],
                        row["receiver_id"], "ACTIVATION_AUTH_LEGACY_TERMINALIZED",
                        now, "LEGACY_ACTIVATION_AUTHORIZATION_RETIRED",
                    )
                connection.execute("DELETE FROM activation_auth_store_lineage")
                connection.execute(
                    "INSERT INTO activation_auth_store_lineage VALUES(1, ?, 1, ?)",
                    (store_id, installation_id),
                )
                connection.execute(
                    "UPDATE activation_auth_metadata SET value=? WHERE key='schema_version'",
                    (STORE_SCHEMA_VERSION,),
                )
                connection.commit()
            _write_anchor(anchor, target, store_id, 1, installation_id)
            return ProductionActivationAuthorizationStore(target, anchor)
        except ProductionActivationAuthorizationStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ProductionActivationAuthorizationStoreError(
                "ACTIVATION_AUTH_STORE_MIGRATION_FAILED"
            ) from exc


class _MappingArtifact:
    def __init__(self, values: dict[str, Any]) -> None:
        self.__dict__.update(values)


def _create_v2_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS activation_auth_store_lineage (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        store_id TEXT NOT NULL,
        store_epoch INTEGER NOT NULL,
        installation_id TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS production_activation_ceremonies (
        ceremony_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        activation_authorization_id TEXT,
        operator_id TEXT NOT NULL,
        receiver_id TEXT NOT NULL,
        activation_store_id TEXT NOT NULL,
        activation_store_epoch INTEGER NOT NULL,
        executor_binding_id TEXT NOT NULL,
        capability_scope_json TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS production_activation_ceremony_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        ceremony_id TEXT NOT NULL,
        request_id TEXT NOT NULL,
        activation_authorization_id TEXT,
        operator_id TEXT NOT NULL,
        receiver_id TEXT NOT NULL,
        activation_store_id TEXT NOT NULL,
        activation_store_epoch INTEGER NOT NULL,
        executor_binding_id TEXT NOT NULL,
        capability_scope_hash TEXT NOT NULL,
        event_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        detail_code TEXT NOT NULL
        )"""
    )


def _default_anchor_path(path: Path) -> Path:
    return Path(f"{path}.anchor")


def _anchor_fields(
    store_path: Path,
    store_id: str,
    store_epoch: int,
    installation_id: str,
) -> dict[str, str | int]:
    return {
        "schema_id": ANCHOR_SCHEMA_ID,
        "store_id": store_id,
        "store_epoch": store_epoch,
        "installation_id": installation_id,
        "store_path_hash": hashlib.sha256(
            str(store_path.resolve()).casefold().encode("utf-8")
        ).hexdigest(),
    }


def _anchor_hash(fields: dict[str, str | int]) -> str:
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_anchor(
    anchor_path: Path,
    store_path: Path,
    store_id: str,
    store_epoch: int,
    installation_id: str,
) -> None:
    fields = _anchor_fields(store_path, store_id, store_epoch, installation_id)
    anchor_path.write_text(
        json.dumps({**fields, "anchor_hash": _anchor_hash(fields)}, sort_keys=True),
        encoding="utf-8",
    )


def _read_anchor(anchor_path: Path) -> dict[str, Any]:
    if not anchor_path.is_file():
        raise ProductionActivationAuthorizationStoreError(
            "ACTIVATION_STORE_ANCHOR_MISSING"
        )
    try:
        payload = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionActivationAuthorizationStoreError(
            "ACTIVATION_STORE_ANCHOR_MISMATCH"
        ) from exc
    if not isinstance(payload, dict):
        raise ProductionActivationAuthorizationStoreError(
            "ACTIVATION_STORE_ANCHOR_MISMATCH"
        )
    return payload


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("activation authorization time must be timezone-aware")
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProductionActivationAuthorizationStoreError("INVALID_ACTIVATION_AUTH_TIME") from exc
