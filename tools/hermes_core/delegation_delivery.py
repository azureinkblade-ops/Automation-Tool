"""Canonical R12B mailbox-delivery and receiver-receipt artifacts.

This module is deliberately inert. It validates and hashes protocol artifacts;
it cannot launch a receiver, execute delegated work, or project task state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional

from .delegated_task import (
    ARTIFACT_VERSION,
    DelegationDomainError,
    DelegationIntegrityError,
    InvalidCanonicalEnvelopeError,
    _normalize_hash,
    _normalize_int,
    _normalize_text,
    _normalize_timestamp,
    _parse_timestamp,
)
from .hashing import canonical_json, sha256_payload


MAILBOX_MESSAGE_ARTIFACT_TYPE = "hermes.agent_mailbox_message"
DELIVERY_EVENT_ARTIFACT_TYPE = "hermes.agent_mailbox_delivery_event"
DELEGATION_RECEIPT_ARTIFACT_TYPE = "hermes.delegation_receipt"

MESSAGE_TYPES = frozenset({
    "DELEGATION", "RECEIPT", "PROGRESS", "RESULT", "CANCELLATION",
    "REVOCATION", "RESULT_DELIVERY",
})
DELIVERY_STATES = frozenset({"CLAIMED", "ACKNOWLEDGED", "DEAD_LETTER"})
RECEIPT_OUTCOMES = frozenset({"ACCEPTED", "REJECTED"})
REJECTION_REASON_CODES = frozenset({
    "UNSUPPORTED_ARTIFACT_VERSION",
    "INVALID_ENVELOPE_HASH",
    "INVALID_LINEAGE",
    "INVALID_OR_EXPIRED_LEASE",
    "REVOKED_OR_CANCELLED",
    "WRONG_RECEIVER",
    "UNSUPPORTED_OPERATION",
    "INPUT_MISSING_OR_HASH_MISMATCH",
    "SCOPE_UNSUPPORTED",
    "RESULT_SCHEMA_UNSUPPORTED",
    "INTERNAL_RECEIVER_ERROR",
})


class MailboxDeliveryConflictError(DelegationDomainError):
    """A mailbox identity was replayed with divergent canonical material."""


class MailboxMessageNotFoundError(DelegationDomainError):
    """The requested durable mailbox message does not exist."""


class ReceiverMismatchError(DelegationDomainError):
    """A mailbox or receipt operation names the wrong receiver."""


class ReceiverAcceptanceConflictError(DelegationDomainError):
    """An attempt already has a divergent durable receipt."""


class InvalidAcceptanceTransitionError(DelegationDomainError):
    """The requested acceptance transition is forbidden."""


class InvalidMessageStateError(DelegationDomainError):
    """A mailbox delivery event is invalid for current durable state."""


@dataclass(frozen=True)
class AgentMailboxMessage:
    message_id: str
    mailbox_id: str
    mailbox_sequence: int
    message_type: str
    sender_agent_id: str
    recipient_agent_id: str
    delegation_id: str
    attempt_id: Optional[str]
    idempotency_key: str
    payload_schema_id: str
    payload_hash: str
    created_at: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_hash: bool = True, include_id: bool = True) -> dict[str, Any]:
        payload = {
            "mailbox_id": self.mailbox_id,
            "mailbox_sequence": self.mailbox_sequence,
            "message_type": self.message_type,
            "sender_agent_id": self.sender_agent_id,
            "recipient_agent_id": self.recipient_agent_id,
            "delegation_id": self.delegation_id,
            "attempt_id": self.attempt_id,
            "idempotency_key": self.idempotency_key,
            "payload_schema_id": self.payload_schema_id,
            "payload_hash": self.payload_hash,
            "created_at": self.created_at,
            "artifact_version": self.artifact_version,
        }
        if include_id:
            payload["message_id"] = self.message_id
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> None:
        expected_id = f"mailmsg-{sha256_payload({'mailbox_id': self.mailbox_id, 'idempotency_key': self.idempotency_key})}"
        if self.message_id != expected_id:
            raise DelegationIntegrityError("mailbox message identity mismatch")
        if sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("mailbox message artifact hash mismatch")


def build_mailbox_message(
    *, mailbox_id: str, mailbox_sequence: int, message_type: str,
    sender_agent_id: str, recipient_agent_id: str, delegation_id: str,
    attempt_id: Optional[str], idempotency_key: str, payload_schema_id: str,
    payload_hash: str, created_at: str,
) -> AgentMailboxMessage:
    mailbox = _normalize_text(mailbox_id, "mailbox_id")
    recipient = _normalize_text(recipient_agent_id, "recipient_agent_id")
    if mailbox != recipient:
        raise ReceiverMismatchError("mailbox_id must equal recipient_agent_id")
    kind = _normalize_text(message_type, "message_type")
    if kind not in MESSAGE_TYPES:
        raise InvalidCanonicalEnvelopeError("unsupported mailbox message_type")
    key = _normalize_text(idempotency_key, "idempotency_key")
    message_id = f"mailmsg-{sha256_payload({'mailbox_id': mailbox, 'idempotency_key': key})}"
    message = AgentMailboxMessage(
        message_id=message_id,
        mailbox_id=mailbox,
        mailbox_sequence=_normalize_int(mailbox_sequence, "mailbox_sequence", minimum=1),
        message_type=kind,
        sender_agent_id=_normalize_text(sender_agent_id, "sender_agent_id"),
        recipient_agent_id=recipient,
        delegation_id=_normalize_text(delegation_id, "delegation_id"),
        attempt_id=None if attempt_id is None else _normalize_text(attempt_id, "attempt_id"),
        idempotency_key=key,
        payload_schema_id=_normalize_text(payload_schema_id, "payload_schema_id"),
        payload_hash=_normalize_hash(payload_hash, "payload_hash"),
        created_at=_normalize_timestamp(created_at, "created_at"),
        artifact_version=ARTIFACT_VERSION,
        artifact_hash="",
    )
    return replace(message, artifact_hash=sha256_payload(message.to_canonical_dict(include_hash=False)))


def reconstruct_mailbox_message(payload: Mapping[str, Any]) -> AgentMailboxMessage:
    required = set(AgentMailboxMessage.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise InvalidCanonicalEnvelopeError(f"mailbox message requires exactly {sorted(required)}")
    rebuilt = build_mailbox_message(**{
        key: payload[key] for key in required
        if key not in {"message_id", "artifact_version", "artifact_hash"}
    })
    if payload["artifact_version"] != ARTIFACT_VERSION:
        raise InvalidCanonicalEnvelopeError("unsupported mailbox message schema")
    if payload["message_id"] != rebuilt.message_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("mailbox message identity or hash mismatch")
    return rebuilt


@dataclass(frozen=True)
class MailboxDeliveryEvent:
    event_id: str
    message_id: str
    message_hash: str
    mailbox_id: str
    event_sequence: int
    previous_event_hash: Optional[str]
    state: str
    actor_agent_id: str
    claim_token: Optional[str]
    claim_expires_at: Optional[str]
    occurred_at: str
    reason_summary: Optional[str]
    artifact_type: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_hash: bool = True, include_id: bool = True) -> dict[str, Any]:
        payload = {
            "message_id": self.message_id,
            "message_hash": self.message_hash,
            "mailbox_id": self.mailbox_id,
            "event_sequence": self.event_sequence,
            "previous_event_hash": self.previous_event_hash,
            "state": self.state,
            "actor_agent_id": self.actor_agent_id,
            "claim_token": self.claim_token,
            "claim_expires_at": self.claim_expires_at,
            "occurred_at": self.occurred_at,
            "reason_summary": self.reason_summary,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
        }
        if include_id:
            payload["event_id"] = self.event_id
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def verify_hash(self) -> None:
        expected_id = f"mailevent-{sha256_payload(self.to_canonical_dict(include_hash=False, include_id=False))}"
        if self.event_id != expected_id:
            raise DelegationIntegrityError("mailbox delivery-event identity mismatch")
        if sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("mailbox delivery-event artifact hash mismatch")


def build_delivery_event(
    *, message_id: str, message_hash: str, mailbox_id: str, event_sequence: int,
    previous_event_hash: Optional[str], state: str, actor_agent_id: str,
    claim_token: Optional[str], claim_expires_at: Optional[str], occurred_at: str,
    reason_summary: Optional[str] = None,
) -> MailboxDeliveryEvent:
    normalized_state = _normalize_text(state, "state")
    if normalized_state not in DELIVERY_STATES:
        raise InvalidCanonicalEnvelopeError("unsupported mailbox delivery state")
    token = None if claim_token is None else _normalize_text(claim_token, "claim_token")
    expires = _normalize_timestamp(claim_expires_at, "claim_expires_at", optional=True)
    if normalized_state in {"CLAIMED", "ACKNOWLEDGED"} and token is None:
        raise InvalidCanonicalEnvelopeError("claimed and acknowledged events require claim_token")
    if normalized_state == "CLAIMED" and expires is None:
        raise InvalidCanonicalEnvelopeError("claimed events require claim_expires_at")
    event = MailboxDeliveryEvent(
        event_id="",
        message_id=_normalize_text(message_id, "message_id"),
        message_hash=_normalize_hash(message_hash, "message_hash"),
        mailbox_id=_normalize_text(mailbox_id, "mailbox_id"),
        event_sequence=_normalize_int(event_sequence, "event_sequence", minimum=1),
        previous_event_hash=None if previous_event_hash is None else _normalize_hash(previous_event_hash, "previous_event_hash"),
        state=normalized_state,
        actor_agent_id=_normalize_text(actor_agent_id, "actor_agent_id"),
        claim_token=token,
        claim_expires_at=expires,
        occurred_at=_normalize_timestamp(occurred_at, "occurred_at"),
        reason_summary=None if reason_summary is None else _normalize_text(reason_summary, "reason_summary"),
        artifact_type=DELIVERY_EVENT_ARTIFACT_TYPE,
        artifact_version=ARTIFACT_VERSION,
        artifact_hash="",
    )
    event = replace(event, event_id=f"mailevent-{sha256_payload(event.to_canonical_dict(include_hash=False, include_id=False))}")
    return replace(event, artifact_hash=sha256_payload(event.to_canonical_dict(include_hash=False)))


def reconstruct_delivery_event(payload: Mapping[str, Any]) -> MailboxDeliveryEvent:
    required = set(MailboxDeliveryEvent.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise InvalidCanonicalEnvelopeError(f"delivery event requires exactly {sorted(required)}")
    if payload["artifact_type"] != DELIVERY_EVENT_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION:
        raise InvalidCanonicalEnvelopeError("unsupported delivery-event schema")
    rebuilt = build_delivery_event(**{
        key: payload[key] for key in required
        if key not in {"event_id", "artifact_type", "artifact_version", "artifact_hash"}
    })
    if payload["event_id"] != rebuilt.event_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("delivery-event identity or hash mismatch")
    return rebuilt


@dataclass(frozen=True)
class DelegationReceipt:
    receipt_id: str
    delegation_id: str
    delegated_task_hash: str
    capability_lease_id: str
    capability_lease_hash: str
    authorization_id: str
    authorization_hash: str
    attempt_id: str
    attempt_hash: str
    route_id: str
    route_hash: str
    launch_attempt_id: str
    launch_attempt_hash: str
    receiver_agent_id: str
    receiver_descriptor_hash: str
    receiver_implementation: str
    receiver_version: str
    runtime_run_id: str
    outcome: str
    reason_code: Optional[str]
    reason_summary: Optional[str]
    received_at: str
    decided_at: str
    artifact_type: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_hash: bool = True, include_id: bool = True) -> dict[str, Any]:
        payload = {key: getattr(self, key) for key in self.__dataclass_fields__ if key not in {"receipt_id", "artifact_hash"}}
        if include_id:
            payload["receipt_id"] = self.receipt_id
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def verify_hash(self) -> None:
        expected_id = f"receipt-{sha256_payload(self.to_canonical_dict(include_hash=False, include_id=False))}"
        if self.receipt_id != expected_id:
            raise DelegationIntegrityError("delegation receipt identity mismatch")
        if sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("delegation receipt artifact hash mismatch")


def build_delegation_receipt(**values: Any) -> DelegationReceipt:
    outcome = _normalize_text(values["outcome"], "outcome")
    if outcome not in RECEIPT_OUTCOMES:
        raise InvalidCanonicalEnvelopeError("receipt outcome must be ACCEPTED or REJECTED")
    reason_code = values.get("reason_code")
    reason_summary = values.get("reason_summary")
    if outcome == "REJECTED":
        reason_code = _normalize_text(reason_code, "reason_code")
        if reason_code not in REJECTION_REASON_CODES:
            raise InvalidCanonicalEnvelopeError("unsupported receipt rejection reason_code")
        reason_summary = _normalize_text(reason_summary, "reason_summary")
    elif reason_code is not None or reason_summary is not None:
        raise InvalidCanonicalEnvelopeError("accepted receipt cannot carry rejection material")
    receipt = DelegationReceipt(
        receipt_id="",
        delegation_id=_normalize_text(values["delegation_id"], "delegation_id"),
        delegated_task_hash=_normalize_hash(values["delegated_task_hash"], "delegated_task_hash"),
        capability_lease_id=_normalize_text(values["capability_lease_id"], "capability_lease_id"),
        capability_lease_hash=_normalize_hash(values["capability_lease_hash"], "capability_lease_hash"),
        authorization_id=_normalize_text(values["authorization_id"], "authorization_id"),
        authorization_hash=_normalize_hash(values["authorization_hash"], "authorization_hash"),
        attempt_id=_normalize_text(values["attempt_id"], "attempt_id"),
        attempt_hash=_normalize_hash(values["attempt_hash"], "attempt_hash"),
        route_id=_normalize_text(values["route_id"], "route_id"),
        route_hash=_normalize_hash(values["route_hash"], "route_hash"),
        launch_attempt_id=_normalize_text(values["launch_attempt_id"], "launch_attempt_id"),
        launch_attempt_hash=_normalize_hash(values["launch_attempt_hash"], "launch_attempt_hash"),
        receiver_agent_id=_normalize_text(values["receiver_agent_id"], "receiver_agent_id"),
        receiver_descriptor_hash=_normalize_hash(values["receiver_descriptor_hash"], "receiver_descriptor_hash"),
        receiver_implementation=_normalize_text(values["receiver_implementation"], "receiver_implementation"),
        receiver_version=_normalize_text(values["receiver_version"], "receiver_version"),
        runtime_run_id=_normalize_text(values["runtime_run_id"], "runtime_run_id"),
        outcome=outcome,
        reason_code=reason_code,
        reason_summary=reason_summary,
        received_at=_normalize_timestamp(values["received_at"], "received_at"),
        decided_at=_normalize_timestamp(values["decided_at"], "decided_at"),
        artifact_type=DELEGATION_RECEIPT_ARTIFACT_TYPE,
        artifact_version=ARTIFACT_VERSION,
        artifact_hash="",
    )
    if _parse_timestamp(receipt.decided_at) < _parse_timestamp(receipt.received_at):
        raise InvalidCanonicalEnvelopeError("decided_at cannot precede received_at")
    receipt = replace(receipt, receipt_id=f"receipt-{sha256_payload(receipt.to_canonical_dict(include_hash=False, include_id=False))}")
    return replace(receipt, artifact_hash=sha256_payload(receipt.to_canonical_dict(include_hash=False)))


def reconstruct_delegation_receipt(payload: Mapping[str, Any]) -> DelegationReceipt:
    required = set(DelegationReceipt.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise InvalidCanonicalEnvelopeError(f"delegation receipt requires exactly {sorted(required)}")
    if payload["artifact_type"] != DELEGATION_RECEIPT_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION:
        raise InvalidCanonicalEnvelopeError("unsupported delegation receipt schema")
    rebuilt = build_delegation_receipt(**{
        key: payload[key] for key in required
        if key not in {"receipt_id", "artifact_type", "artifact_version", "artifact_hash"}
    })
    if payload["receipt_id"] != rebuilt.receipt_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("delegation receipt identity or hash mismatch")
    return rebuilt
