"""Execution-authority persistence interface and errors (EA-2).

This module defines the abstract store contract and the EA-2 persistence error
hierarchy. It does NOT implement storage, issuance, or any execution behavior.

EA-2 stores *representations* of EA-1 domain artifacts. It answers:
- what immutable artifact was persisted
- whether that artifact still verifies
- what audit events exist
- whether the persistence chain is intact

It does NOT decide whether authorization should be granted. That belongs to
EA-3. No call here authorizes, issues, claims, or executes anything.

Design source of truth:
    docs/architecture/hermes-execution-authorization-handoff.md
    docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationRequest,
)


class ExecutionAuthorizationStoreError(RuntimeError):
    """Base error for the execution-authority store layer (EA-2)."""


class ExecutionAuthorizationIntegrityError(ExecutionAuthorizationStoreError):
    """Raised when persisted execution-authority data fails integrity.

    Distinct from ``ExecutionAuthorizationValidationError`` (EA-1 domain
    structure) and ``GovernanceIntegrityError`` (governance store). Reserved
    during EA-1; introduced here for persisted-tamper / chain-break detection.
    """


class ExecutionAuthorizationSchemaError(ExecutionAuthorizationStoreError):
    """Raised on missing, corrupt, or unsupported schema version."""


class ExecutionAuthorizationConflictError(ExecutionAuthorizationStoreError):
    """Raised when an immutable artifact id collides with conflicting content."""


class ExecutionAuthorityLedgerEntry:
    """One hash-linked authority-ledger event (mirrors ledger.LedgerEntry)."""

    __slots__ = (
        "event_id",
        "event_type",
        "artifact_type",
        "artifact_id",
        "artifact_hash",
        "payload_sha256",
        "previous_entry_sha256",
        "entry_sha256",
        "timestamp",
    )

    def __init__(
        self,
        event_id: str,
        event_type: str,
        artifact_type: str,
        artifact_id: str,
        artifact_hash: str,
        payload_sha256: str,
        previous_entry_sha256: Optional[str],
        entry_sha256: str,
        timestamp: str,
    ) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.artifact_type = artifact_type
        self.artifact_id = artifact_id
        self.artifact_hash = artifact_hash
        self.payload_sha256 = payload_sha256
        self.previous_entry_sha256 = previous_entry_sha256
        self.entry_sha256 = entry_sha256
        self.timestamp = timestamp


@dataclass
class IntegrityReport:
    ok: bool
    checked: int
    failures: tuple[str, ...] = ()


class ExecutionAuthorizationStore:
    """Abstract persistence contract for execution-authority artifacts (EA-2).

    All methods persist or read EA-1 immutable representations. None authorizes,
    issues, claims, consumes, or executes.
    """

    # -- requests -----------------------------------------------------------
    def record_request(self, request: ExecutionAuthorizationRequest) -> None:
        raise NotImplementedError

    def get_request(self, request_id: str) -> Optional[ExecutionAuthorizationRequest]:
        raise NotImplementedError

    # -- decisions ----------------------------------------------------------
    def record_decision(self, decision: ExecutionAuthorizationDecision) -> None:
        raise NotImplementedError

    def get_decision(self, decision_id: str) -> Optional[ExecutionAuthorizationDecision]:
        raise NotImplementedError

    # -- authorizations -----------------------------------------------------
    def record_authorization(self, authorization: ExecutionAuthorization) -> None:
        raise NotImplementedError

    def get_authorization(
        self, authorization_id: str
    ) -> Optional[ExecutionAuthorization]:
        raise NotImplementedError

    # -- ledger / integrity -------------------------------------------------
    def get_authority_events(self) -> list[ExecutionAuthorityLedgerEntry]:
        raise NotImplementedError

    def verify_integrity(self) -> IntegrityReport:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
