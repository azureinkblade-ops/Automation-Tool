"""Persistence abstraction for Hermes deterministic governance artifacts.

This module defines the ``GovernanceStore`` contract, the governance event/chain
value types, and the error hierarchy. It is deliberately free of any SQL, SQLite,
or filesystem knowledge: concrete persistence lives behind this interface
(``SQLiteGovernanceStore``).

The deterministic domain logic of 6A/6B/6C/6D stays SQL-free; this store is
the single seam where governance state touches a backing store. No deterministic
identity (finding/evaluation/disposition/acceptance sha256) is ever derived from
a database row id. No execution authority is granted by persisting governance.

See ``docs/architecture/hermes-governance-store.md`` for the contract rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .acceptance_artifact import AcceptanceArtifact
from .consensus_disposition import ConsensusDisposition
from .consensus_evaluator import ConsensusEvaluation
from .finding_normalizer import NormalizedFindingSet


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class GovernanceStoreError(RuntimeError):
    """Base error for governance persistence failures."""


class GovernanceIntegrityError(GovernanceStoreError):
    """Stored governance data failed re-verification or ledger tamper detected."""


class GovernanceConflictError(GovernanceStoreError):
    """A record with the same identity but different content was rejected."""


class GovernanceTransitionError(GovernanceStoreError):
    """A governance state transition was invalid or could not be recorded."""


class GovernanceSchemaError(GovernanceStoreError):
    """Schema bootstrap, version mismatch, or migration failure."""


class GovernanceSqliteError(GovernanceStoreError):
    """A raw SQLite/Driver failure wrapped as a governance error."""


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceEvent:
    """One append-only, hash-linked governance event."""

    sequence_no: int
    task_id: str
    event_type: str
    subject_sha256: str
    previous_event_hash: str | None
    event_hash: str
    created_at: str
    event_id: str | None = None


@dataclass(frozen=True)
class GovernanceChain:
    """Read-back of a task's persisted governance records."""

    task_id: str
    finding_set: NormalizedFindingSet | None = None
    evaluation: ConsensusEvaluation | None = None
    disposition: ConsensusDisposition | None = None
    acceptance: AcceptanceArtifact | None = None
    governance_state: str | None = None
    events: tuple[GovernanceEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntegrityReport:
    """Result of a ledger / record integrity verification."""

    ok: bool
    checked: int
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verified(self) -> bool:
        return self.ok and not self.failures


# ---------------------------------------------------------------------------
# Store contract
# ---------------------------------------------------------------------------


class GovernanceStore(ABC):
    """Authoritative persistence seam for deterministic governance artifacts.

    Implementations must satisfy:
      * domain objects only cross the boundary at record time
      * no SQL types / row ids leak into deterministic identity
      * writes are transactional (atomic)
      * identical repeats are idempotent
      * same identity + different content fails closed (GovernanceConflictError)
      * read-back reproduces domain-equivalent objects
      * persistence never mutates the supplied objects
    """

    # --- record the four deterministic artifacts -------------------------

    @abstractmethod
    def record_finding_set(self, finding_set: NormalizedFindingSet) -> None: ...

    @abstractmethod
    def record_consensus_evaluation(self, evaluation: ConsensusEvaluation) -> None: ...

    @abstractmethod
    def record_consensus_disposition(self, disposition: ConsensusDisposition) -> None: ...

    @abstractmethod
    def record_acceptance(self, acceptance: AcceptanceArtifact) -> None: ...

    # --- ledger -----------------------------------------------------------

    @abstractmethod
    def append_governance_event(self, event: GovernanceEvent) -> GovernanceEvent: ...

    @abstractmethod
    def load_task_governance_chain(self, task_id: str) -> GovernanceChain: ...

    @abstractmethod
    def verify_integrity(self) -> IntegrityReport: ...

    # --- governed state transition ---------------------------------------

    @abstractmethod
    def current_state(self, task_id: str) -> str | None: ...

    @abstractmethod
    def record_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        *,
        actor: str = "hermes",
    ) -> GovernanceEvent: ...
