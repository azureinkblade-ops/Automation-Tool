"""EA-4D.4F-R12C: thin composition binding delegation artifacts to existing EA-4D.4A-E mechanics.

FROZEN R11 BOUNDARY (Section 20.3):
    "R12C composition: one thin service binding the new artifacts to existing
    authorization/attempt/router/start mechanics with deterministic fake agents."

This module binds R12A/R12B delegation artifacts (DelegatedTaskEnvelope,
DelegatedCapabilityLease, AgentMailboxMessage, DelegationReceipt) to the
existing EA-4D.4A-E execution chain using DETERMINISTIC FAKE RECEIVERS.

It does NOT:
    - invoke real Codex or any real agent
    - execute delegated work
    - project work to EXECUTING
    - persist runtime sessions or return real agent results

Authority limits: CPU-only. No GPU, no ComfyUI, no subprocess, no network.
SQLite/file access used for Hermes-owned durable state only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tools.hermes_core.delegated_task import (
    ARTIFACT_VERSION,
    DelegatedCapabilityLease,
    DelegatedTaskEnvelope,
    DelegationIntegrityError,
    build_delegated_capability_lease,
    build_delegated_task_envelope,
    reconstruct_capability_lease,
)
from tools.hermes_core.delegation_delivery import (
    AgentMailboxMessage,
    DelegationReceipt,
    build_delegation_receipt,
    build_mailbox_message,
    reconstruct_mailbox_message,
)


class DelegationCompositionError(RuntimeError):
    """Raised when delegation composition fails a structural or lineage check."""


class FakeReceiverError(DelegationCompositionError):
    """Raised when the deterministic fake receiver encounters invalid input."""


@dataclass(frozen=True)
class FakeReceiverResult:
    """Deterministic result from a fake receiver invocation.

    This is NOT a real agent result. It is a structural proof that the
    composition bound the delegation artifacts to the execution chain
    correctly, without invoking any real agent.
    """
    receiver_agent_id: str
    attempt_id: str
    outcome: str  # ACCEPTED | REJECTED
    processed_at: str
    result_hash: str


def deterministic_fake_receiver(
    *,
    envelope: DelegatedTaskEnvelope,
    lease: DelegatedCapabilityLease,
    message: AgentMailboxMessage,
    attempt_id: str,
    route_id: str,
    launch_attempt_id: str,
    authorization_id: str,
    claim_id: str,
    request_id: str,
    decision_id: str,
    task_id: str,
    worker_id: str,
    worker_class: Optional[str],
    worker_version: str,
    operation: str,
    input_hash: str,
    reservation_id: str,
    processed_at: str,
) -> FakeReceiverResult:
    """Deterministic fake receiver for R12C composition testing.

    Validates the binding between delegation artifacts and the execution
    chain, then returns a deterministic structural result. No real agent
    is invoked; no work is executed.
    """
    # Validate lineage binding
    if lease.delegation_id != envelope.delegation_id:
        raise FakeReceiverError("lease delegation_id mismatch")
    if message.delegation_id != envelope.delegation_id:
        raise FakeReceiverError("message delegation_id mismatch")
    if message.attempt_id != attempt_id:
        raise FakeReceiverError("message attempt_id mismatch")

    # Deterministic result hash from bound material
    material = {
        "receiver_agent_id": message.recipient_agent_id,
        "attempt_id": attempt_id,
        "delegation_id": envelope.delegation_id,
        "delegation_revision": envelope.delegation_revision,
        "task_input_hash": envelope.task_input_hash,
        "lease_artifact_hash": lease.artifact_hash,
        "operation": operation,
        "input_hash": input_hash,
        "processed_at": processed_at,
    }
    from tools.hermes_core.hashing import sha256_payload, canonical_json
    result_hash = sha256_payload(json.dumps(material, sort_keys=True, separators=(",", ":")))

    return FakeReceiverResult(
        receiver_agent_id=message.recipient_agent_id,
        attempt_id=attempt_id,
        outcome="ACCEPTED",
        processed_at=processed_at,
        result_hash=result_hash,
    )


def compose_delegation_with_chain(
    *,
    envelope: DelegatedTaskEnvelope,
    lease: DelegatedCapabilityLease,
    message: AgentMailboxMessage,
    receipt: DelegationReceipt,
    attempt_id: str,
    route_id: str,
    launch_attempt_id: str,
    authorization_id: str,
    claim_id: str,
    request_id: str,
    decision_id: str,
    task_id: str,
    worker_id: str,
    worker_class: Optional[str],
    worker_version: str,
    operation: str,
    input_hash: str,
    reservation_id: str,
    processed_at: str,
    receiver: Optional[Callable[..., FakeReceiverResult]] = None,
) -> FakeReceiverResult:
    """Bind R12A/R12B delegation artifacts to existing EA-4D.4A-E mechanics.

    This is the R12C composition entry point. It verifies the structural
    binding between delegation artifacts and the execution chain identity
    fields, then invokes the (fake) receiver to produce a deterministic
    structural result.

    Does NOT invoke real agents, execute work, or project EXECUTING.
    """
    if receiver is None:
        receiver = deterministic_fake_receiver

    # Verify receipt lineage matches execution chain identity
    if receipt.attempt_id != attempt_id:
        raise DelegationCompositionError("receipt attempt_id mismatch")
    if receipt.delegation_id != envelope.delegation_id:
        raise DelegationCompositionError("receipt delegation_id mismatch")
    if receipt.capability_lease_id != lease.lease_id:
        raise DelegationCompositionError("receipt lease_id mismatch")

    # Verify envelope/lease/message/receipt hash integrity
    envelope.verify_hash()
    lease.verify_hash()
    message.verify_hash()
    receipt.verify_hash()

    # Invoke the deterministic fake receiver with the bound chain identity
    return receiver(
        envelope=envelope,
        lease=lease,
        message=message,
        attempt_id=attempt_id,
        route_id=route_id,
        launch_attempt_id=launch_attempt_id,
        authorization_id=authorization_id,
        claim_id=claim_id,
        request_id=request_id,
        decision_id=decision_id,
        task_id=task_id,
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=worker_version,
        operation=operation,
        input_hash=input_hash,
        reservation_id=reservation_id,
        processed_at=processed_at,
    )
