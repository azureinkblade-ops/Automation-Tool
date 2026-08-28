"""R12A SQLite persistence for delegated tasks and capability leases.

The store owns durable identity, replay, cancellation, and revocation state. It
does not deliver work, accept receipts, route agents, or launch processes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Optional

from .delegated_task import (
    CancellationConflictError,
    CapabilityViolationError,
    DelegatedCapabilityLease,
    DelegatedTaskEnvelope,
    DelegationConflictError,
    DelegationIntegrityError,
    DelegationNotFoundError,
    InvalidDelegationStateTransitionError,
    LeaseConflictError,
    LeaseRevokedError,
    build_delegated_capability_lease,
    reconstruct_capability_lease,
    reconstruct_delegated_task,
    validate_capability_request,
    _normalize_text,
    _normalize_timestamp,
)
from .hashing import canonical_json, sha256_payload


SCHEMA_VERSION = 1


class DelegationStoreError(RuntimeError):
    """Base class for durable delegation-store failures."""


class DelegationStoreSchemaError(DelegationStoreError):
    """The database schema is absent, unsupported, or malformed."""


class SQLiteDelegationStore:
    """One fail-closed SQLite store for the R12A domain."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            version_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='delegation_schema_version'"
            ).fetchone()
            if version_table is not None:
                row = connection.execute(
                    "SELECT version FROM delegation_schema_version WHERE singleton=1"
                ).fetchone()
                if row is None or row["version"] != SCHEMA_VERSION:
                    raise DelegationStoreSchemaError("unsupported delegation-store schema version")
                self._verify_schema(connection)
                return
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.executescript(
                    """
                    CREATE TABLE delegation_schema_version (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        version INTEGER NOT NULL
                    );
                    INSERT INTO delegation_schema_version(singleton, version) VALUES (1, 1);

                    CREATE TABLE delegations (
                        delegation_id TEXT PRIMARY KEY,
                        artifact_hash TEXT NOT NULL,
                        task_input_hash TEXT NOT NULL,
                        originator_request_id TEXT NOT NULL,
                        originator_agent_id TEXT NOT NULL,
                        delegation_revision INTEGER NOT NULL,
                        requested_target_agent_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('CREATED', 'CANCELLED')),
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        UNIQUE(originator_agent_id, originator_request_id, delegation_revision)
                    );

                    CREATE TABLE capability_leases (
                        lease_id TEXT PRIMARY KEY,
                        artifact_hash TEXT NOT NULL,
                        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
                        attempt_id TEXT NOT NULL,
                        route_id TEXT NOT NULL,
                        recipient_agent_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        UNIQUE(attempt_id, route_id)
                    );

                    CREATE TABLE delegation_cancellations (
                        delegation_id TEXT PRIMARY KEY REFERENCES delegations(delegation_id),
                        reason TEXT NOT NULL,
                        cancelled_at TEXT NOT NULL,
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL
                    );

                    CREATE TABLE lease_revocations (
                        lease_id TEXT PRIMARY KEY REFERENCES capability_leases(lease_id),
                        reason TEXT NOT NULL,
                        revoked_at TEXT NOT NULL,
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL
                    );
                    """
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        required = {
            "delegation_schema_version",
            "delegations",
            "capability_leases",
            "delegation_cancellations",
            "lease_revocations",
        }
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not required.issubset({row["name"] for row in rows}):
            raise DelegationStoreSchemaError("delegation-store schema is incomplete")

    @staticmethod
    def _encode(payload: dict[str, Any]) -> tuple[str, str]:
        text = canonical_json(payload)
        return text, sha256_payload(payload)

    @staticmethod
    def _decode(row: sqlite3.Row, artifact: str) -> dict[str, Any]:
        try:
            payload = json.loads(row["canonical_payload"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DelegationIntegrityError(f"{artifact} canonical payload is corrupt") from exc
        if canonical_json(payload) != row["canonical_payload"]:
            raise DelegationIntegrityError(f"{artifact} payload is not canonical JSON")
        if sha256_payload(payload) != row["payload_sha256"]:
            raise DelegationIntegrityError(f"{artifact} payload checksum mismatch")
        return payload

    def create_delegation(self, envelope: DelegatedTaskEnvelope) -> DelegatedTaskEnvelope:
        envelope.verify_hash()
        payload = envelope.to_canonical_dict()
        text, checksum = self._encode(payload)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id=?",
                    (envelope.delegation_id,),
                ).fetchone()
                if existing is not None:
                    durable = self._load_delegation_row(existing)
                    if durable.artifact_hash != envelope.artifact_hash:
                        raise DelegationConflictError(
                            "delegation identity already exists with divergent canonical material"
                        )
                    connection.rollback()
                    return durable
                connection.execute(
                    """INSERT INTO delegations(
                        delegation_id, artifact_hash, task_input_hash,
                        originator_request_id, originator_agent_id,
                        delegation_revision, requested_target_agent_id, status,
                        canonical_payload, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)""",
                    (
                        envelope.delegation_id,
                        envelope.artifact_hash,
                        envelope.task_input_hash,
                        envelope.originator_request_id,
                        envelope.originator_agent_id,
                        envelope.delegation_revision,
                        envelope.requested_target_agent_id,
                        text,
                        checksum,
                    ),
                )
                connection.commit()
                return envelope
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise DelegationConflictError("delegation durable uniqueness conflict") from exc
            except Exception:
                connection.rollback()
                raise

    def _load_delegation_row(self, row: sqlite3.Row) -> DelegatedTaskEnvelope:
        payload = self._decode(row, "delegation")
        envelope = reconstruct_delegated_task(payload)
        if (
            row["delegation_id"] != envelope.delegation_id
            or row["artifact_hash"] != envelope.artifact_hash
            or row["task_input_hash"] != envelope.task_input_hash
            or row["originator_request_id"] != envelope.originator_request_id
            or row["originator_agent_id"] != envelope.originator_agent_id
            or row["delegation_revision"] != envelope.delegation_revision
            or row["requested_target_agent_id"] != envelope.requested_target_agent_id
        ):
            raise DelegationIntegrityError("delegation physical linkage mismatch")
        return envelope

    def get_delegation(self, delegation_id: str) -> DelegatedTaskEnvelope:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM delegations WHERE delegation_id=?", (delegation_id,)
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"delegation not found: {delegation_id}")
        return self._load_delegation_row(row)

    def delegation_status(self, delegation_id: str) -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status FROM delegations WHERE delegation_id=?", (delegation_id,)
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"delegation not found: {delegation_id}")
        return str(row["status"])

    def issue_lease(self, lease: DelegatedCapabilityLease) -> DelegatedCapabilityLease:
        lease.verify_hash()
        payload = lease.to_canonical_dict()
        text, checksum = self._encode(payload)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                delegation_row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id=?", (lease.delegation_id,)
                ).fetchone()
                if delegation_row is None:
                    raise DelegationNotFoundError(f"delegation not found: {lease.delegation_id}")
                delegation = self._load_delegation_row(delegation_row)
                if delegation_row["status"] != "CREATED":
                    raise InvalidDelegationStateTransitionError(
                        "a cancelled delegation cannot receive a capability lease"
                    )
                self._validate_lease_against_delegation(lease, delegation)
                existing = connection.execute(
                    "SELECT * FROM capability_leases WHERE lease_id=? OR (attempt_id=? AND route_id=?)",
                    (lease.lease_id, lease.attempt_id, lease.route_id),
                ).fetchone()
                if existing is not None:
                    durable = self._load_lease_row(existing)
                    if durable.lease_id != lease.lease_id or durable.artifact_hash != lease.artifact_hash:
                        raise LeaseConflictError("attempt/route lease identity has divergent canonical material")
                    connection.rollback()
                    return durable
                connection.execute(
                    """INSERT INTO capability_leases(
                        lease_id, artifact_hash, delegation_id, attempt_id, route_id,
                        recipient_agent_id, status, canonical_payload, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
                    (
                        lease.lease_id,
                        lease.artifact_hash,
                        lease.delegation_id,
                        lease.attempt_id,
                        lease.route_id,
                        lease.recipient_agent_id,
                        text,
                        checksum,
                    ),
                )
                connection.commit()
                return lease
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise LeaseConflictError("capability lease durable uniqueness conflict") from exc
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _validate_lease_against_delegation(
        lease: DelegatedCapabilityLease, envelope: DelegatedTaskEnvelope
    ) -> None:
        if lease.delegated_task_hash != envelope.artifact_hash:
            raise CapabilityViolationError("lease binds the wrong delegated-task hash")
        if lease.recipient_agent_id != envelope.requested_target_agent_id:
            raise CapabilityViolationError("lease recipient differs from requested target agent")
        if lease.allowed_operation != envelope.operation:
            raise CapabilityViolationError("lease operation differs from delegated operation")
        if not set(lease.allowed_tools).issubset(envelope.scope.allowed_tools):
            raise CapabilityViolationError("lease tools exceed delegated scope")
        if not set(lease.permitted_read_paths).issubset(envelope.scope.read_paths):
            raise CapabilityViolationError("lease read paths exceed delegated scope")
        if not set(lease.permitted_write_paths).issubset(envelope.scope.write_paths):
            raise CapabilityViolationError("lease write paths exceed delegated scope")
        if lease.network_policy != envelope.scope.network_policy:
            raise CapabilityViolationError("lease network policy differs from delegated scope")
        if not set(lease.approved_hosts).issubset(envelope.scope.approved_hosts):
            raise CapabilityViolationError("lease network hosts exceed delegated scope")
        if lease.max_runtime_seconds > envelope.scope.time_budget_seconds:
            raise CapabilityViolationError("lease runtime exceeds delegated scope")
        if lease.expected_result_schema_id != envelope.expected_result_schema_id:
            raise CapabilityViolationError("lease result schema differs from delegated contract")
        if lease.expected_evidence != envelope.expected_evidence:
            raise CapabilityViolationError("lease evidence requirements differ from delegated contract")

    def _load_lease_row(self, row: sqlite3.Row) -> DelegatedCapabilityLease:
        payload = self._decode(row, "capability lease")
        lease = reconstruct_capability_lease(payload)
        if (
            row["lease_id"] != lease.lease_id
            or row["artifact_hash"] != lease.artifact_hash
            or row["delegation_id"] != lease.delegation_id
            or row["attempt_id"] != lease.attempt_id
            or row["route_id"] != lease.route_id
            or row["recipient_agent_id"] != lease.recipient_agent_id
        ):
            raise DelegationIntegrityError("capability lease physical linkage mismatch")
        return lease

    def get_lease(self, lease_id: str) -> DelegatedCapabilityLease:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM capability_leases WHERE lease_id=?", (lease_id,)
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"capability lease not found: {lease_id}")
        return self._load_lease_row(row)

    def lease_status(self, lease_id: str) -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status FROM capability_leases WHERE lease_id=?", (lease_id,)
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"capability lease not found: {lease_id}")
        return str(row["status"])

    def cancel_delegation(self, delegation_id: str, *, reason: str, cancelled_at: str) -> None:
        event = {
            "artifact_type": "hermes.delegation_cancellation",
            "artifact_version": "1",
            "delegation_id": _normalize_text(delegation_id, "delegation_id"),
            "reason": _normalize_text(reason, "reason"),
            "cancelled_at": _normalize_timestamp(cancelled_at, "cancelled_at"),
        }
        text, checksum = self._encode(event)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                delegation = connection.execute(
                    "SELECT status FROM delegations WHERE delegation_id=?", (delegation_id,)
                ).fetchone()
                if delegation is None:
                    raise DelegationNotFoundError(f"delegation not found: {delegation_id}")
                existing = connection.execute(
                    "SELECT * FROM delegation_cancellations WHERE delegation_id=?", (delegation_id,)
                ).fetchone()
                if existing is not None:
                    if existing["canonical_payload"] != text or existing["payload_sha256"] != checksum:
                        raise CancellationConflictError("conflicting delegation cancellation replay")
                    connection.rollback()
                    return
                if delegation["status"] != "CREATED":
                    raise InvalidDelegationStateTransitionError("delegation cannot transition to cancelled")
                connection.execute(
                    "INSERT INTO delegation_cancellations VALUES (?, ?, ?, ?, ?)",
                    (delegation_id, event["reason"], event["cancelled_at"], text, checksum),
                )
                connection.execute(
                    "UPDATE delegations SET status='CANCELLED' WHERE delegation_id=?", (delegation_id,)
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def revoke_lease(self, lease_id: str, *, reason: str, revoked_at: str) -> None:
        event = {
            "artifact_type": "hermes.capability_lease_revocation",
            "artifact_version": "1",
            "lease_id": _normalize_text(lease_id, "lease_id"),
            "reason": _normalize_text(reason, "reason"),
            "revoked_at": _normalize_timestamp(revoked_at, "revoked_at"),
        }
        text, checksum = self._encode(event)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                lease = connection.execute(
                    "SELECT status FROM capability_leases WHERE lease_id=?", (lease_id,)
                ).fetchone()
                if lease is None:
                    raise DelegationNotFoundError(f"capability lease not found: {lease_id}")
                existing = connection.execute(
                    "SELECT * FROM lease_revocations WHERE lease_id=?", (lease_id,)
                ).fetchone()
                if existing is not None:
                    if existing["canonical_payload"] != text or existing["payload_sha256"] != checksum:
                        raise CancellationConflictError("conflicting capability-lease revocation replay")
                    connection.rollback()
                    return
                if lease["status"] != "ACTIVE":
                    raise InvalidDelegationStateTransitionError("capability lease cannot transition to revoked")
                connection.execute(
                    "INSERT INTO lease_revocations VALUES (?, ?, ?, ?, ?)",
                    (lease_id, event["reason"], event["revoked_at"], text, checksum),
                )
                connection.execute(
                    "UPDATE capability_leases SET status='REVOKED' WHERE lease_id=?", (lease_id,)
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def validate_lease_use(
        self,
        lease_id: str,
        *,
        recipient_agent_id: str,
        delegation_id: str,
        operation: str,
        tools: Iterable[str] = (),
        read_paths: Iterable[str] = (),
        write_paths: Iterable[str] = (),
        network_hosts: Iterable[str] = (),
        at: str,
    ) -> DelegatedCapabilityLease:
        with closing(self._connect()) as connection:
            lease_row = connection.execute(
                "SELECT * FROM capability_leases WHERE lease_id=?", (lease_id,)
            ).fetchone()
            if lease_row is None:
                raise DelegationNotFoundError(f"capability lease not found: {lease_id}")
            delegation_row = connection.execute(
                "SELECT * FROM delegations WHERE delegation_id=?", (lease_row["delegation_id"],)
            ).fetchone()
        if delegation_row is None:
            raise DelegationIntegrityError("capability lease references a missing delegation")
        lease = self._load_lease_row(lease_row)
        self._load_delegation_row(delegation_row)
        if delegation_row["status"] == "CANCELLED":
            raise InvalidDelegationStateTransitionError("delegation is cancelled")
        if lease_row["status"] == "REVOKED":
            raise LeaseRevokedError("capability lease is revoked")
        validate_capability_request(
            lease,
            recipient_agent_id=recipient_agent_id,
            delegation_id=delegation_id,
            operation=operation,
            tools=tools,
            read_paths=read_paths,
            write_paths=write_paths,
            network_hosts=network_hosts,
            at=at,
        )
        return lease

    def verify_integrity(self) -> dict[str, int]:
        counts = {"delegations": 0, "leases": 0, "cancellations": 0, "revocations": 0}
        with closing(self._connect()) as connection:
            for row in connection.execute("SELECT * FROM delegations ORDER BY delegation_id"):
                self._load_delegation_row(row)
                counts["delegations"] += 1
            for row in connection.execute("SELECT * FROM capability_leases ORDER BY lease_id"):
                self._load_lease_row(row)
                counts["leases"] += 1
            for table, key in (
                ("delegation_cancellations", "cancellations"),
                ("lease_revocations", "revocations"),
            ):
                for row in connection.execute(f"SELECT * FROM {table}"):
                    self._decode(row, key[:-1])
                    counts[key] += 1
        return counts
