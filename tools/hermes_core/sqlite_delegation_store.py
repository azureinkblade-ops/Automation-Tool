"""R12A/R12B SQLite persistence for delegation and mailbox authority.

The store owns durable identity, replay, cancellation, and revocation state. It
It does not route agents, launch processes, execute work, or project task state.
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
    LeaseExpiredError,
    LeaseRevokedError,
    build_delegated_capability_lease,
    reconstruct_capability_lease,
    reconstruct_delegated_task,
    validate_capability_request,
    _normalize_text,
    _normalize_timestamp,
    _parse_timestamp,
)
from .hashing import canonical_json, sha256_payload
from .delegation_delivery import (
    AgentMailboxMessage,
    DelegationReceipt,
    InvalidAcceptanceTransitionError,
    InvalidMessageStateError,
    MailboxDeliveryConflictError,
    MailboxDeliveryEvent,
    MailboxMessageNotFoundError,
    ReceiverAcceptanceConflictError,
    ReceiverMismatchError,
    build_delivery_event,
    build_mailbox_message,
    reconstruct_delegation_receipt,
    reconstruct_delivery_event,
    reconstruct_mailbox_message,
)


SCHEMA_VERSION = 2


_R12B_SCHEMA = (
    """CREATE TABLE agent_mailbox_messages (
        message_id TEXT PRIMARY KEY,
        artifact_hash TEXT NOT NULL,
        mailbox_id TEXT NOT NULL,
        mailbox_sequence INTEGER NOT NULL,
        message_type TEXT NOT NULL,
        sender_agent_id TEXT NOT NULL,
        recipient_agent_id TEXT NOT NULL,
        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
        attempt_id TEXT,
        idempotency_key TEXT NOT NULL,
        payload_schema_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        canonical_payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        message_body TEXT NOT NULL,
        message_body_sha256 TEXT NOT NULL,
        UNIQUE(mailbox_id, mailbox_sequence),
        UNIQUE(mailbox_id, idempotency_key)
    )""",
    """CREATE TABLE agent_mailbox_delivery_events (
        event_id TEXT PRIMARY KEY,
        artifact_hash TEXT NOT NULL,
        message_id TEXT NOT NULL REFERENCES agent_mailbox_messages(message_id),
        mailbox_id TEXT NOT NULL,
        event_sequence INTEGER NOT NULL,
        previous_event_hash TEXT,
        state TEXT NOT NULL CHECK (state IN ('CLAIMED', 'ACKNOWLEDGED', 'DEAD_LETTER')),
        actor_agent_id TEXT NOT NULL,
        claim_token TEXT,
        claim_expires_at TEXT,
        occurred_at TEXT NOT NULL,
        canonical_payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        UNIQUE(message_id, event_sequence)
    )""",
    """CREATE TABLE delegation_receipts (
        receipt_id TEXT PRIMARY KEY,
        artifact_hash TEXT NOT NULL,
        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
        attempt_id TEXT NOT NULL UNIQUE,
        capability_lease_id TEXT NOT NULL REFERENCES capability_leases(lease_id),
        receiver_agent_id TEXT NOT NULL,
        source_message_id TEXT NOT NULL REFERENCES agent_mailbox_messages(message_id),
        outcome TEXT NOT NULL CHECK (outcome IN ('ACCEPTED', 'REJECTED')),
        decided_at TEXT NOT NULL,
        canonical_payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
    )""",
)


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
                if row is None:
                    raise DelegationStoreSchemaError("unsupported delegation-store schema version")
                if row["version"] == 1:
                    self._migrate_v1_to_v2(connection)
                elif row["version"] != SCHEMA_VERSION:
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
                    INSERT INTO delegation_schema_version(singleton, version) VALUES (1, 2);

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

                    CREATE TABLE agent_mailbox_messages (
                        message_id TEXT PRIMARY KEY,
                        artifact_hash TEXT NOT NULL,
                        mailbox_id TEXT NOT NULL,
                        mailbox_sequence INTEGER NOT NULL,
                        message_type TEXT NOT NULL,
                        sender_agent_id TEXT NOT NULL,
                        recipient_agent_id TEXT NOT NULL,
                        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
                        attempt_id TEXT,
                        idempotency_key TEXT NOT NULL,
                        payload_schema_id TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        message_body TEXT NOT NULL,
                        message_body_sha256 TEXT NOT NULL,
                        UNIQUE(mailbox_id, mailbox_sequence),
                        UNIQUE(mailbox_id, idempotency_key)
                    );

                    CREATE TABLE agent_mailbox_delivery_events (
                        event_id TEXT PRIMARY KEY,
                        artifact_hash TEXT NOT NULL,
                        message_id TEXT NOT NULL REFERENCES agent_mailbox_messages(message_id),
                        mailbox_id TEXT NOT NULL,
                        event_sequence INTEGER NOT NULL,
                        previous_event_hash TEXT,
                        state TEXT NOT NULL CHECK (state IN ('CLAIMED', 'ACKNOWLEDGED', 'DEAD_LETTER')),
                        actor_agent_id TEXT NOT NULL,
                        claim_token TEXT,
                        claim_expires_at TEXT,
                        occurred_at TEXT NOT NULL,
                        canonical_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        UNIQUE(message_id, event_sequence)
                    );

                    CREATE TABLE delegation_receipts (
                        receipt_id TEXT PRIMARY KEY,
                        artifact_hash TEXT NOT NULL,
                        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
                        attempt_id TEXT NOT NULL UNIQUE,
                        capability_lease_id TEXT NOT NULL REFERENCES capability_leases(lease_id),
                        receiver_agent_id TEXT NOT NULL,
                        source_message_id TEXT NOT NULL REFERENCES agent_mailbox_messages(message_id),
                        outcome TEXT NOT NULL CHECK (outcome IN ('ACCEPTED', 'REJECTED')),
                        decided_at TEXT NOT NULL,
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
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            present = {
                row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            new_tables = {
                "agent_mailbox_messages",
                "agent_mailbox_delivery_events",
                "delegation_receipts",
            }
            if present & new_tables:
                raise DelegationStoreSchemaError("partial R12B migration state")
            for statement in _R12B_SCHEMA:
                connection.execute(statement)
            connection.execute(
                "UPDATE delegation_schema_version SET version=? WHERE singleton=1",
                (SCHEMA_VERSION,),
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
            "agent_mailbox_messages",
            "agent_mailbox_delivery_events",
            "delegation_receipts",
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

    @staticmethod
    def _decode_message_body(row: sqlite3.Row) -> dict[str, Any]:
        try:
            body = json.loads(row["message_body"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DelegationIntegrityError("mailbox message body is corrupt") from exc
        if canonical_json(body) != row["message_body"]:
            raise DelegationIntegrityError("mailbox message body is not canonical JSON")
        if sha256_payload(body) != row["message_body_sha256"] or row["payload_hash"] != row["message_body_sha256"]:
            raise DelegationIntegrityError("mailbox message body checksum mismatch")
        return body

    def _load_message_row(self, row: sqlite3.Row) -> AgentMailboxMessage:
        payload = self._decode(row, "mailbox message")
        message = reconstruct_mailbox_message(payload)
        self._decode_message_body(row)
        if (
            row["message_id"] != message.message_id
            or row["artifact_hash"] != message.artifact_hash
            or row["mailbox_id"] != message.mailbox_id
            or row["mailbox_sequence"] != message.mailbox_sequence
            or row["message_type"] != message.message_type
            or row["recipient_agent_id"] != message.recipient_agent_id
            or row["delegation_id"] != message.delegation_id
            or row["attempt_id"] != message.attempt_id
            or row["idempotency_key"] != message.idempotency_key
            or row["payload_hash"] != message.payload_hash
        ):
            raise DelegationIntegrityError("mailbox message physical linkage mismatch")
        return message

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        *,
        mailbox_id: str,
        message_type: str,
        sender_agent_id: str,
        recipient_agent_id: str,
        delegation_id: str,
        attempt_id: Optional[str],
        idempotency_key: str,
        payload_schema_id: str,
        body: dict[str, Any],
        created_at: str,
    ) -> AgentMailboxMessage:
        body_text = canonical_json(body)
        body_hash = sha256_payload(body)
        existing = connection.execute(
            "SELECT * FROM agent_mailbox_messages WHERE mailbox_id=? AND idempotency_key=?",
            (mailbox_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            durable = self._load_message_row(existing)
            expected = build_mailbox_message(
                mailbox_id=mailbox_id,
                mailbox_sequence=durable.mailbox_sequence,
                message_type=message_type,
                sender_agent_id=sender_agent_id,
                recipient_agent_id=recipient_agent_id,
                delegation_id=delegation_id,
                attempt_id=attempt_id,
                idempotency_key=idempotency_key,
                payload_schema_id=payload_schema_id,
                payload_hash=body_hash,
                created_at=created_at,
            )
            if durable.artifact_hash != expected.artifact_hash or existing["message_body"] != body_text:
                raise MailboxDeliveryConflictError("mailbox idempotency key has divergent material")
            return durable
        sequence = connection.execute(
            "SELECT COALESCE(MAX(mailbox_sequence), 0) + 1 FROM agent_mailbox_messages WHERE mailbox_id=?",
            (mailbox_id,),
        ).fetchone()[0]
        message = build_mailbox_message(
            mailbox_id=mailbox_id,
            mailbox_sequence=sequence,
            message_type=message_type,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=recipient_agent_id,
            delegation_id=delegation_id,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            payload_schema_id=payload_schema_id,
            payload_hash=body_hash,
            created_at=created_at,
        )
        text, checksum = self._encode(message.to_canonical_dict())
        connection.execute(
            """INSERT INTO agent_mailbox_messages(
                message_id, artifact_hash, mailbox_id, mailbox_sequence,
                message_type, sender_agent_id, recipient_agent_id,
                delegation_id, attempt_id, idempotency_key, payload_schema_id,
                payload_hash, created_at, canonical_payload, payload_sha256,
                message_body, message_body_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message.message_id, message.artifact_hash, message.mailbox_id,
                message.mailbox_sequence, message.message_type,
                message.sender_agent_id, message.recipient_agent_id,
                message.delegation_id, message.attempt_id,
                message.idempotency_key, message.payload_schema_id,
                message.payload_hash, message.created_at, text, checksum,
                body_text, body_hash,
            ),
        )
        return message

    def deliver_delegation(
        self,
        lease_id: str,
        *,
        sender_agent_id: str,
        delivered_at: str,
        idempotency_key: Optional[str] = None,
    ) -> AgentMailboxMessage:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                lease_row = connection.execute(
                    "SELECT * FROM capability_leases WHERE lease_id=?", (lease_id,)
                ).fetchone()
                if lease_row is None:
                    raise DelegationNotFoundError(f"capability lease not found: {lease_id}")
                delegation_row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id=?",
                    (lease_row["delegation_id"],),
                ).fetchone()
                if delegation_row is None:
                    raise DelegationIntegrityError("capability lease references a missing delegation")
                lease = self._load_lease_row(lease_row)
                envelope = self._load_delegation_row(delegation_row)
                if delegation_row["status"] == "CANCELLED":
                    raise InvalidDelegationStateTransitionError("cancelled delegation cannot be delivered")
                if lease_row["status"] == "REVOKED":
                    raise LeaseRevokedError("revoked capability lease cannot be delivered")
                validate_capability_request(
                    lease,
                    recipient_agent_id=lease.recipient_agent_id,
                    delegation_id=envelope.delegation_id,
                    operation=envelope.operation,
                    at=delivered_at,
                )
                key = idempotency_key or f"delegation:{envelope.delegation_id}:{lease.attempt_id}:{lease.route_id}"
                message = self._insert_message(
                    connection,
                    mailbox_id=lease.recipient_agent_id,
                    message_type="DELEGATION",
                    sender_agent_id=sender_agent_id,
                    recipient_agent_id=lease.recipient_agent_id,
                    delegation_id=envelope.delegation_id,
                    attempt_id=lease.attempt_id,
                    idempotency_key=key,
                    payload_schema_id="hermes.delegation_delivery/v1",
                    body={
                        "delegated_task": envelope.to_canonical_dict(),
                        "capability_lease": lease.to_canonical_dict(),
                    },
                    created_at=delivered_at,
                )
                connection.commit()
                return message
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise MailboxDeliveryConflictError("mailbox delivery durable uniqueness conflict") from exc
            except Exception:
                connection.rollback()
                raise

    def get_message(self, message_id: str) -> AgentMailboxMessage:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM agent_mailbox_messages WHERE message_id=?", (message_id,)
            ).fetchone()
        if row is None:
            raise MailboxMessageNotFoundError(f"mailbox message not found: {message_id}")
        return self._load_message_row(row)

    def message_body(self, message_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM agent_mailbox_messages WHERE message_id=?", (message_id,)
            ).fetchone()
        if row is None:
            raise MailboxMessageNotFoundError(f"mailbox message not found: {message_id}")
        self._load_message_row(row)
        return self._decode_message_body(row)

    def list_mailbox(self, mailbox_id: str) -> list[AgentMailboxMessage]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_mailbox_messages WHERE mailbox_id=? ORDER BY mailbox_sequence",
                (mailbox_id,),
            ).fetchall()
        return [self._load_message_row(row) for row in rows]

    def _load_event_row(self, row: sqlite3.Row) -> MailboxDeliveryEvent:
        event = reconstruct_delivery_event(self._decode(row, "mailbox delivery event"))
        if (
            row["event_id"] != event.event_id
            or row["artifact_hash"] != event.artifact_hash
            or row["message_id"] != event.message_id
            or row["mailbox_id"] != event.mailbox_id
            or row["event_sequence"] != event.event_sequence
            or row["previous_event_hash"] != event.previous_event_hash
            or row["state"] != event.state
            or row["claim_token"] != event.claim_token
        ):
            raise DelegationIntegrityError("mailbox delivery-event physical linkage mismatch")
        return event

    def _latest_event(self, connection: sqlite3.Connection, message_id: str) -> Optional[MailboxDeliveryEvent]:
        row = connection.execute(
            "SELECT * FROM agent_mailbox_delivery_events WHERE message_id=? ORDER BY event_sequence DESC LIMIT 1",
            (message_id,),
        ).fetchone()
        return None if row is None else self._load_event_row(row)

    def _insert_event(self, connection: sqlite3.Connection, event: MailboxDeliveryEvent) -> None:
        event.verify_hash()
        text, checksum = self._encode(event.to_canonical_dict())
        connection.execute(
            """INSERT INTO agent_mailbox_delivery_events(
                event_id, artifact_hash, message_id, mailbox_id, event_sequence,
                previous_event_hash, state, actor_agent_id, claim_token,
                claim_expires_at, occurred_at, canonical_payload, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id, event.artifact_hash, event.message_id,
                event.mailbox_id, event.event_sequence, event.previous_event_hash,
                event.state, event.actor_agent_id, event.claim_token,
                event.claim_expires_at, event.occurred_at, text, checksum,
            ),
        )

    def claim_message(
        self,
        message_id: str,
        *,
        recipient_agent_id: str,
        claim_token: str,
        claimed_at: str,
        claim_expires_at: str,
    ) -> MailboxDeliveryEvent:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM agent_mailbox_messages WHERE message_id=?", (message_id,)
                ).fetchone()
                if row is None:
                    raise MailboxMessageNotFoundError(f"mailbox message not found: {message_id}")
                message = self._load_message_row(row)
                if message.recipient_agent_id != recipient_agent_id:
                    raise ReceiverMismatchError("only the registered recipient may claim a message")
                latest = self._latest_event(connection, message_id)
                if latest is not None and latest.state == "ACKNOWLEDGED":
                    raise InvalidMessageStateError("acknowledged message cannot be reclaimed")
                if latest is not None and latest.state == "CLAIMED":
                    if latest.claim_token == claim_token:
                        expected = build_delivery_event(
                            message_id=message.message_id,
                            message_hash=message.artifact_hash,
                            mailbox_id=message.mailbox_id,
                            event_sequence=latest.event_sequence,
                            previous_event_hash=latest.previous_event_hash,
                            state="CLAIMED",
                            actor_agent_id=recipient_agent_id,
                            claim_token=claim_token,
                            claim_expires_at=claim_expires_at,
                            occurred_at=claimed_at,
                        )
                        if expected.artifact_hash != latest.artifact_hash:
                            raise InvalidMessageStateError("claim token replay has divergent material")
                        connection.rollback()
                        return latest
                    if _parse_timestamp(claimed_at) < _parse_timestamp(latest.claim_expires_at or latest.occurred_at):
                        raise InvalidMessageStateError("message has an active claim")
                sequence = 1 if latest is None else latest.event_sequence + 1
                event = build_delivery_event(
                    message_id=message.message_id,
                    message_hash=message.artifact_hash,
                    mailbox_id=message.mailbox_id,
                    event_sequence=sequence,
                    previous_event_hash=None if latest is None else latest.artifact_hash,
                    state="CLAIMED",
                    actor_agent_id=recipient_agent_id,
                    claim_token=claim_token,
                    claim_expires_at=claim_expires_at,
                    occurred_at=claimed_at,
                )
                self._insert_event(connection, event)
                connection.commit()
                return event
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise InvalidMessageStateError("mailbox claim durable uniqueness conflict") from exc
            except Exception:
                connection.rollback()
                raise

    def acknowledge_message(
        self,
        message_id: str,
        *,
        recipient_agent_id: str,
        claim_token: str,
        acknowledged_at: str,
    ) -> MailboxDeliveryEvent:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM agent_mailbox_messages WHERE message_id=?", (message_id,)
                ).fetchone()
                if row is None:
                    raise MailboxMessageNotFoundError(f"mailbox message not found: {message_id}")
                message = self._load_message_row(row)
                if message.recipient_agent_id != recipient_agent_id:
                    raise ReceiverMismatchError("only the registered recipient may acknowledge a message")
                if message.message_type not in {"DELEGATION", "CANCELLATION", "REVOCATION", "RESULT_DELIVERY"}:
                    raise InvalidMessageStateError("message type is not recipient-acknowledgeable")
                latest = self._latest_event(connection, message_id)
                if latest is not None and latest.state == "ACKNOWLEDGED":
                    if latest.claim_token == claim_token:
                        expected = build_delivery_event(
                            message_id=message.message_id,
                            message_hash=message.artifact_hash,
                            mailbox_id=message.mailbox_id,
                            event_sequence=latest.event_sequence,
                            previous_event_hash=latest.previous_event_hash,
                            state="ACKNOWLEDGED",
                            actor_agent_id=recipient_agent_id,
                            claim_token=claim_token,
                            claim_expires_at=latest.claim_expires_at,
                            occurred_at=acknowledged_at,
                        )
                        if expected.artifact_hash != latest.artifact_hash:
                            raise InvalidMessageStateError("acknowledgement replay has divergent material")
                        connection.rollback()
                        return latest
                    raise InvalidMessageStateError("message was acknowledged under a different claim")
                if latest is None or latest.state != "CLAIMED" or latest.claim_token != claim_token:
                    raise InvalidMessageStateError("acknowledgement requires the active claim token")
                if _parse_timestamp(acknowledged_at) >= _parse_timestamp(latest.claim_expires_at or latest.occurred_at):
                    raise InvalidMessageStateError("claim expired before acknowledgement")
                event = build_delivery_event(
                    message_id=message.message_id,
                    message_hash=message.artifact_hash,
                    mailbox_id=message.mailbox_id,
                    event_sequence=latest.event_sequence + 1,
                    previous_event_hash=latest.artifact_hash,
                    state="ACKNOWLEDGED",
                    actor_agent_id=recipient_agent_id,
                    claim_token=claim_token,
                    claim_expires_at=latest.claim_expires_at,
                    occurred_at=acknowledged_at,
                )
                self._insert_event(connection, event)
                connection.commit()
                return event
            except Exception:
                connection.rollback()
                raise

    def delivery_state(self, message_id: str) -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM agent_mailbox_messages WHERE message_id=?", (message_id,)
            ).fetchone()
            if row is None:
                raise MailboxMessageNotFoundError(f"mailbox message not found: {message_id}")
            latest = self._latest_event(connection, message_id)
        return "PENDING" if latest is None else latest.state

    def _load_receipt_row(self, row: sqlite3.Row) -> DelegationReceipt:
        receipt = reconstruct_delegation_receipt(self._decode(row, "delegation receipt"))
        if (
            row["receipt_id"] != receipt.receipt_id
            or row["artifact_hash"] != receipt.artifact_hash
            or row["delegation_id"] != receipt.delegation_id
            or row["attempt_id"] != receipt.attempt_id
            or row["capability_lease_id"] != receipt.capability_lease_id
            or row["receiver_agent_id"] != receipt.receiver_agent_id
            or row["outcome"] != receipt.outcome
        ):
            raise DelegationIntegrityError("delegation receipt physical linkage mismatch")
        return receipt

    @staticmethod
    def _validate_receipt_lineage(
        receipt: DelegationReceipt,
        envelope: DelegatedTaskEnvelope,
        lease: DelegatedCapabilityLease,
        message: AgentMailboxMessage,
    ) -> None:
        checks = (
            (receipt.delegation_id, envelope.delegation_id),
            (receipt.delegated_task_hash, envelope.artifact_hash),
            (receipt.capability_lease_id, lease.lease_id),
            (receipt.capability_lease_hash, lease.artifact_hash),
            (receipt.authorization_id, lease.authorization_id),
            (receipt.authorization_hash, lease.authorization_hash),
            (receipt.attempt_id, lease.attempt_id),
            (receipt.attempt_hash, lease.attempt_hash),
            (receipt.route_id, lease.route_id),
            (receipt.route_hash, lease.route_hash),
            (receipt.receiver_agent_id, lease.recipient_agent_id),
            (receipt.receiver_descriptor_hash, lease.worker_descriptor_hash),
            (message.delegation_id, envelope.delegation_id),
            (message.attempt_id, lease.attempt_id),
            (message.recipient_agent_id, lease.recipient_agent_id),
        )
        if any(actual != expected for actual, expected in checks):
            raise InvalidAcceptanceTransitionError("receipt lineage does not match durable delegation delivery")

    def record_receipt(
        self,
        receipt: DelegationReceipt,
        *,
        source_message_id: str,
        hermes_recipient_agent_id: str = "hermes-execution-authority",
    ) -> DelegationReceipt:
        receipt.verify_hash()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM delegation_receipts WHERE attempt_id=?", (receipt.attempt_id,)
                ).fetchone()
                if existing is not None:
                    durable = self._load_receipt_row(existing)
                    if durable.artifact_hash != receipt.artifact_hash or existing["source_message_id"] != source_message_id:
                        raise ReceiverAcceptanceConflictError("attempt already has a divergent durable receipt")
                    connection.rollback()
                    return durable
                message_row = connection.execute(
                    "SELECT * FROM agent_mailbox_messages WHERE message_id=?", (source_message_id,)
                ).fetchone()
                if message_row is None:
                    raise MailboxMessageNotFoundError(f"mailbox message not found: {source_message_id}")
                message = self._load_message_row(message_row)
                if message.message_type != "DELEGATION":
                    raise InvalidAcceptanceTransitionError("receipt source must be a delegation delivery")
                delegation_row = connection.execute(
                    "SELECT * FROM delegations WHERE delegation_id=?", (message.delegation_id,)
                ).fetchone()
                lease_row = connection.execute(
                    "SELECT * FROM capability_leases WHERE attempt_id=?", (message.attempt_id,)
                ).fetchone()
                if delegation_row is None or lease_row is None:
                    raise DelegationIntegrityError("receipt source lineage is incomplete")
                envelope = self._load_delegation_row(delegation_row)
                lease = self._load_lease_row(lease_row)
                self._validate_receipt_lineage(receipt, envelope, lease, message)
                latest = self._latest_event(connection, source_message_id)
                if latest is None or latest.state != "CLAIMED" or latest.actor_agent_id != receipt.receiver_agent_id:
                    raise InvalidAcceptanceTransitionError("receiver must hold a durable delivery claim before receipt")
                if _parse_timestamp(receipt.decided_at) >= _parse_timestamp(latest.claim_expires_at or latest.occurred_at):
                    raise InvalidAcceptanceTransitionError("receiver claim expired before receipt decision")
                if receipt.outcome == "ACCEPTED":
                    if delegation_row["status"] == "CANCELLED":
                        raise InvalidAcceptanceTransitionError("cancelled delegation cannot be accepted")
                    if lease_row["status"] == "REVOKED":
                        raise LeaseRevokedError("revoked lease cannot be accepted")
                    if _parse_timestamp(receipt.decided_at) >= _parse_timestamp(lease.expires_at):
                        raise LeaseExpiredError("expired lease cannot be accepted")
                text, checksum = self._encode(receipt.to_canonical_dict())
                connection.execute(
                    """INSERT INTO delegation_receipts(
                        receipt_id, artifact_hash, delegation_id, attempt_id,
                        capability_lease_id, receiver_agent_id, source_message_id,
                        outcome, decided_at, canonical_payload, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        receipt.receipt_id, receipt.artifact_hash,
                        receipt.delegation_id, receipt.attempt_id,
                        receipt.capability_lease_id, receipt.receiver_agent_id,
                        source_message_id, receipt.outcome, receipt.decided_at,
                        text, checksum,
                    ),
                )
                self._insert_message(
                    connection,
                    mailbox_id=hermes_recipient_agent_id,
                    message_type="RECEIPT",
                    sender_agent_id=receipt.receiver_agent_id,
                    recipient_agent_id=hermes_recipient_agent_id,
                    delegation_id=receipt.delegation_id,
                    attempt_id=receipt.attempt_id,
                    idempotency_key=f"receipt:{receipt.attempt_id}",
                    payload_schema_id="hermes.delegation_receipt/v1",
                    body=receipt.to_canonical_dict(),
                    created_at=receipt.decided_at,
                )
                connection.commit()
                return receipt
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ReceiverAcceptanceConflictError("receiver receipt durable uniqueness conflict") from exc
            except Exception:
                connection.rollback()
                raise

    def get_receipt(self, attempt_id: str) -> DelegationReceipt:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM delegation_receipts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"delegation receipt not found for attempt: {attempt_id}")
        return self._load_receipt_row(row)

    def verify_integrity(self) -> dict[str, int]:
        counts = {
            "delegations": 0, "leases": 0, "cancellations": 0,
            "revocations": 0, "mailbox_messages": 0,
            "delivery_events": 0, "receipts": 0,
        }
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
            for row in connection.execute("SELECT * FROM agent_mailbox_messages ORDER BY mailbox_id, mailbox_sequence"):
                self._load_message_row(row)
                counts["mailbox_messages"] += 1
            previous_by_message: dict[str, str] = {}
            for row in connection.execute("SELECT * FROM agent_mailbox_delivery_events ORDER BY message_id, event_sequence"):
                event = self._load_event_row(row)
                if event.previous_event_hash != previous_by_message.get(event.message_id):
                    raise DelegationIntegrityError("mailbox delivery-event hash chain mismatch")
                previous_by_message[event.message_id] = event.artifact_hash
                counts["delivery_events"] += 1
            for row in connection.execute("SELECT * FROM delegation_receipts ORDER BY attempt_id"):
                self._load_receipt_row(row)
                counts["receipts"] += 1
        return counts
