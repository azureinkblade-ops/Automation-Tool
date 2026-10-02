"""Restart-durable invocation-authorization persistence for EA-4E.32."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from tools.hermes_core.hashing import sha256_payload


AUTH_STORE_SCHEMA_ID = "hermes.production-invocation-authorization-store/v1"
AUTH_STORE_SCHEMA_VERSION = "1"
AUTH_STORE_ANCHOR_SCHEMA_ID = "hermes.production-invocation-authorization-anchor/v1"
AUTH_STORE_ANCHOR_SCHEMA_VERSION = "1"
SQLITE_BUSY_TIMEOUT_MS = 1_000

AUTHORIZATION_FIELDS = (
    "invocation_authorization_id",
    "receiver_id",
    "binding_id",
    "enablement_id",
    "execution_request_id",
    "attempt_number",
    "issued_at",
    "expires_at",
    "runtime_scope",
    "delegation_class",
    "nonce",
)


class DurableAuthorizationStoreError(RuntimeError):
    """Base fail-closed durable-store error."""


class DurableAuthorizationStoreIntegrityError(DurableAuthorizationStoreError):
    """Persisted state is malformed, unsupported, or hash-inconsistent."""


class DurableAuthorizationStoreConflict(DurableAuthorizationStoreError):
    """A durable identity was replayed with different canonical material."""


class DurableAuthorizationStoreUnavailable(DurableAuthorizationStoreError):
    """The configured store is missing or cannot be opened safely."""


@dataclass(frozen=True)
class DurableIssueResult:
    authorization_payload: dict[str, object]
    replayed: bool


@dataclass(frozen=True)
class DurableAuthorizationState:
    authorization_payload: dict[str, object]
    consumed: bool
    consumed_at: str | None


@dataclass(frozen=True)
class DurableClaimResult:
    allowed: bool
    reason: str
    consumed: bool


class DurableInvocationAuthorizationStore:
    """Explicit-path SQLite owner for issuance identity and consumption state."""

    def __init__(self, path: str | Path, *, anchor_path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.anchor_path = Path(anchor_path).resolve()
        if self.path == self.anchor_path:
            raise DurableAuthorizationStoreUnavailable(
                "authorization store and anchor paths must be distinct"
            )
        if not self.path.is_file():
            raise DurableAuthorizationStoreUnavailable(
                f"durable authorization store does not exist: {self.path}"
            )
        if not self.anchor_path.is_file():
            raise DurableAuthorizationStoreUnavailable(
                f"durable authorization anchor does not exist: {self.anchor_path}"
            )
        with self._connection() as connection:
            self._verify_store_identity(connection)

    @classmethod
    def initialize(
        cls, path: str | Path, *, anchor_path: str | Path
    ) -> "DurableInvocationAuthorizationStore":
        """Explicitly create an empty store, or verify an existing store."""
        target = Path(path).resolve()
        anchor = Path(anchor_path).resolve()
        if target == anchor:
            raise DurableAuthorizationStoreUnavailable(
                "authorization store and anchor paths must be distinct"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return cls(target, anchor_path=anchor)
        if anchor.exists():
            raise DurableAuthorizationStoreUnavailable(
                "authorization anchor exists without its established store"
            )

        store_instance_id = str(uuid.uuid4())
        store_generation = 1
        connection = sqlite3.connect(str(target), isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE auth_store_metadata ("
                "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
                "schema_id TEXT NOT NULL, schema_version TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO auth_store_metadata(singleton, schema_id, schema_version) "
                "VALUES (1, ?, ?)",
                (AUTH_STORE_SCHEMA_ID, AUTH_STORE_SCHEMA_VERSION),
            )
            connection.execute(
                "CREATE TABLE auth_store_lineage ("
                "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
                "store_instance_id TEXT NOT NULL, store_generation INTEGER NOT NULL "
                "CHECK (store_generation >= 1))"
            )
            connection.execute(
                "INSERT INTO auth_store_lineage(singleton, store_instance_id, store_generation) "
                "VALUES (1, ?, ?)",
                (store_instance_id, store_generation),
            )
            connection.execute(
                "CREATE TABLE invocation_authorizations ("
                "authorization_id TEXT PRIMARY KEY, "
                "issue_request_id TEXT NOT NULL UNIQUE, "
                "issue_request_hash TEXT NOT NULL, "
                "canonical_authorization_hash TEXT NOT NULL, "
                "receiver_id TEXT NOT NULL, binding_id TEXT NOT NULL, "
                "enablement_id TEXT NOT NULL, execution_request_id TEXT NOT NULL, "
                "attempt_number INTEGER NOT NULL, issued_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, runtime_scope TEXT NOT NULL, "
                "delegation_class TEXT NOT NULL, nonce TEXT NOT NULL, "
                "consumed_state TEXT NOT NULL, consumed_at TEXT, "
                "record_hash TEXT NOT NULL)"
            )
            connection.execute("COMMIT")
            cls._write_anchor_file(
                anchor,
                store_instance_id=store_instance_id,
                store_generation=store_generation,
                create_parent=True,
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()
            try:
                target.unlink()
            except OSError:
                pass
            raise
        finally:
            connection.close()
        return cls(target, anchor_path=anchor)

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw",
                uri=True,
                isolation_level=None,
                timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            return connection
        except sqlite3.Error as exc:
            raise DurableAuthorizationStoreUnavailable(str(exc)) from exc

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            row = connection.execute(
                "SELECT schema_id, schema_version FROM auth_store_metadata "
                "WHERE singleton = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store schema metadata is missing"
            ) from exc
        if row is None:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store schema metadata is missing"
            )
        if tuple(row) != (AUTH_STORE_SCHEMA_ID, AUTH_STORE_SCHEMA_VERSION):
            raise DurableAuthorizationStoreIntegrityError(
                "unsupported authorization store schema"
            )

    @staticmethod
    def _anchor_material(
        *, store_instance_id: str, store_generation: int
    ) -> dict[str, object]:
        return {
            "schema_id": AUTH_STORE_ANCHOR_SCHEMA_ID,
            "schema_version": AUTH_STORE_ANCHOR_SCHEMA_VERSION,
            "store_instance_id": store_instance_id,
            "store_generation": store_generation,
        }

    @classmethod
    def _write_anchor_file(
        cls,
        anchor_path: Path,
        *,
        store_instance_id: str,
        store_generation: int,
        create_parent: bool = False,
    ) -> None:
        material = cls._anchor_material(
            store_instance_id=store_instance_id,
            store_generation=store_generation,
        )
        payload = {**material, "anchor_hash": sha256_payload(material)}
        if create_parent:
            anchor_path.parent.mkdir(parents=True, exist_ok=True)
        elif not anchor_path.parent.is_dir():
            raise DurableAuthorizationStoreUnavailable(
                "authorization anchor directory is unavailable"
            )
        temporary = anchor_path.with_name(
            f".{anchor_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, anchor_path)
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise DurableAuthorizationStoreUnavailable(
                f"authorization anchor cannot be written: {exc}"
            ) from exc

    def _read_anchor(self) -> tuple[str, int]:
        try:
            with self.anchor_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DurableAuthorizationStoreUnavailable(
                f"authorization anchor cannot be read: {exc}"
            ) from exc
        required = {
            "schema_id",
            "schema_version",
            "store_instance_id",
            "store_generation",
            "anchor_hash",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization anchor fields are malformed"
            )
        if (
            payload["schema_id"] != AUTH_STORE_ANCHOR_SCHEMA_ID
            or payload["schema_version"] != AUTH_STORE_ANCHOR_SCHEMA_VERSION
        ):
            raise DurableAuthorizationStoreIntegrityError(
                "unsupported authorization anchor schema"
            )
        store_instance_id = payload["store_instance_id"]
        store_generation = payload["store_generation"]
        if not isinstance(store_instance_id, str) or not store_instance_id:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization anchor store identity is malformed"
            )
        if (
            not isinstance(store_generation, int)
            or isinstance(store_generation, bool)
            or store_generation < 1
        ):
            raise DurableAuthorizationStoreIntegrityError(
                "authorization anchor generation is malformed"
            )
        material = self._anchor_material(
            store_instance_id=store_instance_id,
            store_generation=store_generation,
        )
        if payload["anchor_hash"] != sha256_payload(material):
            raise DurableAuthorizationStoreIntegrityError(
                "authorization anchor hash mismatch"
            )
        return store_instance_id, store_generation

    @staticmethod
    def _read_lineage(connection: sqlite3.Connection) -> tuple[str, int]:
        try:
            row = connection.execute(
                "SELECT store_instance_id, store_generation FROM auth_store_lineage "
                "WHERE singleton = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store lineage metadata is missing"
            ) from exc
        if row is None:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store lineage metadata is missing"
            )
        store_instance_id, store_generation = tuple(row)
        if not isinstance(store_instance_id, str) or not store_instance_id:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store identity is malformed"
            )
        if (
            not isinstance(store_generation, int)
            or isinstance(store_generation, bool)
            or store_generation < 1
        ):
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store generation is malformed"
            )
        return store_instance_id, store_generation

    def _verify_store_identity(
        self, connection: sqlite3.Connection
    ) -> tuple[str, int]:
        self._verify_schema(connection)
        database_identity = self._read_lineage(connection)
        anchor_identity = self._read_anchor()
        if database_identity != anchor_identity:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store and external anchor do not match"
            )
        return database_identity

    @staticmethod
    def _advance_generation(
        connection: sqlite3.Connection, store_instance_id: str, generation: int
    ) -> int:
        next_generation = generation + 1
        cursor = connection.execute(
            "UPDATE auth_store_lineage SET store_generation = ? "
            "WHERE singleton = 1 AND store_instance_id = ? AND store_generation = ?",
            (next_generation, store_instance_id, generation),
        )
        if cursor.rowcount != 1:
            raise DurableAuthorizationStoreIntegrityError(
                "authorization store generation changed unexpectedly"
            )
        return next_generation

    def _publish_generation(
        self, *, store_instance_id: str, store_generation: int
    ) -> None:
        self._write_anchor_file(
            self.anchor_path,
            store_instance_id=store_instance_id,
            store_generation=store_generation,
        )

    def _after_database_commit_before_anchor(self) -> None:
        """Test seam for crash ambiguity qualification."""

    @property
    def store_instance_id(self) -> str:
        with self._connection() as connection:
            return self._verify_store_identity(connection)[0]

    @property
    def store_generation(self) -> int:
        with self._connection() as connection:
            return self._verify_store_identity(connection)[1]

    @staticmethod
    def _normalize_payload(payload: Mapping[str, object]) -> dict[str, object]:
        if set(payload) != set(AUTHORIZATION_FIELDS):
            raise DurableAuthorizationStoreIntegrityError(
                "authorization payload fields are incomplete or unsupported"
            )
        normalized = {field: payload[field] for field in AUTHORIZATION_FIELDS}
        for field in AUTHORIZATION_FIELDS:
            value = normalized[field]
            if field == "attempt_number":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise DurableAuthorizationStoreIntegrityError(
                        "authorization attempt number is malformed"
                    )
            elif not isinstance(value, str) or not value:
                raise DurableAuthorizationStoreIntegrityError(
                    f"authorization field is malformed: {field}"
                )
        return normalized

    @staticmethod
    def _record_material(
        *,
        issue_request_id: str,
        issue_request_hash: str,
        canonical_authorization_hash: str,
        payload: Mapping[str, object],
        consumed_state: str,
        consumed_at: str | None,
    ) -> dict[str, object]:
        return {
            "issue_request_id": issue_request_id,
            "issue_request_hash": issue_request_hash,
            "canonical_authorization_hash": canonical_authorization_hash,
            "authorization": dict(payload),
            "consumed_state": consumed_state,
            "consumed_at": consumed_at,
        }

    @classmethod
    def _row_state(cls, row: sqlite3.Row) -> DurableAuthorizationState:
        payload = {
            "invocation_authorization_id": row["authorization_id"],
            "receiver_id": row["receiver_id"],
            "binding_id": row["binding_id"],
            "enablement_id": row["enablement_id"],
            "execution_request_id": row["execution_request_id"],
            "attempt_number": row["attempt_number"],
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "runtime_scope": row["runtime_scope"],
            "delegation_class": row["delegation_class"],
            "nonce": row["nonce"],
        }
        payload = cls._normalize_payload(payload)
        canonical_hash = sha256_payload(payload)
        if row["canonical_authorization_hash"] != canonical_hash:
            raise DurableAuthorizationStoreIntegrityError(
                "canonical authorization hash mismatch"
            )
        if row["consumed_state"] not in {"UNCONSUMED", "CONSUMED"}:
            raise DurableAuthorizationStoreIntegrityError(
                "invalid authorization consumed state"
            )
        if row["consumed_state"] == "UNCONSUMED" and row["consumed_at"] is not None:
            raise DurableAuthorizationStoreIntegrityError(
                "unconsumed authorization has consumed timestamp"
            )
        if row["consumed_state"] == "CONSUMED" and not row["consumed_at"]:
            raise DurableAuthorizationStoreIntegrityError(
                "consumed authorization lacks consumed timestamp"
            )
        material = cls._record_material(
            issue_request_id=row["issue_request_id"],
            issue_request_hash=row["issue_request_hash"],
            canonical_authorization_hash=canonical_hash,
            payload=payload,
            consumed_state=row["consumed_state"],
            consumed_at=row["consumed_at"],
        )
        if row["record_hash"] != sha256_payload(material):
            raise DurableAuthorizationStoreIntegrityError(
                "authorization record hash mismatch"
            )
        return DurableAuthorizationState(
            authorization_payload=payload,
            consumed=row["consumed_state"] == "CONSUMED",
            consumed_at=row["consumed_at"],
        )

    @staticmethod
    def _select_by_authorization(
        connection: sqlite3.Connection, authorization_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM invocation_authorizations WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchone()

    @staticmethod
    def _select_by_issue(
        connection: sqlite3.Connection, issue_request_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM invocation_authorizations WHERE issue_request_id = ?",
            (issue_request_id,),
        ).fetchone()

    def _before_issue_commit(self, connection: sqlite3.Connection) -> None:
        """Test seam for rollback qualification."""

    def _before_claim_commit(self, connection: sqlite3.Connection) -> None:
        """Test seam for rollback qualification."""

    def get_issued(
        self, issue_request_id: str, issue_request_hash: str
    ) -> DurableIssueResult | None:
        with self._connection() as connection:
            self._verify_store_identity(connection)
            row = self._select_by_issue(connection, issue_request_id)
            if row is None:
                return None
            state = self._row_state(row)
            if row["issue_request_hash"] != issue_request_hash:
                raise DurableAuthorizationStoreConflict(
                    "issue request ID has conflicting canonical material"
                )
            return DurableIssueResult(state.authorization_payload, replayed=True)

    def persist_issued(
        self,
        *,
        issue_request_id: str,
        issue_request_hash: str,
        authorization_payload: Mapping[str, object],
    ) -> DurableIssueResult:
        payload = self._normalize_payload(authorization_payload)
        canonical_hash = sha256_payload(payload)
        consumed_state = "UNCONSUMED"
        consumed_at = None
        material = self._record_material(
            issue_request_id=issue_request_id,
            issue_request_hash=issue_request_hash,
            canonical_authorization_hash=canonical_hash,
            payload=payload,
            consumed_state=consumed_state,
            consumed_at=consumed_at,
        )
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                store_instance_id, store_generation = self._verify_store_identity(
                    connection
                )
                issue_row = self._select_by_issue(connection, issue_request_id)
                auth_row = self._select_by_authorization(
                    connection, str(payload["invocation_authorization_id"])
                )
                existing = issue_row or auth_row
                if existing is not None:
                    state = self._row_state(existing)
                    if (
                        existing["issue_request_id"] != issue_request_id
                        or existing["issue_request_hash"] != issue_request_hash
                        or state.authorization_payload != payload
                    ):
                        raise DurableAuthorizationStoreConflict(
                            "durable authorization identity collision"
                        )
                    connection.execute("COMMIT")
                    return DurableIssueResult(payload, replayed=True)
                connection.execute(
                    "INSERT INTO invocation_authorizations ("
                    "authorization_id, issue_request_id, issue_request_hash, "
                    "canonical_authorization_hash, receiver_id, binding_id, "
                    "enablement_id, execution_request_id, attempt_number, issued_at, "
                    "expires_at, runtime_scope, delegation_class, nonce, "
                    "consumed_state, consumed_at, record_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["invocation_authorization_id"], issue_request_id,
                        issue_request_hash, canonical_hash, payload["receiver_id"],
                        payload["binding_id"], payload["enablement_id"],
                        payload["execution_request_id"], payload["attempt_number"],
                        payload["issued_at"], payload["expires_at"],
                        payload["runtime_scope"], payload["delegation_class"],
                        payload["nonce"], consumed_state, consumed_at,
                        sha256_payload(material),
                    ),
                )
                self._before_issue_commit(connection)
                next_generation = self._advance_generation(
                    connection, store_instance_id, store_generation
                )
                connection.execute("COMMIT")
                self._after_database_commit_before_anchor()
                self._publish_generation(
                    store_instance_id=store_instance_id,
                    store_generation=next_generation,
                )
                return DurableIssueResult(payload, replayed=False)
        except DurableAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise DurableAuthorizationStoreError(str(exc)) from exc
        except Exception as exc:
            raise DurableAuthorizationStoreError(str(exc)) from exc

    def inspect(self, authorization_payload: Mapping[str, object]) -> DurableAuthorizationState:
        payload = self._normalize_payload(authorization_payload)
        with self._connection() as connection:
            self._verify_store_identity(connection)
            row = self._select_by_authorization(
                connection, str(payload["invocation_authorization_id"])
            )
            if row is None:
                raise DurableAuthorizationStoreIntegrityError(
                    "authorization is absent from durable state"
                )
            state = self._row_state(row)
            if state.authorization_payload != payload:
                if row["receiver_id"] != payload["receiver_id"]:
                    raise DurableAuthorizationStoreConflict(
                        "cross-receiver invocation replay"
                    )
                raise DurableAuthorizationStoreConflict(
                    "invocation authorization ID collision"
                )
            return state

    def inspect_by_id(self, authorization_id: str) -> DurableAuthorizationState:
        with self._connection() as connection:
            self._verify_store_identity(connection)
            row = self._select_by_authorization(connection, authorization_id)
            if row is None:
                raise DurableAuthorizationStoreIntegrityError(
                    "authorization is absent from durable state"
                )
            return self._row_state(row)

    def claim(
        self,
        authorization_payload: Mapping[str, object],
        *,
        consumed_at: str,
        validate: Callable[[], str | None],
    ) -> DurableClaimResult:
        payload = self._normalize_payload(authorization_payload)
        authorization_id = str(payload["invocation_authorization_id"])
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                store_instance_id, store_generation = self._verify_store_identity(
                    connection
                )
                row = self._select_by_authorization(connection, authorization_id)
                if row is None:
                    connection.execute("ROLLBACK")
                    return DurableClaimResult(False, "INVOCATION_AUTHORIZATION_NOT_DURABLE", False)
                state = self._row_state(row)
                if state.authorization_payload != payload:
                    connection.execute("ROLLBACK")
                    reason = (
                        "CROSS_RECEIVER_INVOCATION_REPLAY"
                        if row["receiver_id"] != payload["receiver_id"]
                        else "INVOCATION_AUTHORIZATION_ID_COLLISION"
                    )
                    return DurableClaimResult(False, reason, False)
                if state.consumed:
                    connection.execute("ROLLBACK")
                    return DurableClaimResult(
                        False, "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED", True
                    )
                validation_reason = validate()
                if validation_reason is not None:
                    connection.execute("ROLLBACK")
                    return DurableClaimResult(False, validation_reason, False)
                material = self._record_material(
                    issue_request_id=row["issue_request_id"],
                    issue_request_hash=row["issue_request_hash"],
                    canonical_authorization_hash=row["canonical_authorization_hash"],
                    payload=payload,
                    consumed_state="CONSUMED",
                    consumed_at=consumed_at,
                )
                cursor = connection.execute(
                    "UPDATE invocation_authorizations SET consumed_state = 'CONSUMED', "
                    "consumed_at = ?, record_hash = ? "
                    "WHERE authorization_id = ? AND consumed_state = 'UNCONSUMED'",
                    (consumed_at, sha256_payload(material), authorization_id),
                )
                if cursor.rowcount != 1:
                    connection.execute("ROLLBACK")
                    return DurableClaimResult(
                        False, "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED", True
                )
                self._before_claim_commit(connection)
                next_generation = self._advance_generation(
                    connection, store_instance_id, store_generation
                )
                connection.execute("COMMIT")
                self._after_database_commit_before_anchor()
                self._publish_generation(
                    store_instance_id=store_instance_id,
                    store_generation=next_generation,
                )
                return DurableClaimResult(True, "INVOCATION_AUTHORIZATION_VALID", True)
        except DurableAuthorizationStoreError:
            raise
        except sqlite3.Error as exc:
            raise DurableAuthorizationStoreError(str(exc)) from exc
        except Exception as exc:
            raise DurableAuthorizationStoreError(str(exc)) from exc

    def count(self) -> int:
        with self._connection() as connection:
            self._verify_store_identity(connection)
            return int(connection.execute(
                "SELECT COUNT(*) FROM invocation_authorizations"
            ).fetchone()[0])

    def consumed_count(self) -> int:
        with self._connection() as connection:
            self._verify_store_identity(connection)
            return int(connection.execute(
                "SELECT COUNT(*) FROM invocation_authorizations "
                "WHERE consumed_state = 'CONSUMED'"
            ).fetchone()[0])
